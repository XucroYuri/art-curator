"""Deterministic, source-in-place bounded ingestion, including the real CLI."""
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from PIL import Image

from artcurator import db
from artcurator.config import ROOT, Settings
from artcurator.ingest import run
from artcurator.ingest_adapters import Request, Result, execute
from artcurator.ingest_inventory import discover
from artcurator.ingest_runtime import control
from artcurator.ingest_schema import Inventory, Job, Options
from test_ingest import corpus as corpus
from test_ingest import snapshot


def test_selection_when_discovery_order_varies_is_lexical(corpus: Settings,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    # Given reverse traversal and a corrupt file outside the selected prefix.
    import artcurator.ingest_inventory as module
    (corpus.input / "z-broken.png").write_bytes(b"not an image")
    paths = list(reversed(sorted(corpus.input.rglob("*.png"))))
    monkeypatch.setattr(module, "image_paths", lambda root: paths)
    hashed: list[Path] = []
    original = module.file_digest

    def track(path: Path) -> str:
        hashed.append(path)
        return original(path)

    monkeypatch.setattr(module, "file_digest", track)
    # When selecting before source hashing/decoding.
    records = discover(corpus.input, lambda count: None, sample=2)
    # Then exact case-sensitive POSIX-relative ordering, occurrences not unique hashes.
    assert [r.path for r in records] == ["folder-a/red-copy.png", "folder-a/red.png"]
    assert len(hashed) == 2


def test_selection_when_replayed_preserves_sources_and_sealed_artifacts(corpus: Settings) -> None:
    # Given a sampled completed run.
    options = Options(analysis=False, reserve_bytes=0, sample=2)
    before = snapshot(corpus.input)
    first = run(corpus, options)
    artifacts = snapshot(corpus.out / "revisions")
    # When replayed.
    replay = run(corpus, options)
    # Then locators still refer to originals and selection is frozen in the sealed snapshot.
    revision = corpus.out / "revisions" / replay.revision
    inventory = Inventory.model_validate_json((revision / "snapshot.json").read_bytes())
    assert inventory.selected_paths == ("folder-a/red-copy.png", "folder-a/red.png")
    assert all(Path(row.abs_path).is_relative_to(corpus.input) for row in db.load_rows(revision))
    assert replay.revision == first.revision
    assert snapshot(corpus.out / "revisions") == artifacts
    assert snapshot(corpus.input) == before


def test_selection_when_resuming_ignores_new_files(corpus: Settings) -> None:
    # Given a paused sampled run, followed by a newly added lexically earlier file.
    options = Options(analysis=False, reserve_bytes=0, sample=2)

    def pause(request: Request) -> Result:
        result = execute(request)
        if request.action == "scan":
            control(corpus.out, "pause")
        return result

    first = run(corpus, options, execute=pause)
    Image.new("RGB", (9, 7), "green").save(corpus.input / "a.png")
    # When resuming the same options.
    resumed = run(corpus, options)
    # Then only the frozen selection is completed.
    assert resumed.revision == first.revision
    assert resumed.progress.status == "complete"
    inventory = Inventory.model_validate_json((corpus.out / "revisions" / resumed.revision / "snapshot.json").read_bytes())
    assert inventory.selected_paths == ("folder-a/red-copy.png", "folder-a/red.png")


def test_selection_when_completed_run_gets_delta_reselects_and_reuses(corpus: Settings) -> None:
    # Given a completed sample and a new image sorting before that sample.
    options = Options(analysis=False, reserve_bytes=0, sample=2)
    first = run(corpus, options)
    Image.new("RGB", (9, 7), "green").save(corpus.input / "a.png")
    # When a new incremental invocation selects its prefix.
    delta = run(corpus, options)
    # Then the new snapshot distinguishes deselected history from selected members.
    inventory = Inventory.model_validate_json((corpus.out / "revisions" / delta.revision / "snapshot.json").read_bytes())
    assert delta.revision != first.revision
    assert inventory.selected_paths == ("a.png", "folder-a/red-copy.png")
    assert inventory.removed == ("folder-a/red.png",)
    assert sum(r.items for r in delta.receipts if r.action == "scan" and r.outcome == "completed") == 1


@pytest.mark.parametrize("flag", ["--sample", "--limit"])
def test_cli_when_sampling_records_selection_in_place(corpus: Settings, flag: str) -> None:
    # Given original sources and a unique CLI output root.
    name = "test-sample-" + uuid.uuid4().hex
    before = snapshot(corpus.input)
    # When using the actual CLI, subprocess adapters and default concurrency.
    result = subprocess.run([sys.executable, "-m", "artcurator.cli", "ingest-run", "--input",
        str(corpus.input), "--corpus", name, "--inventory-only", "--reserve-gib", "0", flag, "1"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)
    # Then only one original occurrence is included, with durable selection evidence.
    assert result.returncode == 0, result.stderr
    root = ROOT / "out" / "ingest" / name
    job = Job.model_validate_json((root / "job.json").read_bytes())
    inventory = Inventory.model_validate_json((root / "revisions" / job.revision / "snapshot.json").read_bytes())
    assert inventory.selected_paths == ("folder-a/red-copy.png",)
    assert snapshot(corpus.input) == before
    assert json.loads((root / "launch.json").read_bytes())["options"]["sample"] == 1


@pytest.mark.parametrize("arguments", [["--sample", "0"], ["--sample", "-1"], ["--limit", "0"],
                                       ["--sample", "1", "--limit", "2"]])
def test_cli_when_selector_invalid_fails_before_writes(arguments: list[str], corpus: Settings) -> None:
    # Given invalid or conflicting selection bounds.
    name = "test-invalid-sample-" + uuid.uuid4().hex
    # When parsing the command.
    result = subprocess.run([sys.executable, "-m", "artcurator.cli", "ingest-run", "--corpus", name,
                             "--input", str(corpus.input), "--inventory-only",
                             *arguments], cwd=ROOT, capture_output=True, timeout=20)
    # Then usage failure leaves no output root.
    assert result.returncode == 2
    assert not (ROOT / "out" / "ingest" / name).exists()
