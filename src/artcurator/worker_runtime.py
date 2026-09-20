"""Evidence-only worker entrypoint: canonical inputs in, typed response out."""
import contextlib
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .config import ROOT, environment, confine_writes
from .worker_adapter import descriptor, handshake
from .worker_protocol import ProtocolError, Request, Response, validate_response


def serve(signal: str) -> None:
    request = Request.model_validate_json(sys.stdin.read())
    actual = handshake(signal, actual=True)
    if request.handshake != actual or request.signal != signal or time.time() >= request.deadline:
        raise ProtocolError("handshake_or_deadline_mismatch")
    path = Path(request.tensor_file).resolve()
    if not path.is_relative_to(ROOT) or path.parent.name != "worker-exchange":
        raise ProtocolError("invalid_tensor_location")
    environment(path.parent.parent)
    confine_writes()

    def deny_state(event: str, args: tuple) -> None:
        if event == "sqlite3.connect":
            raise PermissionError("Workers cannot open coordinator SQLite state")
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            if "manifest.sqlite" in str(args[0]):
                raise PermissionError("Workers cannot access coordinator state files")

    sys.addaudithook(deny_state)
    images = []
    # Model libraries may print progress; stdout is reserved exclusively for the protocol.
    with contextlib.redirect_stdout(sys.stderr):
        from .resources import Budgets
        import torch
        free, total = torch.cuda.mem_get_info(0)
        cap = Budgets.choose(1, 1, 1, [(total, free)]).gpu_bytes[0]
        torch.cuda.set_per_process_memory_fraction(cap / total, 0)
        if signal == "qrealign":
            from .qrealign_worker import load
            predictor = load(path.parent.parent)
        else:
            from .hpsv3_model import load
            predictor = load("8bit")
        if (predictor.name, predictor.revision, predictor.preproc) != descriptor(signal):
            raise ProtocolError("loaded_artifact_mismatch")
        try:
            with np.load(path, allow_pickle=False) as tensors:
                if tensors.files != [f"input_{i}" for i in range(len(request.input_ids))]:
                    raise ProtocolError("tensor_count_or_order")
                for key in tensors.files:
                    value = tensors[key]
                    if value.dtype != np.uint8 or value.ndim != 3 or value.shape[2] != 3:
                        raise ProtocolError("tensor_schema")
                    images.append(Image.fromarray(value))
            values = predictor.predict(images).reshape(len(images), -1)
        finally:
            for image in images:
                image.close()
    response = Response(run_id=request.run_id, request_id=request.request_id, handshake=actual,
                        input_ids=request.input_ids, values=tuple(tuple(float(v) for v in row) for row in values),
                        provider="cuda:0")
    validate_response(request, response)
    print(response.model_dump_json())
