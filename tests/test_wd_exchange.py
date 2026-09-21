"""Real subprocess protocol rejection without an ONNX model download."""
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from artcurator.wd_exchange import Exchange
from artcurator.wd_schema import Handshake, Request, Response


@pytest.mark.parametrize("fault", ["request_id", "input_ids", "providers_active", "evidence"])
def test_exchange_when_lineage_corrupted(fault: str) -> None:
    # Given a valid typed request and a real process returning malformed lineage.
    handshake = Handshake(build="a" * 64, model_sha256="b" * 64, tags_sha256="c" * 64, packages={})
    request = Request(handshake=handshake, run_id="run", request_id="request", deadline=time.time() + 10,
                      model_dir="unused", crops=["unused"], input_ids=["d" * 64])
    response = Response(handshake=handshake, run_id="run", request_id="request", input_ids=["d" * 64],
        evidence=[{}], providers_available=["CPUExecutionProvider"], providers_active=["CPUExecutionProvider"],
        load_seconds=0, inference_seconds=0).model_dump()
    response[fault] = {"request_id": "wrong", "input_ids": ["e" * 64],
                       "providers_active": ["CUDAExecutionProvider"], "evidence": []}[fault]
    script = "import sys; sys.stdin.readline(); print(" + repr(json.dumps(response)) + ",flush=True)"
    with subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          text=True) as process, ThreadPoolExecutor(max_workers=1) as reader:
        # When exchanging; then corrupted results are rejected before cache publication.
        with pytest.raises(ValueError, match="lineage"):
            Exchange(process, reader).request(request)


def test_exchange_when_response_matches() -> None:
    # Given a self-contained echo worker speaking the versioned protocol.
    handshake = Handshake(build="a" * 64, model_sha256="b" * 64, tags_sha256="c" * 64, packages={})
    request = Request(handshake=handshake, run_id="run", request_id="request", deadline=time.time() + 10,
                      model_dir="unused", crops=["unused"], input_ids=["d" * 64])
    script = ("import sys,json; r=json.loads(sys.stdin.readline()); "
              "r.update(evidence=[{}],providers_available=['CPUExecutionProvider'],"
              "providers_active=['CPUExecutionProvider'],load_seconds=0,inference_seconds=0); "
              "print(json.dumps(r),flush=True)")
    with subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          text=True) as process, ThreadPoolExecutor(max_workers=1) as reader:
        # When exchanging; then exact input identity and compact empty evidence survive.
        response = Exchange(process, reader).request(request)
        assert response.input_ids == ["d" * 64]
        assert response.evidence[0].characters == []
