"""Real detached-owner CLI lifecycle; synthetic pixels and local outputs only."""
import json
import subprocess
import sys
import uuid

import psutil
import pytest

from artcurator.config import ROOT, Settings
from artcurator.ingest_process import execute_process
from artcurator.ingest_adapters import Request
from artcurator.ingest_schema import Job, Options
from artcurator.ingest_storage import lease
from test_ingest import corpus as corpus
from test_ingest import snapshot


def test_background_when_client_exits_owner_finishes(corpus: Settings) -> None:
    # Given
    name = "test-owner-" + uuid.uuid4().hex
    root = ROOT / "out" / "ingest" / name
    before = snapshot(corpus.input)
    # When: launcher exits; wait on the actual owner OS process, not on a browser/session.
    client = subprocess.run([sys.executable, "-m", "artcurator.cli", "ingest", "--input", str(corpus.input),
        "--corpus", name, "--inventory-only", "--reserve-gib", "0"], cwd=ROOT,
        capture_output=True, text=True, check=True, timeout=20)
    pid = json.loads(client.stdout)["pid"]
    try:
        psutil.Process(pid).wait(timeout=60)
    except psutil.NoSuchProcess:
        pass  # Already exited before the OS wait was attached.
    # Then
    job = Job.model_validate_json((root / "job.json").read_bytes())
    assert job.progress.status == "complete", (root / "owner.log").read_text()
    assert snapshot(corpus.input) == before
    status = subprocess.run([sys.executable, "-m", "artcurator.cli", "ingest-status", "--corpus", name],
                            cwd=ROOT, capture_output=True, text=True, check=True, timeout=20)
    assert json.loads(status.stdout)["stage"] == "PROPOSE"
    guarded = subprocess.run([sys.executable, "-m", "artcurator.cli", "ingest-advance", "--corpus", name,
                              "--ingest-target", "CONFIRM"], cwd=ROOT, capture_output=True, timeout=20)
    assert guarded.returncode != 0


def test_stage_when_deadline_expires_is_not_success(corpus: Settings) -> None:
    # Given
    root = corpus.out
    root.mkdir()
    request = Request(settings=corpus.model_copy(update={"out": root / "scan" / "deadline"}),
                      options=Options(analysis=False, stage_deadline_seconds=.001), action="scan",
                      paths=tuple(corpus.input.rglob("*.png")))
    # When
    result = execute_process(request)
    # Then
    assert result.outcome == "failed"
    assert "deadline" in result.reason


def test_single_writer_when_another_owner_active_refuses(corpus: Settings) -> None:
    # Given
    from artcurator.ingest import run
    # When / Then
    with lease(corpus.out), pytest.raises(ValueError, match="owner"):
        run(corpus, Options(analysis=False, reserve_bytes=0))
