# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "Pillow", "psutil", "torch", "transformers==4.57.6", "pydantic>=2", "scikit-learn", "onnxruntime"]
# ///
# How to run: uv run --no-project --python .venv-identity/Scripts/python.exe python tools/certify_identity.py out/library out/review out/similarity
"""Fixed-crop CPU/GPU experiment; receipts contain hashes and generic corpus aliases."""
import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import psutil
import torch
from PIL import Image
from sklearn.metrics import adjusted_rand_score

from artcurator.identity_cluster import cluster_vectors
from artcurator.identity_embed import load_embedder
from artcurator.identity_profiles import PREPROCESS
from artcurator.identity_schema import IdentityOptions
from artcurator.identity_store import atomic_bytes, digest, file_digest, load_document, normalized, save_array


def comparison(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float | bool]:
    """Predeclared normalized-component and cosine budgets, no post-hoc relaxation."""
    reference64 = normalized(reference).astype(np.float64)
    candidate64 = normalized(candidate).astype(np.float64)
    cosine = 1 - np.sum(reference64 * candidate64, axis=1) / (
        np.linalg.norm(reference64, axis=1) * np.linalg.norm(candidate64, axis=1))
    error = np.abs(reference64 - candidate64)
    distances_ref = reference64 @ reference64.T
    distances_gpu = candidate64 @ candidate64.T
    ambiguity = np.abs(distances_ref - .85) <= .002
    flips = (distances_ref >= .85) != (distances_gpu >= .85)
    labels_ref, _ = cluster_vectors(reference, IdentityOptions())
    labels_gpu, _ = cluster_vectors(candidate, IdentityOptions())
    return {"max_cosine_deviation": float(cosine.max()), "median_cosine_deviation": float(np.median(cosine)),
            "max_component_error": float(error.max()), "median_component_error": float(np.median(error)),
            "component_pass": bool(np.all(error <= .001 + .001 * np.abs(reference64))),
            "cosine_pass": bool(cosine.max() <= 1e-5),
            "max_pairwise_cosine_error": float(np.max(np.abs(distances_ref - distances_gpu))),
            "probe_flips_outside_ambiguity": int(np.sum(flips & ~ambiguity)),
            "cluster_adjusted_rand": float(adjusted_rand_score(labels_ref, labels_gpu)),
            "outlier_changes": int(np.sum((labels_ref < 0) != (labels_gpu < 0)))}


def main() -> None:
    outputs = [Path(arg) for arg in sys.argv[1:]]
    if len(outputs) != 3:
        raise ValueError("provide library, review and similarity outputs in that order")
    destination = outputs[0].parent / "identity-certification"
    destination.mkdir(exist_ok=True)
    budget = {"component_atol": .001, "component_rtol": .001, "max_cosine_deviation": 1e-5,
              "pairwise_cosine_atol": .002, "cluster_ari_min": .99, "outlier_change_fraction_max": .01,
              "probe_cosine_cutoff": .85, "probe_ambiguity": .002,
              "samples_per_corpus": 128, "seed": 20260920, "benchmark_repeats": 10}
    atomic_bytes(destination / "predeclared-budgets.json", json.dumps(budget, indent=2).encode())
    samples = []
    images = []
    for alias, out in zip(("library", "review", "similarity"), outputs, strict=True):
        document = load_document(out)
        selected = sorted(document.faces, key=lambda f: digest(("20260920" + f.face_id).encode()))[:128]
        samples.append({"corpus": alias, "faces": [face.face_id for face in selected],
                        "crop_sha256": [file_digest(out / face.crop_rel) for face in selected]})
        for face in selected:
            with Image.open(out / face.crop_rel) as source:
                images.append(source.convert("RGB"))
    atomic_bytes(destination / "sample-manifest.json", json.dumps(samples, indent=2).encode())
    cpu = load_embedder(outputs[0], IdentityOptions(device="cpu"))
    cpu_values = []
    started = time.perf_counter()
    for index, image in enumerate(images):
        cpu_values.append(cpu.predict([image])[0])
        if (index + 1) % 16 == 0:
            print(f"cpu {index + 1}/{len(images)} seconds={time.perf_counter() - started:.3f}", flush=True)
    cpu_seconds = time.perf_counter() - started
    reference = np.stack(cpu_values)
    save_array(destination / "cpu-fp32.npy", reference)
    del cpu
    gc.collect()
    torch.cuda.reset_peak_memory_stats()
    gpu = load_embedder(outputs[0], IdentityOptions(device="cuda", precision="float16"))
    gpu.predict(images[:8])
    results = []
    for batch_size in (8, 16, 32):
        collected = []
        started = time.perf_counter()
        for offset in range(0, len(images), batch_size):
            collected.append(gpu.predict(images[offset:offset + batch_size]))
        elapsed = time.perf_counter() - started
        values = np.vstack(collected)
        save_array(destination / f"gpu-fp16-b{batch_size}.npy", values)
        result = {"batch_size": batch_size, "seconds": elapsed, "s_per_face": elapsed / len(images),
                  "comparison": comparison(reference, values)}
        results.append(result)
        print(json.dumps(result), flush=True)
    # Repeated randomized-order matched GPU slices: preprocessing + transfer + synchronized inference.
    benchmark = []
    rng = np.random.default_rng(20260920)
    for repeat in range(10):
        for batch_size in rng.permutation([8, 16, 32]).tolist():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            for offset in range(0, 128, batch_size):
                gpu.predict(images[offset:offset + batch_size])
            elapsed = time.perf_counter() - started
            benchmark.append({"repeat": repeat, "batch_size": batch_size, "seconds": elapsed,
                              "s_per_face": elapsed / 128,
                              "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                              "peak_reserved_bytes": torch.cuda.max_memory_reserved()})
        print(f"benchmark repeat {repeat + 1}/10", flush=True)
    serial = np.vstack([gpu.predict([image]) for image in images])
    save_array(destination / "gpu-fp16-b1.npy", serial)
    final = {"method": "128 deterministic hash-selected crops per corpus; fresh CPU FP32 and GPU FP16; fixed weights",
             "budget": budget, "sample_manifest_sha256": file_digest(destination / "sample-manifest.json"),
             "model": gpu.name, "revision": gpu.revision, "preprocess": PREPROCESS,
             "execution": gpu.execution.model_dump(), "cpu_seconds": cpu_seconds,
             "cpu_s_per_face": cpu_seconds / len(images), "gpu_batches": results, "benchmark": benchmark,
             "corpora": [], "serial_comparison": comparison(reference, serial),
             "peak_ram_bytes": psutil.Process().memory_info().peak_wset}
    for index, sample in enumerate(samples):
        interval = slice(index * 128, (index + 1) * 128)
        candidate = np.load(destination / "gpu-fp16-b16.npy", allow_pickle=False)
        final["corpora"].append({"corpus": sample["corpus"], "faces": 128,
            **comparison(reference[interval], candidate[interval]),
            "batch_vs_serial": comparison(serial[interval], candidate[interval]),
            "stored_fp16": comparison(reference[interval], candidate[interval].astype(np.float16))})
    atomic_bytes(destination / "results.json", json.dumps(final, indent=2, allow_nan=False).encode())
    for image in images:
        image.close()
    print("certification experiment complete", flush=True)


if __name__ == "__main__":
    main()
