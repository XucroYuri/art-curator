"""Lazy, pinned local inference adapters. One model on GPU at a time."""
from __future__ import annotations
import gc
import hashlib
import importlib.metadata
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import numpy as np
from PIL import Image

from . import db

if TYPE_CHECKING:
    from torch import Tensor


@dataclass(frozen=True, slots=True)
class CPUInference:
    """Official CPU preprocessing, followed by caller-thread-only CUDA inference."""
    prepare: Callable[[list[Image.Image]], list[Tensor]]
    predict: Callable[[list[Tensor]], np.ndarray]


@dataclass(frozen=True, slots=True)
class Predictor:
    name: str
    revision: str
    preproc: str
    predict: Callable[[list[Image.Image]], np.ndarray]
    cpu: CPUInference | None = None


def release() -> None:
    import torch
    gc.collect()
    torch.cuda.empty_cache()


def weight_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def hf_revision(repo: str, out: Path) -> str:
    from huggingface_hub import HfApi
    ledger = out / "cache" / (repo.replace("/", "--") + "-revision.txt")
    if ledger.exists():
        return ledger.read_text(encoding="utf-8").strip()
    revision = HfApi().model_info(repo).sha
    if not revision:
        raise ValueError(f"No immutable revision returned: {repo}")
    ledger.write_text(revision, encoding="utf-8")
    return revision


def siglip(out: Path, repo: str = "google/siglip-so400m-patch14-384") -> Predictor:
    import torch
    from transformers import SiglipImageProcessor, SiglipVisionModel
    revision = hf_revision(repo, out)
    processor = SiglipImageProcessor.from_pretrained(repo, revision=revision)
    model = SiglipVisionModel.from_pretrained(repo, revision=revision, torch_dtype=torch.bfloat16)
    model.eval().to("cuda")

    def prepare(images: list[Image.Image]) -> list[Tensor]:
        return [processor(images=images, return_tensors="pt").pixel_values]

    def predict_cpu(tensors: list[Tensor]) -> np.ndarray:
        tensor = tensors[0].to("cuda", torch.bfloat16)
        with torch.inference_mode():
            features = model(pixel_values=tensor).pooler_output.float()
            return torch.nn.functional.normalize(features, dim=-1).cpu().numpy()

    return Predictor(repo, revision, "pixels-v1-siglip-official-bf16-normalized",
                     lambda images: predict_cpu(prepare(images)), CPUInference(prepare, predict_cpu))


def aesthetic(out: Path) -> Predictor:
    import torch
    from aesthetic_predictor_v2_5 import convert_v2_5_from_siglip
    repo = "google/siglip-so400m-patch14-384"
    revision = hf_revision(repo, out)
    model, processor = convert_v2_5_from_siglip(revision=revision, low_cpu_mem_usage=True)
    model.eval().to("cuda", torch.bfloat16)
    checkpoint = Path(torch.hub.get_dir()) / "checkpoints/aesthetic_predictor_v2_5.pth"
    head = weight_hash(checkpoint)

    def prepare(images: list[Image.Image]) -> list[Tensor]:
        return [processor(images=images, return_tensors="pt").pixel_values]

    def predict_cpu(tensors: list[Tensor]) -> np.ndarray:
        tensor = tensors[0].to("cuda", torch.bfloat16)
        with torch.inference_mode():
            return model(tensor).logits.reshape(-1).float().cpu().numpy()

    return Predictor("discus0434/aesthetic-predictor-v2-5", f"{revision}+head-sha256:{head}",
                     "pixels-v1-aes-official-bf16", lambda images: predict_cpu(prepare(images)),
                     CPUInference(prepare, predict_cpu))


def topiq(metric: str, out: Path) -> Predictor:
    import pyiqa
    import torch
    from torchvision.transforms.functional import to_tensor
    model = pyiqa.create_metric(metric, device="cuda").eval()
    if model.lower_better:
        raise ValueError(f"Unexpected metric direction: {metric}")
    weights = sorted(Path(torch.hub.get_dir()).rglob("cfanet*.pth"))
    tag = "ava_swin" if metric == "topiq_iaa" else "koniq_res50"
    selected = [p for p in weights if tag in p.name]
    if not selected:
        raise FileNotFoundError(f"Cannot fingerprint {metric} weights in project torch cache")
    revision = importlib.metadata.version("pyiqa") + ":" + ";".join(weight_hash(p) for p in selected)

    def prepare(images: list[Image.Image]) -> list[Tensor]:
        return [to_tensor(image).unsqueeze(0) for image in images]

    def predict_cpu(tensors: list[Tensor]) -> np.ndarray:
        # Native-resolution microbatches avoid padding/resizing changes to NR scores.
        scores = []
        with torch.inference_mode():
            for cpu_tensor in tensors:
                tensor = cpu_tensor.to("cuda")
                scores.append(float(model(tensor).reshape(-1)[0].cpu()))
        return np.asarray(scores, dtype=np.float32)

    return Predictor(metric, revision, "pixels-v1-native-rgb-fp32-official-microbatch1",
                     lambda images: predict_cpu(prepare(images)), CPUInference(prepare, predict_cpu))


def safety(out: Path) -> Predictor:
    import torch
    from transformers import AutoImageProcessor, AutoModelForImageClassification
    repo = "Falconsai/nsfw_image_detection"
    revision = hf_revision(repo, out)
    processor = AutoImageProcessor.from_pretrained(repo, revision=revision, use_fast=False)
    model = AutoModelForImageClassification.from_pretrained(repo, revision=revision).eval().to("cuda")
    labels = {str(label).lower(): int(index) for index, label in model.config.id2label.items()}
    nsfw_index = labels["nsfw"]

    def prepare(images: list[Image.Image]) -> list[Tensor]:
        return [processor(images=images, return_tensors="pt").pixel_values]

    def predict_cpu(tensors: list[Tensor]) -> np.ndarray:
        inputs = {"pixel_values": tensors[0].to("cuda")}
        with torch.inference_mode():
            return model(**inputs).logits.softmax(-1)[:, nsfw_index].float().cpu().numpy()

    return Predictor(repo, revision, "pixels-v1-official-fp32-softmax-nsfw",
                     lambda images: predict_cpu(prepare(images)), CPUInference(prepare, predict_cpu))


def load(name: str, out: Path) -> Predictor:
    match name:
        case "siglip":
            try:
                return siglip(out)
            except (OSError, RuntimeError) as error:
                logging.warning("siglip fallback reason=%s", error)
                db.meta(out, "siglip_fallback", str(error))
                release()
                return siglip(out, "google/siglip-base-patch16-384")
        case "aes_v25":
            return aesthetic(out)
        case "topiq_iaa" | "topiq_nr":
            return topiq(name, out)
        case "nsfw_prob":
            return safety(out)
        case _:
            raise ValueError(f"Unknown model: {name}")
