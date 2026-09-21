"""Isolated local WD ONNX worker; stdout is a bounded versioned response only."""
import contextlib
import hashlib
import importlib.metadata
import sys
import time
from pathlib import Path

import numpy as np

from .wd_preprocess import preprocess
from .wd_projection import compact, encode_raw, load_tags
from .wd_schema import BUILD_FILES, PINS, Evidence, Request, Response


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def serve() -> None:
    import onnxruntime as ort

    request = Request.model_validate_json(sys.stdin.readline())
    h = request.handshake
    model = Path(request.model_dir)
    packages = {name: importlib.metadata.version(name) for name in PINS}
    build = hashlib.sha256(b"".join(Path(__file__).with_name(name).read_bytes()
                                    for name in BUILD_FILES)).hexdigest()
    if (h.packages != packages or h.build != build or sha(model / "model.onnx") != h.model_sha256
            or sha(model / "selected_tags.csv") != h.tags_sha256 or time.time() >= request.deadline):
        raise ValueError("WD handshake or deadline mismatch")
    if len(request.crops) != len(request.input_ids) or len(set(request.input_ids)) != len(request.input_ids):
        raise ValueError("WD input identity mismatch")
    available = ort.get_available_providers()
    if h.provider not in available:
        raise ValueError("requested WD provider is unavailable; no silent fallback")
    if h.provider == "CUDAExecutionProvider":
        with contextlib.redirect_stdout(sys.stderr):
            ort.preload_dlls(directory=request.cuda_dll_directory)
    tags = load_tags(model / "selected_tags.csv")
    if sum(category == 4 for _, category in tags) != h.model.closed_set_size:
        raise ValueError("WD closed set mismatch")
    options = ort.SessionOptions()
    options.intra_op_num_threads = h.threads
    options.inter_op_num_threads = 1
    started = time.perf_counter()
    providers = [(h.provider, {"gpu_mem_limit": 6 * 1024**3, "cudnn_conv_algo_search": "HEURISTIC"})] if h.provider == "CUDAExecutionProvider" else [h.provider]
    session = ort.InferenceSession(str(model / "model.onnx"), sess_options=options, providers=providers)
    load_seconds = time.perf_counter() - started
    if session.get_providers()[0] != h.provider:
        raise ValueError("WD provider placement mismatch")
    while True:
        if request.handshake != h or time.time() >= request.deadline:
            raise ValueError("WD persistent request identity/deadline mismatch")
        if len(request.crops) != len(request.input_ids) or len(set(request.input_ids)) != len(request.input_ids):
            raise ValueError("WD duplicate/misaligned inputs")
        values = []
        for filename, content in zip(request.crops, request.input_ids, strict=True):
            path = Path(filename)
            if sha(path) != content:
                raise ValueError("WD crop changed")
            values.append(preprocess(path))
        started = time.perf_counter()
        # Respect static batch exports; dynamic exports use the bounded request batch.
        static_batch = session.get_inputs()[0].shape[0]
        microbatch = static_batch if isinstance(static_batch, int) else len(values)
        evidence: list[Evidence] = []
        raw: list[str] = []
        for offset in range(0, len(values), microbatch):
            batch = values[offset:offset + microbatch]
            padded = batch + [batch[-1]] * (microbatch - len(batch))
            scores = session.run(None, {session.get_inputs()[0].name: np.stack(padded)})[0]
            for row in scores[:len(batch)]:
                evidence.append(compact(row, tags))
                raw.append(encode_raw(row))
        if time.time() >= request.deadline:
            raise ValueError("WD expired result")
        response = Response(handshake=h, run_id=request.run_id, request_id=request.request_id,
            input_ids=request.input_ids, evidence=evidence, raw=raw, providers_available=available,
            providers_active=session.get_providers(), load_seconds=load_seconds,
            inference_seconds=time.perf_counter() - started)
        print(response.model_dump_json(), flush=True)
        load_seconds = 0
        line = sys.stdin.readline()
        if not line:
            break
        request = Request.model_validate_json(line)


if __name__ == "__main__":
    serve()
