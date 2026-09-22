"""Reservation contention and per-image deferral regression contracts."""
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from artcurator import db
from artcurator.config import Settings
from artcurator.ingest import run
from artcurator.ingest_schema import Options
from artcurator.resources import ByteBudget
from artcurator.scan import scan
from test_ingest import corpus as corpus


def test_admission_when_real_preview_reservations_contend(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the exact real-library occupied/request/cap values, without allocating pixels.
    budget = ByteBudget(536_870_912)
    waiting = Event()
    acquired = Event()
    original_wait = budget.condition.wait

    def observe_wait(timeout: float | None = None) -> bool:
        waiting.set()
        return original_wait(timeout)

    monkeypatch.setattr(budget.condition, "wait", observe_wait)

    def reserve_next() -> None:
        with budget.reserve(63_150_692):
            acquired.set()
            assert budget.used <= budget.cap

    # When two requests arrive while the first reservation occupies the budget.
    with ThreadPoolExecutor(max_workers=2) as pool:
        with budget.reserve(496_532_476):
            first = pool.submit(reserve_next)
            second = pool.submit(reserve_next)
            assert waiting.wait(2), "admissible request rejected instead of queued"
            assert not acquired.is_set()
            assert budget.used == 496_532_476
        first.result(timeout=2)
        second.result(timeout=2)
    # Then both requests complete, no overcommit or false deferral remains.
    assert acquired.is_set()
    assert budget.used == 0
    assert budget.peak <= budget.cap
    assert budget.events == []


def test_release_when_consumer_raises() -> None:
    # Given an admitted reservation.
    budget = ByteBudget(100)
    # When its consumer fails.
    with pytest.raises(OSError), budget.reserve(100):
        raise OSError("synthetic consumer failure")
    # Then capacity is returned.
    assert budget.used == 0


def test_previews_when_one_image_cannot_fit_continue_and_report(corpus: Settings,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    # Given two decoded unique images and a cap smaller than one preview request.
    module = importlib.import_module("artcurator.previews")
    corpus.out.mkdir()
    scan(corpus, None)
    budget = ByteBudget(100)
    monkeypatch.setattr(module, "ByteBudget", lambda cap: budget)
    monkeypatch.setattr(module, "decode_estimate", lambda path: 101 if path.name == "blue.png" else 60)
    # When previews process the batch.
    result = module.previews(corpus.model_copy(update={"workers": 8}))
    # Then the other image is generated, the oversized image is recorded, not fatal.
    assert result.generated == 1
    timing = json.loads((corpus.out / "previews-timing.json").read_bytes())
    assert timing["deferred"] == 1
    rejected = json.loads((corpus.out / "previews-rejected.json").read_bytes())
    assert len(rejected) == 1 and rejected[0]["sha256"] in {r.sha256 for r in db.load_rows(corpus.out)}
    assert budget.used == 0


def test_ingestion_when_entire_scan_batch_is_oversized_continues(corpus: Settings,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a first batch that cannot fit alone, followed by an admissible image.
    module = importlib.import_module("artcurator.scan")
    monkeypatch.setattr(module, "decode_estimate", lambda path: 2**40 if "red" in path.name else 60)
    # When inventory ingestion uses single-item batches.
    job = run(corpus, Options(analysis=False, reserve_bytes=0, scan_batch_size=1))
    # Then no failed image aborts the run; report retains failed content identities.
    assert job.progress.status == "complete"
    report = json.loads((corpus.out / "revisions" / job.revision / "analysis-report.json").read_bytes())
    assert len(report["decode_failed"]) == 1
    assert len(db.load_rows(corpus.out / "revisions" / job.revision)) == 1
