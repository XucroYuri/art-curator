"""Stage cutpoints and fail-closed barriers, scoped G1 AC evidence."""
import json

import pytest
from PIL import Image

from artcurator import ingest
from artcurator.config import Settings
from artcurator.ingest_adapters import Request, Result, execute
from artcurator.ingest_schema import Job, Options
from artcurator.ingest_storage import protect_sources
from test_ingest import corpus as corpus
from test_ingest import snapshot


@pytest.mark.parametrize("action", ["scan", "detect", "embed", "cluster", "anchors", "group", "tag", "candidates"])
def test_resume_when_cut_after_each_stage(corpus: Settings, action: str) -> None:
    # Given: the stage has produced files but its coordinator receipt was not published.
    options = Options(analysis=False, reserve_bytes=0, scan_batch_size=1)
    baseline_settings = corpus.model_copy(update={"out": corpus.out.parent / "baseline"})
    baseline = ingest.run(baseline_settings, options)
    expected = json.loads((baseline_settings.out / "revisions" / baseline.revision / "analysis-report.json").read_bytes())
    def interrupted(request: Request) -> Result:
        result = execute(request)
        if request.action == action:
            raise RuntimeError("cutpoint")
        return result
    with pytest.raises(RuntimeError, match="cutpoint"):
        ingest.run(corpus, options, execute=interrupted)
    # When
    resumed = ingest.run(corpus, options)
    replayed = ingest.run(corpus, options)
    # Then
    assert resumed.progress.status == replayed.progress.status == "complete"
    assert resumed.revision == replayed.revision
    ids = [r.operation_id for r in replayed.receipts]
    assert len(ids) == len(set(ids))
    report = json.loads((corpus.out / "revisions" / resumed.revision / "analysis-report.json").read_bytes())
    assert (report["occurrences"], report["unique_images"], report["mapping_mutations"]) == (3, 2, 0)
    for document in (report, expected):
        document.pop("costs")
    assert report == expected


def test_resume_when_frozen_source_access_revoked_fails_closed(corpus: Settings) -> None:
    # Given
    options = Options(analysis=False, reserve_bytes=0)
    def pause(request: Request) -> Result:
        result = execute(request)
        ingest.control(corpus.out, "pause")
        return result
    ingest.run(corpus, options, execute=pause)
    (corpus.input / "folder-b/blue.png").unlink()
    # When / Then
    with pytest.raises(ValueError, match="unavailable"):
        ingest.run(corpus, options)
    assert Job.model_validate_json((corpus.out / "job.json").read_bytes()).progress.status == "failed"


def test_replay_when_committed_payload_corrupted_refuses(corpus: Settings) -> None:
    # Given
    options = Options(analysis=False, reserve_bytes=0)
    job = ingest.run(corpus, options)
    report = corpus.out / "revisions" / job.revision / "analysis-report.json"
    report.write_text("{}", encoding="utf-8")
    # When / Then
    with pytest.raises(ValueError, match="inconsistent"):
        ingest.run(corpus, options)


def test_cancel_when_scan_settles_retains_committed_artifacts(corpus: Settings) -> None:
    # Given
    before = snapshot(corpus.input)
    def cancel(request: Request) -> Result:
        result = execute(request)
        ingest.control(corpus.out, "cancel")
        return result
    # When
    result = ingest.run(corpus, Options(analysis=False, reserve_bytes=0), execute=cancel)
    # Then
    assert result.progress.status == "cancelled"
    assert list((corpus.out / "content").glob("*.json"))
    assert snapshot(corpus.input) == before


@pytest.mark.parametrize("operation", ["write", "rename", "unlink", "metadata"])
def test_source_write_interception_when_stage_attempts_mutation(corpus: Settings, operation: str) -> None:
    # Given
    source = corpus.input / "folder-b/blue.png"
    before = snapshot(corpus.input)
    # When / Then
    with protect_sources(corpus), pytest.raises(PermissionError):
        match operation:
            case "write":
                source.write_bytes(b"forbidden")
            case "rename":
                source.rename(corpus.out / "stolen.png")
            case "unlink":
                source.unlink()
            case "metadata":
                source.touch()
    assert snapshot(corpus.input) == before


def test_decode_failure_when_invalid_image_is_accounted_without_retry(corpus: Settings) -> None:
    # Given
    (corpus.input / "invalid.png").write_bytes(b"not an image")
    options = Options(analysis=False, reserve_bytes=0)
    # When
    result = ingest.run(corpus, options)
    repeated = ingest.run(corpus, options)
    # Then
    report = json.loads((corpus.out / "revisions" / result.revision / "analysis-report.json").read_bytes())
    assert len(report["decode_failed"]) == 1
    assert report["occurrences"] == 4
    assert repeated.revision == result.revision


def test_content_change_when_size_and_mtime_unchanged_is_detected(corpus: Settings) -> None:
    # Given
    import os
    options = Options(analysis=False, reserve_bytes=0)
    first = ingest.run(corpus, options)
    path = corpus.input / "folder-b/blue.png"
    stat = path.stat()
    original = path.read_bytes()
    # Changed opaque bytes with exactly the same metadata, even if decode is now rejected.
    path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    # When
    second = ingest.run(corpus, options)
    # Then
    assert second.revision != first.revision


def test_paused_snapshot_when_new_file_added_defers_new_member(corpus: Settings) -> None:
    # Given
    options = Options(analysis=False, reserve_bytes=0)
    def pause(request: Request) -> Result:
        result = execute(request)
        ingest.control(corpus.out, "pause")
        return result
    ingest.run(corpus, options, execute=pause)
    Image.new("RGB", (20, 20), "green").save(corpus.input / "late.png")
    # When
    resumed = ingest.run(corpus, options)
    # Then
    report = json.loads((corpus.out / "revisions" / resumed.revision / "analysis-report.json").read_bytes())
    assert report["occurrences"] == 3


def test_failed_action_when_exception_is_metered(corpus: Settings) -> None:
    # Given
    def fail(request: Request) -> Result:
        raise RuntimeError("stage failure")
    # When
    with pytest.raises(RuntimeError, match="stage failure"):
        ingest.run(corpus, Options(analysis=False, reserve_bytes=0), execute=fail)
    # Then
    job = Job.model_validate_json((corpus.out / "job.json").read_bytes())
    failures = [r for r in job.receipts if r.outcome == "failed"]
    assert len(failures) == 1
    assert failures[0].wall_seconds >= 0
    assert failures[0].gpu_active_seconds is None


def test_scan_profile_change_when_cached_invalidates_scan(corpus: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    from artcurator import ingest_catalog
    ingest.run(corpus, Options(analysis=False, reserve_bytes=0))
    entry = next((corpus.out / "content").glob("*.json"))
    sha = entry.stem
    # When
    monkeypatch.setattr(ingest_catalog, "scan_profile", lambda: "changed-render-profile")
    # Then
    assert ingest_catalog.lookup(corpus.out, sha) is None


def test_resume_when_ingest_barrier_payload_changed_refuses(corpus: Settings) -> None:
    # Given
    from artcurator import db
    options = Options(analysis=False, reserve_bytes=0)
    def interrupt(request: Request) -> Result:
        if request.action == "detect":
            raise RuntimeError("cutpoint")
        return execute(request)
    with pytest.raises(RuntimeError):
        ingest.run(corpus, options, execute=interrupt)
    job = Job.model_validate_json((corpus.out / "job.json").read_bytes())
    db.meta(corpus.out / "revisions" / job.revision, "uncommitted-change", "injected")
    # When / Then
    with pytest.raises(ValueError, match="barrier"):
        ingest.run(corpus, options)
