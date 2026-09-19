"""Isolated Transformers 5 Q-ReAlign-Mini pass; no alternate-model fallback."""
from __future__ import annotations
import argparse
import importlib.metadata
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from . import db
from .cache import Pass, infer
from .config import confine_writes, environment, output_path
from .models import CPUInference, Predictor, hf_revision

if TYPE_CHECKING:
    from torch import Tensor


def load(out: Path) -> Predictor:
    """Resolve an immutable Mini snapshot before invoking pyiqa's official metric."""
    import pyiqa
    import torch
    from huggingface_hub import snapshot_download
    from torchvision.transforms.functional import to_tensor

    repo = "q-future/Q-ReAlign-Mini-0.8B"
    revision = hf_revision(repo, out)
    snapshot = snapshot_download(repo, revision=revision)
    metric = pyiqa.create_metric("qrealign", model=snapshot, device="cuda").eval()
    if metric.lower_better:
        raise RuntimeError("Q-ReAlign direction must be higher-is-better")

    def prepare(images: list[Image.Image]) -> list[Tensor]:
        return [to_tensor(image).unsqueeze(0) for image in images]

    def predict_cpu(tensors: list[Tensor]) -> np.ndarray:
        with torch.inference_mode():
            scores = [float(metric(tensor).reshape(-1)[0].cpu()) for tensor in tensors]
        return np.asarray(scores, dtype=np.float32)

    versions = f"pyiqa-{importlib.metadata.version('pyiqa')}-transformers-{importlib.metadata.version('transformers')}"
    return Predictor(repo, revision, f"pixels-v1-native-official-mini-quality-{versions}",
                     lambda images: predict_cpu(prepare(images)), CPUInference(prepare, predict_cpu))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 13), default=8)
    parser.add_argument("--prefetch-batches", type=int, choices=range(5), default=2)
    args = parser.parse_args()
    out = output_path(args.out)
    environment(out)
    confine_writes()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(out / "run.log", encoding="utf-8"), logging.StreamHandler()])
    started = time.perf_counter()
    predictor = load(out)
    rows = db.load_rows(out)
    values = infer(rows, Pass(out, "qrealign", 1, predictor, time.perf_counter() - started,
                             workers=args.workers, prefetch_batches=args.prefetch_batches))
    for row, value in zip(rows, values, strict=True):
        row.qrealign = float(value)
    db.save_rows(out, rows)
    db.meta(out, "deviation_qrealign_dependency", "Path (b): isolated .venv-qrealign, pyiqa 0.1.16 / Transformers 5.17.0. "
            "Path (a) changed 8-image aesthetic scores by up to 0.0625 (>0.001); restoring 4.57.6 gave exact equality. "
            "Main venv retains pyiqa 0.1.15.post2 and Transformers 4.57.6. No scorer substitution.")


if __name__ == "__main__":
    main()
