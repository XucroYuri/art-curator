"""Isolated Transformers 5 Q-ReAlign-Mini pass; no alternate-model fallback."""
from __future__ import annotations
import importlib.metadata
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from .models import CPUInference, Predictor

if TYPE_CHECKING:
    from torch import Tensor


def load(out: Path) -> Predictor:
    """Resolve an immutable Mini snapshot before invoking pyiqa's official metric."""
    import pyiqa
    import torch
    from huggingface_hub import snapshot_download
    from torchvision.transforms.functional import to_tensor

    repo = "q-future/Q-ReAlign-Mini-0.8B"
    revision = "fe1f45a7574c9e9d908875af9f7e90cb946aa19f"
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
    from .worker_runtime import serve
    serve("qrealign")


if __name__ == "__main__":
    main()
