"""Fake-clock heartbeats and storage-fault boundaries for ingestion ACs."""
import shutil

import pytest

from artcurator.config import Settings
from artcurator.ingest import run
from artcurator.ingest_adapters import execute
from artcurator.ingest_runtime import Runtime, control
from artcurator.ingest_schema import Job, Options, Progress, Stage
from test_ingest import corpus as corpus
from test_ingest import snapshot


def test_pause_ack_when_clock_advances_one_tick(corpus: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a deterministic heartbeat scheduler, no sleeps or timing-dependent assertions.
    import artcurator.ingest_runtime as module
    corpus.out.mkdir()
    job = Job(job_id="clock", root=corpus.input, profile_digest="fixture",
              progress=Progress(stage=Stage.ANALYZE, status="running", heartbeat=100))
    runtime = Runtime(corpus.out, job, execute)
    class Tick:
        calls = 0
        def wait(self, interval: float) -> bool:
            assert interval <= 2
            self.calls += 1
            return self.calls > 1
    monkeypatch.setattr(runtime, "done", Tick())
    monkeypatch.setattr(module.time, "time", lambda: 100.5)
    control(corpus.out, "pause")
    # When
    runtime._heartbeat()
    # Then
    assert runtime.job.progress.status == "pausing"
    assert runtime.job.progress.heartbeat == 100.5
    assert runtime.job.progress.stage == "ANALYZE"


def test_disk_full_when_reserve_unavailable_stops_before_stage(corpus: Settings,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    actual = shutil.disk_usage(corpus.input)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: type(actual)(actual.total, actual.total - 1, 1))
    before = snapshot(corpus.input)
    # When / Then
    with pytest.raises(ValueError, match="reserve"):
        run(corpus, Options(analysis=False, reserve_bytes=1))
    assert snapshot(corpus.input) == before
    assert not corpus.out.exists()


def test_revoked_root_when_resumed_is_not_reported_complete(corpus: Settings) -> None:
    # Given
    unavailable = corpus.model_copy(update={"input": corpus.input / "missing"})
    # When / Then
    with pytest.raises(ValueError, match="access"):
        run(unavailable, Options(analysis=False, reserve_bytes=0))
