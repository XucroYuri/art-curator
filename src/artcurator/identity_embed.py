"""Batched fixed-weight crops with device-isolated, integrity-checked caches."""
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import assert_never

import numpy as np
from PIL import Image

from .db import readonly_uri

from .identity_profiles import PREPROCESS, ExecutionProfile, certify_model, embedding_namespace, execution_profile
from .identity_schema import IdentityOptions, ModelInfo
from .identity_store import (
    atomic_bytes, digest, file_digest, load_document, load_provenance, normalized, save_array, save_model,
)


@dataclass(frozen=True, slots=True)
class CropEmbedder:
    name: str
    revision: str
    preproc: str
    predict: Callable[[list[Image.Image]], np.ndarray]
    execution: ExecutionProfile


def local_snapshot(outputs: Path, repo: str, revision: str) -> Path:
    """Resolve only the same immutable model across legacy/shared output caches."""
    suffix = f"cache/huggingface/hub/models--{repo.replace('/', '--')}/snapshots/{revision}"
    from .config import ROOT
    candidates = {*outputs.glob(f"*/{suffix}"), *(ROOT / "out").glob(f"*/{suffix}")}
    for candidate in sorted(candidates):
        if (candidate / "preprocessor_config.json").is_file() and (
            (candidate / "model.safetensors").is_file() or (candidate / "model.safetensors.index.json").is_file()
        ):
            return candidate
    raise FileNotFoundError("incumbent immutable SigLIP snapshot is not cached locally")


def load_embedder(out: Path, options: IdentityOptions) -> CropEmbedder:
    execution = execution_profile(options)
    match options.embedder:
        case "siglip":
            import torch
            from transformers import SiglipImageProcessor, SiglipVisionModel
            connection = sqlite3.connect(readonly_uri(out / "manifest.sqlite"), uri=True)
            try:
                found = connection.execute("SELECT value FROM meta WHERE key='model_siglip'").fetchone()
            finally:
                connection.close()
            if found is None:
                raise ValueError("incumbent SigLIP provenance missing; refuse a new/substitute model")
            model_name, revision, *_ = found[0].split("|")
            if options.device == "auto" and execution.device == "cuda":
                certify_model(execution, (model_name, revision))
            snapshot = local_snapshot(out.parent, model_name, revision)
            torch.set_num_threads(options.threads)
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            dtype = torch.float16 if execution.precision == "float16" else torch.float32
            processor = SiglipImageProcessor.from_pretrained(snapshot, local_files_only=True)
            model = SiglipVisionModel.from_pretrained(snapshot,
                                                      local_files_only=True, torch_dtype=dtype,
                                                      attn_implementation="sdpa")
            model.eval().to(execution.device)
            model.requires_grad_(False)

            def predict(images: list[Image.Image]) -> np.ndarray:
                inputs = processor(images=images, return_tensors="pt").pixel_values.to(execution.device, dtype)
                with torch.inference_mode():
                    return normalized(model(pixel_values=inputs).pooler_output.float().cpu().numpy())

            return CropEmbedder(model_name, revision, PREPROCESS, predict, execution)
        case "ccip":
            if not options.ccip_license_accepted:
                raise ValueError("CCIP OpenRAIL use restrictions require explicit ccip_license_accepted")
            import onnxruntime as ort
            from huggingface_hub import hf_hub_download
            repo = "deepghs/ccip_onnx"
            revision = "eb2acdd29af1703388d3d0c04221add322bc9110"
            model_name = "ccip-caformer-24-randaug-pruned/model_feat.onnx"
            path = Path(hf_hub_download(repo, model_name, revision=revision))
            config = ort.SessionOptions()
            config.intra_op_num_threads = options.threads
            config.inter_op_num_threads = 1
            session = ort.InferenceSession(str(path), sess_options=config, providers=["CPUExecutionProvider"])

            def predict_ccip(images: list[Image.Image]) -> np.ndarray:
                prepared = []
                for image in images:
                    with image.resize((384, 384), Image.Resampling.BILINEAR) as resized:
                        value = np.asarray(resized, dtype=np.float32).transpose(2, 0, 1) / 255
                    mean = np.array([.48145466, .4578275, .40821073], dtype=np.float32)[:, None, None]
                    std = np.array([.26862954, .26130258, .27577711], dtype=np.float32)[:, None, None]
                    prepared.append((value - mean) / std)
                return normalized(np.asarray(session.run(["output"], {"input": np.stack(prepared)})[0]))

            return CropEmbedder(repo + "/" + model_name, revision + ":" + file_digest(path),
                               "crop-jpeg-v1-ccip384-bilinear-clip", predict_ccip, execution)
        case unreachable:
            assert_never(unreachable)


def embed(out: Path, options: IdentityOptions) -> None:
    import torch
    started = time.perf_counter()
    document = load_document(out)
    provenance = load_provenance(out)
    if options.device != "cpu" and torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    predictor = load_embedder(out, options) if document.faces else None
    load_seconds = time.perf_counter() - started
    info = ModelInfo(name=options.embedder, model=predictor.name if predictor else "unavailable-no-faces",
                     revision=predictor.revision if predictor else "unavailable-no-faces")
    execution = predictor.execution if predictor else execution_profile(options)
    preprocess = predictor.preproc if predictor else "none"
    profile = {"model": info.model_dump(), "preprocess": preprocess,
               "semantic_profile": provenance.semantic_profile,
               "execution": execution.model_dump()}
    namespace = digest((embedding_namespace(execution, info.model + "@" + info.revision, preprocess)
                        + provenance.semantic_profile).encode())
    cache = out / "cache/identity-embedding" / namespace
    cache.mkdir(parents=True, exist_ok=True)
    values: list[np.ndarray] = []
    cached = 0
    inference_seconds = 0.
    for offset in range(0, len(document.faces), execution.batch_size):
        batch = document.faces[offset:offset + execution.batch_size]
        pending = []
        batch_values: dict[int, np.ndarray] = {}
        with ExitStack() as stack:
            images = []
            for index, face in enumerate(batch):
                path = out / face.crop_rel
                crop_hash = file_digest(path)
                if crop_hash != provenance.crops[face.face_id]:
                    raise ValueError("crop content changed; refuse stale embedding")
                target = cache / (crop_hash + ".npy")
                checksum = target.with_suffix(".sha256")
                if target.exists() and checksum.exists() and file_digest(target) == checksum.read_text():
                    value = np.load(target, allow_pickle=False)
                    if value.ndim != 1:
                        raise ValueError("cached embedding must be one vector")
                    batch_values[index] = normalized(value[None])[0]
                    cached += 1
                else:
                    source = stack.enter_context(Image.open(path))
                    images.append(stack.enter_context(source.convert("RGB")))
                    pending.append((index, target))
            if images:
                if predictor is None:
                    raise ValueError("missing embedder")
                infer_start = time.perf_counter()
                predicted = normalized(predictor.predict(images))
                inference_seconds += time.perf_counter() - infer_start
                if len(predicted) != len(pending):
                    raise ValueError("embedding batch count mismatch")
                for (index, target), value in zip(pending, predicted, strict=True):
                    save_array(target, value)
                    atomic_bytes(target.with_suffix(".sha256"), file_digest(target).encode())
                    batch_values[index] = value
        values.extend(batch_values[index] for index in range(len(batch)))
        logging.info("identity embedding progress completed=%d total=%d", len(values), len(document.faces))
    matrix = np.stack(values).astype(np.float16) if values else np.empty((0, 0), dtype=np.float16)
    save_array(out / "identities.npy", matrix)
    metrics = {"load_seconds": load_seconds, "inference_seconds": inference_seconds, "cached": cached,
               "s_per_face": inference_seconds / (len(values) - cached) if len(values) > cached else None,
               "computed": len(values) - cached, "wall_seconds": time.perf_counter() - started,
               "peak_vram_allocated_bytes": torch.cuda.max_memory_allocated() if execution.device == "cuda" else 0,
               "peak_vram_reserved_bytes": torch.cuda.max_memory_reserved() if execution.device == "cuda" else 0}
    atomic_bytes(out / "identity-embedding.json", json.dumps({**profile, "namespace": namespace, "metrics": metrics,
                 "sha256": file_digest(out / "identities.npy"), "faces": [f.face_id for f in document.faces]}).encode())
    # Derived groups must never survive replacement of their embedding matrix.
    faces = [face.model_copy(update={"cluster_id": None, "cluster_prob": 0., "is_outlier": True,
                                    "cluster_margin": None}) for face in document.faces]
    save_model(out / "identities.json", document.model_copy(update={
        "embedder": info, "faces": faces, "clusters": [], "cluster_count": 0}))
