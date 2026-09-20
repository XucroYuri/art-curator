"""Fake worker failures must never become authoritative default scores."""
import subprocess
import time
import sys
from pathlib import Path

import pytest


def request_fixture():
    from artcurator.worker_protocol import Handshake, Request
    handshake = Handshake(build="a" * 64, environment="b" * 64, artifact="c" * 64,
                          preprocessing="d" * 64, execution="e" * 64, capabilities=("score",))
    return Request(run_id="run", request_id="request", handshake=handshake,
                   input_ids=("1" * 64, "2" * 64), deadline=time.time() + 60)


@pytest.mark.parametrize("failure", ["handshake", "reordered", "count", "stale", "nonfinite"])
def test_response_when_invalid(failure: str) -> None:
    # Given a current request and a deliberately invalid stub response.
    from artcurator.worker_protocol import Response, ProtocolError, validate_response
    request = request_fixture()
    response = Response(request_id=request.request_id, run_id=request.run_id,
                        handshake=request.handshake, input_ids=request.input_ids,
                        values=((.2,), (.3,)), provider="cuda:0")
    updates = {
        "handshake": {"handshake": request.handshake.model_copy(update={"build": "f" * 64})},
        "reordered": {"input_ids": tuple(reversed(request.input_ids))},
        "count": {"values": ((.2,),)},
        "stale": {"request_id": "old-request"},
        "nonfinite": {"values": ((float("nan"),), (.3,))},
    }
    # When accepting it; then no positional repair or default is permitted.
    with pytest.raises(ProtocolError):
        validate_response(request, response.model_copy(update=updates[failure]))


def test_timeout_when_stub_worker_expires(tmp_path: Path) -> None:
    # Given a transport timing out instead of returning evidence.
    from artcurator import db
    from artcurator.worker_protocol import exchange
    request = request_fixture()

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    # When the coordinator exchanges a request; then it records failure only.
    assert exchange(tmp_path, request, ["stub"], transport=timeout) is None
    with db.connection(tmp_path) as connection:
        record = connection.execute("SELECT value FROM meta WHERE key=?", ("worker_failure_request",)).fetchone()
    assert '"reason": "timeout"' in record[0]


@pytest.mark.parametrize("mode", ["valid", "reorder"])
def test_exchange_when_real_stub_process(tmp_path: Path, mode: str) -> None:
    # Given a real foreground Python process, without GPU/model work.
    from artcurator.worker_protocol import exchange
    request = request_fixture()
    command = [sys.executable, str(Path(__file__).parent / "fixtures/protocol_worker.py"), mode]
    # When exchanged; then only the ordered response is accepted.
    response = exchange(tmp_path, request, command)
    assert (response is not None) == (mode == "valid")


def test_coordinator_when_worker_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given previously scored content, and a worker transport that times out.
    from PIL import Image
    from artcurator import db, worker_adapter
    from artcurator.isolated_score import score_isolated
    from artcurator.scan import inspect
    from artcurator.worker_protocol import exchange
    image = tmp_path / "image.png"
    Image.new("RGB", (4, 4)).save(image)
    row = inspect(image, tmp_path).model_copy(update={"qrealign": .9})
    db.save_rows(tmp_path, [row])

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(worker_adapter, "exchange",
                        lambda out, request, command: exchange(out, request, command, transport=timeout))
    # When scoring; then stale evidence is cleared, never replaced by a default.
    score_isolated(tmp_path, "qrealign")
    assert db.load_rows(tmp_path)[0].qrealign is None
