"""Coordinator-side isolated scorer adapter with pinned handshake expectations."""
import importlib.metadata
import json
import time
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from . import db
from .cache_identity import digest
from .config import ROOT
from .models import Predictor
from .worker_protocol import Handshake, ProtocolError, Request, exchange


def descriptor(signal: str) -> tuple[str, str, str]:
    if signal == "qrealign":
        return ("q-future/Q-ReAlign-Mini-0.8B", "fe1f45a7574c9e9d908875af9f7e90cb946aa19f",
                "pixels-v1-native-official-mini-quality-pyiqa-0.1.16-transformers-5.17.0")
    if signal == "hpsv3":
        return ("MizzenAI/HPSv3",
                "4f81e3e09edd82fe3c5f636444c721b592a735ca+processor:eed13092ef92e448dd6875b2a00151bd3f7db0ac",
                "pixels-v1-hpsv3-1.0.0-tf4.45.2-empty-prompt-official-200704-sdpa-8bit-fp32head-exp-sigma")
    raise ProtocolError("unsupported_signal")


def handshake(signal: str, *, actual: bool = False) -> Handshake:
    """Bind source build, lock bytes and independently checked worker dependency pins."""
    pins = {"transformers": "5.17.0", "pyiqa": "0.1.16"} if signal == "qrealign" else {
        "transformers": "4.45.2", "hpsv3": "1.0.0"}
    if actual:
        pins = {name: importlib.metadata.version(name) for name in pins}
    name, revision, preprocessing = descriptor(signal)
    build = digest("".join(p.read_text(encoding="utf-8") for p in sorted(Path(__file__).parent.glob("*.py"))))
    lock = digest((ROOT / "uv.lock").read_text(encoding="utf-8"))
    environment = digest(json.dumps([lock, pins], sort_keys=True))
    return Handshake(build=build, environment=environment, artifact=digest(name + "@" + revision),
                     preprocessing=digest(preprocessing), capabilities=("score", "rgb-u8-hwc-v1"),
                     execution=digest(json.dumps([environment, "cuda:0", preprocessing, "batch-1"])))


def remote_predictor(out: Path, signal: str, input_ids: list[str]) -> Predictor:
    expected = handshake(signal)
    run_id = uuid.uuid4().hex
    position = 0

    def predict(images: list[Image.Image]) -> np.ndarray:
        nonlocal position
        request_id = uuid.uuid4().hex
        directory = out / "worker-exchange"
        directory.mkdir(exist_ok=True)
        tensors = directory / f"{request_id}.npz"
        np.savez(tensors, **{f"input_{i}": np.asarray(image) for i, image in enumerate(images)})
        ids = tuple(input_ids[position:position + len(images)])
        request = Request(run_id=run_id, request_id=request_id, handshake=expected, input_ids=ids,
                          deadline=time.time() + 240, signal=signal, tensor_file=str(tensors.resolve()))
        command = [str(ROOT / f".venv-{signal}/Scripts/python.exe"), "-m", f"artcurator.{signal}_worker"]
        try:
            response = exchange(out, request, command)
        finally:
            tensors.unlink(missing_ok=True)
        if response is None:
            raise ProtocolError("worker_evidence_unavailable")
        position += len(images)
        db.meta(out, "worker_response_" + request_id, response.model_dump_json())
        values = np.asarray(response.values, dtype=np.float32)
        return values if signal == "hpsv3" else values[:, 0]

    return Predictor(*descriptor(signal), predict)
