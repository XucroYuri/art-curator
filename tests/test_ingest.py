"""Synthetic G1 integration contracts; no private corpus paths or model downloads."""
import importlib
import json
from pathlib import Path

import pytest
from PIL import Image

from artcurator.config import Settings
from artcurator.identity_store import file_digest


@pytest.fixture
def corpus(tmp_path: Path) -> Settings:
    root = tmp_path / "source"
    fixture = json.loads((Path(__file__).parent / "fixtures/album-flow.json").read_text())
    for item in fixture["images"]:
        path = root / item["name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if "copy" in item:
            path.write_bytes((root / item["copy"]).read_bytes())
        else:
            Image.new("RGB", tuple(item["size"]), tuple(item["color"])).save(path)
    return Settings(input=root, out=tmp_path / "derived", references=root,
                    posted=root, characters_root=root, workers=1)


def snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns, file_digest(p))
            for p in root.rglob("*") if p.is_file()}


def runner():
    return importlib.import_module("artcurator.ingest")


def options():
    schema = importlib.import_module("artcurator.ingest_schema")
    return schema.Options(analysis=False, reserve_bytes=0)


def test_full_run_when_sources_are_read_only(corpus: Settings) -> None:
    # Given
    before = snapshot(corpus.input)
    # When
    job = runner().run(corpus, options())
    # Then
    assert job.progress.stage == "PROPOSE"
    assert job.progress.status == "complete"
    assert snapshot(corpus.input) == before
    report = json.loads((corpus.out / "revisions" / job.revision / "analysis-report.json").read_bytes())
    assert report["occurrences"] == 3 and report["unique_images"] == 2
    assert report["partial"] is True
    assert report["consent"] is None


def test_replay_when_content_unchanged_does_no_stage_work(corpus: Settings) -> None:
    # Given
    first = runner().run(corpus, options())
    before = snapshot(corpus.out / "revisions")
    # When
    second = runner().run(corpus, options())
    # Then
    assert second.revision == first.revision
    assert snapshot(corpus.out / "revisions") == before
    assert second.progress.cached > 0


def test_delta_when_added_content_scans_only_new_unique_image(corpus: Settings) -> None:
    # Given
    first = runner().run(corpus, options())
    Image.new("RGB", (39, 29), "green").save(corpus.input / "new.png")
    (corpus.input / "duplicate.png").write_bytes((corpus.input / "folder-a/red.png").read_bytes())
    # When
    second = runner().run(corpus, options())
    # Then
    assert first.revision != second.revision
    fresh = [r for r in second.receipts if r.action == "scan" and r.outcome == "completed"]
    assert sum(r.items for r in fresh) == 1
    inventory = json.loads((corpus.out / "revisions" / second.revision / "inventory.json").read_bytes())
    assert set(inventory["added"]) == {"new.png", "duplicate.png"}


def test_resume_when_interrupted_keeps_valid_scan_commits(corpus: Settings) -> None:
    # Given
    module = runner()
    adapters = importlib.import_module("artcurator.ingest_adapters")
    def interrupt(request):
        if request.action == "detect":
            raise RuntimeError("injected interruption")
        return adapters.execute(request)
    with pytest.raises(RuntimeError, match="injected"):
        module.run(corpus, options(), execute=interrupt)
    # When
    resumed = module.run(corpus, options())
    # Then
    assert resumed.progress.status == "complete"
    assert all(r.outcome == "cached" for r in resumed.receipts if r.action == "scan")


def test_delta_when_renamed_changed_deleted_preserves_old_revision(corpus: Settings) -> None:
    # Given
    first = runner().run(corpus, options())
    prior = snapshot(corpus.out / "revisions" / first.revision)
    (corpus.input / "folder-b/blue.png").rename(corpus.input / "renamed.png")
    (corpus.input / "folder-a/red-copy.png").unlink()
    Image.new("RGB", (48, 32), "yellow").save(corpus.input / "folder-a/red.png")
    # When
    result = runner().run(corpus, options())
    # Then
    assert snapshot(corpus.out / "revisions" / first.revision) == prior
    assert sum(r.items for r in result.receipts if r.action == "scan" and r.outcome == "completed") == 1
    inventory = json.loads((corpus.out / "revisions" / result.revision / "inventory.json").read_bytes())
    assert inventory["changed"] == ["folder-a/red.png"]
    assert set(inventory["removed"]) == {"folder-b/blue.png", "folder-a/red-copy.png"}


def test_admission_when_output_overlaps_source_refuses_before_writes(corpus: Settings) -> None:
    # Given
    settings = corpus.model_copy(update={"out": corpus.input / "derived"})
    before = snapshot(corpus.input)
    # When / Then
    with pytest.raises(ValueError, match="overlap"):
        runner().run(settings, options())
    assert snapshot(corpus.input) == before


def test_admission_when_quota_exhausted_does_not_scan(corpus: Settings) -> None:
    # Given
    limited = options().model_copy(update={"quota_bytes": 1})
    # When / Then
    with pytest.raises(ValueError, match="quota"):
        runner().run(corpus, limited)
    assert not (corpus.out / "revisions").exists()


def test_retained_bytes_when_temp_file_vanishes_still_counts_the_rest(tmp_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a heartbeat temp file that disappears between directory listing and stat.
    storage = importlib.import_module("artcurator.ingest_storage")
    (tmp_path / "keep.bin").write_bytes(b"x" * 5)
    (tmp_path / "progress.json.tmp").write_bytes(b"y" * 7)
    real_is_file, real_stat = Path.is_file, Path.stat
    monkeypatch.setattr(Path, "is_file",
                        lambda self: True if self.name.endswith(".tmp") else real_is_file(self))

    def vanished(self, **kwargs):
        if self.name.endswith(".tmp"):
            raise FileNotFoundError(self)
        return real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", vanished)
    # When
    total = storage.retained_bytes(tmp_path)
    # Then: the race is skipped, never a crash or a wrong total.
    assert total == 5


def test_pause_when_requested_saves_exact_checkpoint(corpus: Settings) -> None:
    # Given
    module = runner()
    adapters = importlib.import_module("artcurator.ingest_adapters")
    def pause_after_scan(request):
        result = adapters.execute(request)
        if request.action == "scan":
            module.control(corpus.out, "pause")
        return result
    # When
    job = module.run(corpus, options(), execute=pause_after_scan)
    # Then
    assert job.progress.status == "paused"
    assert job.progress.resume_stage == "INGEST"
    assert job.progress.checkpoint


def test_changed_profile_when_replayed_invalidates_analysis_not_scan(corpus: Settings) -> None:
    # Given
    first = runner().run(corpus, options())
    changed = corpus.model_copy(update={"identity": corpus.identity.model_copy(update={"min_cluster_size": 4})})
    # When
    second = runner().run(changed, options())
    # Then
    assert second.revision != first.revision
    assert all(r.outcome == "cached" for r in second.receipts if r.action == "scan")
