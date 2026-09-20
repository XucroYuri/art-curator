# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "Pillow", "psutil", "torch", "transformers==4.57.6", "pydantic>=2", "scikit-learn", "onnxruntime"]
# ///
# How to run: uv run --no-project --python .venv-identity/Scripts/python.exe python tools/certify_identity_fp32.py out/library out/review out/similarity
"""CUDA FP32 candidate after failed FP16; reuse the exact immutable CPU sample."""
import json
import sys
import time
from pathlib import Path

import numpy as np
import psutil
import torch
from PIL import Image

from artcurator.identity_embed import load_embedder
from artcurator.identity_schema import IdentityOptions
from artcurator.identity_store import atomic_bytes, file_digest, normalized, save_array
from certify_identity import comparison


def strict_comparison(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float | bool]:
    """Original budgets retained; strict FP32 component agreement is an ADR-0004 diagnostic."""
    result = comparison(reference, candidate)
    error = np.abs(normalized(reference).astype(np.float64) - normalized(candidate).astype(np.float64))
    result["fp32_component_pass"] = bool(np.all(error <= 1e-5 + 1e-4 * np.abs(reference)))
    ref_pairs = normalized(reference) @ normalized(reference).T
    gpu_pairs = normalized(candidate) @ normalized(candidate).T
    inversions = 0
    for before, after in zip(ref_pairs, gpu_pairs, strict=True):
        gap = before[:, None] - before[None, :]
        changed = (gap > .004) & ((after[:, None] - after[None, :]) < 0)
        inversions += int(changed.sum())
    result["rank_inversions_outside_ambiguity"] = inversions
    return result


def main() -> None:
    outputs = [Path(arg) for arg in sys.argv[1:]]
    if len(outputs) != 3:
        raise ValueError("provide three output corpora")
    destination = outputs[0].parent / "identity-certification"
    prior = json.loads((destination / "results.json").read_bytes())
    if file_digest(destination / "sample-manifest.json") != prior["sample_manifest_sha256"]:
        raise ValueError("CPU reference sample changed")
    atomic_bytes(destination / "fp32-predeclared-budgets.json", json.dumps({**prior["budget"],
        "additional_fp32_component_atol": 1e-5, "additional_fp32_component_rtol": 1e-4,
        "rank_pair_gap_ambiguity": .004, "strict_rank_inversions_max": 0,
        "cpu_reference_sha256": file_digest(destination / "cpu-fp32.npy")}, indent=2).encode())
    manifest = json.loads((destination / "sample-manifest.json").read_bytes())
    images = []
    for sample, out in zip(manifest, outputs, strict=True):
        for face_id, crop_hash in zip(sample["faces"], sample["crop_sha256"], strict=True):
            path = out / "faces" / (face_id + ".jpg")
            if file_digest(path) != crop_hash:
                raise ValueError("sample crop content changed")
            with Image.open(path) as source:
                images.append(source.convert("RGB"))
    reference = np.load(destination / "cpu-fp32.npy", allow_pickle=False)
    torch.cuda.reset_peak_memory_stats()
    gpu = load_embedder(outputs[0], IdentityOptions(device="cuda", precision="float32"))
    gpu.predict(images[:8])
    batches = []
    for size in (1, 8, 16, 32):
        started = time.perf_counter()
        values = np.vstack([gpu.predict(images[offset:offset + size]) for offset in range(0, len(images), size)])
        elapsed = time.perf_counter() - started
        save_array(destination / f"gpu-fp32-b{size}.npy", values)
        result = {"batch_size": size, "seconds": elapsed, "s_per_face": elapsed / len(images),
                  "comparison": strict_comparison(reference, values)}
        batches.append(result)
        print(json.dumps(result), flush=True)
    serial = np.load(destination / "gpu-fp32-b1.npy", allow_pickle=False)
    benchmark = []
    rng = np.random.default_rng(20260920)
    for repeat in range(10):
        for size in rng.permutation([8, 16, 32]).tolist():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            for offset in range(0, 128, size):
                gpu.predict(images[offset:offset + size])
            elapsed = time.perf_counter() - started
            benchmark.append({"repeat": repeat, "batch_size": size, "seconds": elapsed,
                              "s_per_face": elapsed / 128,
                              "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                              "peak_reserved_bytes": torch.cuda.max_memory_reserved()})
        print(f"fp32 benchmark repeat {repeat + 1}/10", flush=True)
    selected = min((8, 16, 32), key=lambda size: float(np.median([
        record["s_per_face"] for record in benchmark if record["batch_size"] == size])))
    candidate = np.load(destination / f"gpu-fp32-b{selected}.npy", allow_pickle=False)
    corpora = []
    for index, sample in enumerate(manifest):
        interval = slice(index * 128, (index + 1) * 128)
        corpora.append({"corpus": sample["corpus"], "faces": 128,
            **strict_comparison(reference[interval], candidate[interval]),
            "batch_vs_serial": strict_comparison(serial[interval], candidate[interval]),
            "stored_fp16": comparison(reference[interval], candidate[interval].astype(np.float16))})
    result = {"model": gpu.name, "revision": gpu.revision, "preprocess": gpu.preproc,
              "execution": gpu.execution.model_copy(update={"batch_size": selected}).model_dump(),
              "selected_batch": selected, "gpu_batches": batches, "benchmark": benchmark, "corpora": corpora,
              "cpu_evidence_sha256": file_digest(destination / "results.json"),
              "sample_manifest_sha256": prior["sample_manifest_sha256"],
              "cpu_reference_sha256": file_digest(destination / "cpu-fp32.npy"),
              "peak_ram_bytes": psutil.Process().memory_info().peak_wset}
    atomic_bytes(destination / "fp32-results.json", json.dumps(result, indent=2, allow_nan=False).encode())
    for image in images:
        image.close()
    print("FP32 experiment complete", flush=True)


if __name__ == "__main__":
    main()
