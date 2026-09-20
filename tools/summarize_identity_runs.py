# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pydantic>=2"]
# ///
# How to run: uv run --no-project --python .venv-identity/Scripts/python.exe python tools/summarize_identity_runs.py out/library out/review out/similarity
"""Derive generic, reproducible performance/LOO tables from completed receipts."""
import csv
import json
import sys
from pathlib import Path

import numpy as np

from artcurator.identity_store import atomic_bytes, file_digest, load_provenance


def main() -> None:
    outputs = [Path(arg) for arg in sys.argv[1:]]
    records = []
    for alias, out in zip(("library", "review", "similarity"), outputs, strict=True):
        receipt = json.loads((out / "identity-gpu-run.json").read_bytes())
        with (out / "identity-timings.jsonl").open(encoding="utf-8") as handle:
            stages = [json.loads(line) for line in handle if line.strip()]
        detection = next(s for s in stages if s["stage"] == "identity-detect" and s["completed"])
        latest = {s["stage"]: s for s in stages if s["completed"]}
        with (out / "identity-faces.csv").open(encoding="utf-8", newline="") as handle:
            images = {row["image_sha16"]: float(row["image_best_face_sim"]) for row in csv.DictReader(handle)
                      if row["image_best_face_sim"]}
        crops = load_provenance(out).crops
        record = {"corpus": alias, "images": receipt["ab"]["images"], "faces": receipt["faces"],
            "unique_crop_digests": len(set(crops.values())), "duplicate_crop_faces": len(crops) - len(set(crops.values())),
            "detection_seconds_historical": detection["seconds"],
            "detection_s_per_image_historical": detection["seconds"] / receipt["ab"]["images"],
            "embedding_stage_seconds": latest["identity-embed"]["seconds"],
            "embedding_stage_s_per_face": latest["identity-embed"]["seconds"] / receipt["faces"],
            "gpu_inference_s_per_computed_face": receipt["embedding"]["inference_seconds"] / receipt["embedding"]["computed"],
            "clustering_seconds": latest["identity-cluster"]["seconds"],
            "report_seconds": latest["identity-report"]["seconds"],
            "peak_ram_bytes": max(latest[s]["peak_ram_bytes"] for s in ("identity-embed", "identity-cluster", "identity-report")),
            "gpu_rerun_wall_seconds": receipt["wall_seconds"],
            "composite_with_historical_detection_seconds": receipt["wall_seconds"] + detection["seconds"],
            "loo_image_mean": float(np.mean(list(images.values()))),
            "loo_image_median": float(np.median(list(images.values()))),
            "receipt_sha256": file_digest(out / "identity-gpu-run.json"),
            "ab_report_sha256": file_digest(out / "identity-ab-report.md")}
        records.append(record)
    atomic_bytes(outputs[0].parent / "identity-certification/summary.json", json.dumps(records, indent=2).encode())
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
