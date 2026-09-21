"""Synthetic candidates v2 and curated visual-memory regressions."""
import importlib
import json
from pathlib import Path

import pytest

from test_identity_grouping_exports import fixture


def test_merge_when_sources_share_name() -> None:
    # Given model and memory evidence for one identity.
    module = importlib.import_module("artcurator.identity_candidates_v2")
    model = [module.Option(name="hero", display="hero", source="model", score=.9)]
    memory = [module.Option(name="hero", display="hero", source="memory", score=.8)]
    # When sources are merged; then neither score is lost and actions remain last.
    rows = module.merge_options(model, memory)
    assert rows[0].score_model == .9
    assert rows[0].score_memory == .8
    assert [row.name for row in rows[-2:]] == ["其他", "新建角色"]
    assert len({row.name for row in rows}) == len(rows)


def test_zero_reference_when_emitting(tmp_path: Path) -> None:
    # Given saved query vectors but no reference anchors or WD output.
    fixture(tmp_path)
    (tmp_path / "anchors.json").unlink()
    module = importlib.import_module("artcurator.identity_candidates_v2")
    # When emitting; then startup requires no named references and abstains honestly.
    result = module.emit(tmp_path)
    assert result.version == 2.1
    assert all(face.abstained and face.suggested is None for face in result.faces)
    assert all([row.name for row in face.candidates][-2:] == ["其他", "新建角色"] for face in result.faces)
    assert result.sources.model.closed_set_size == 2751


@pytest.mark.parametrize("mark", ["baseline", "variant"])
def test_mark_when_journal_round_trips(tmp_path: Path, mark: str) -> None:
    # Given a marked confirmation.
    fixture(tmp_path)
    labels = {"version": 1, "source": "review-studio", "corpus_fingerprint": "c" * 64,
              "labels": [{"face_id": "f_00000001", "image_sha16": "a" * 16,
                          "character": "hero", "action": "confirm", "mark": mark}]}
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(labels), encoding="utf-8")
    module = importlib.import_module("artcurator.identity_labels")
    # When applying; then mark survives the hash chain and strengthens memory.
    module.apply_labels(tmp_path, path)
    assert module.load_registry(tmp_path).events[-1].label.mark == mark
    memory = importlib.import_module("artcurator.character_memory").load_memory(tmp_path)
    char = memory.characters[0]
    assert char.assigned_faces == ["f_00000001"]
    assert (char.baseline_faces == ["f_00000001"]) == (mark == "baseline")
    assert bool(char.variant_faces) == (mark == "variant")


def test_curation_when_merging_reassigns_visual_memory(tmp_path: Path) -> None:
    # Given two user identities with separate faces and baseline markings.
    fixture(tmp_path)
    labels = {"version": 1, "source": "review-studio", "corpus_fingerprint": "c" * 64,
              "labels": [{"face_id": f"f_{i:08x}", "image_sha16": "a" * 16,
                          "character": name, "action": "confirm", "mark": "baseline"}
                         for i, name in enumerate(("hero", "alias"), 1)]}
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(labels), encoding="utf-8")
    labels_module = importlib.import_module("artcurator.identity_labels")
    labels_module.apply_labels(tmp_path, path)
    module = importlib.import_module("artcurator.character_memory")
    # When merging; then historical events remain valid and current attribution moves.
    module.curate(tmp_path, "merge", "alias", "hero")
    memory = module.load_memory(tmp_path)
    assert len(memory.characters) == 1
    assert set(memory.characters[0].baseline_faces) == {"f_00000001", "f_00000002"}
    assert set(labels_module.load_registry(tmp_path).references.values()) == {"hero"}


@pytest.mark.parametrize("mark", ["invalid", 3])
def test_mark_when_invalid_rejected(mark: str | int) -> None:
    # Given an invalid optional mark; when parsing; then reject before persistence.
    from artcurator.identity_schema import Label
    with pytest.raises(ValueError):
        Label.model_validate({"face_id": "f_00000001", "image_sha16": "a" * 16,
                              "character": "hero", "action": "confirm", "mark": mark})


def seed_memory(out: Path) -> None:
    from artcurator.identity_labels import apply_labels
    fixture(out)
    path = out / "labels.json"
    path.write_text(json.dumps({"version": 1, "source": "review-studio", "corpus_fingerprint": "c" * 64,
        "labels": [{"face_id": "f_00000001", "image_sha16": "a" * 16, "character": "hero",
                    "action": "confirm", "mark": "baseline"}]}), encoding="utf-8")
    apply_labels(out, path)


def test_rename_when_visual_support_exists(tmp_path: Path) -> None:
    # Given a marked identity; when renamed; then references and assignments move together.
    seed_memory(tmp_path)
    from artcurator.character_memory import curate
    from artcurator.identity_labels import load_registry
    result = curate(tmp_path, "rename", "hero", "renamed")
    assert result.characters[0].name == "renamed"
    assert result.characters[0].aliases == ["hero"]
    assert result.characters[0].baseline_faces == ["f_00000001"]
    assert load_registry(tmp_path).references == {"f_00000001": "renamed"}


def test_delete_when_assigned(tmp_path: Path) -> None:
    # Given a named face; when deleting its memory; then no stale visual reference remains.
    seed_memory(tmp_path)
    from artcurator.character_memory import curate
    from artcurator.identity_labels import load_registry
    result = curate(tmp_path, "delete", "hero")
    assert result.characters == []
    assert load_registry(tmp_path).references == {}


def test_export_import_when_same_corpus(tmp_path: Path) -> None:
    # Given a content-bound export; when importing it; then marks/aliases round-trip.
    seed_memory(tmp_path)
    from artcurator.memory_curation import export_memory, import_memory
    from artcurator.character_memory import load_memory
    path = tmp_path / "export.json"
    export_memory(tmp_path, path)
    before = load_memory(tmp_path)
    result = import_memory(tmp_path, path)
    assert result.characters[0].baseline_faces == before.characters[0].baseline_faces
    assert result.characters[0].assigned_faces == before.characters[0].assigned_faces


def test_import_when_foreign_faces_rejected(tmp_path: Path) -> None:
    # Given a foreign face reference; when importing; then current state stays intact.
    seed_memory(tmp_path)
    from artcurator.memory_curation import import_memory
    before = (tmp_path / "character-memory.json").read_bytes()
    path = tmp_path / "import.json"
    path.write_text(json.dumps({"version": 1, "characters": [{"name": "foreign", "assigned_faces": ["f_ffffffff"]}]}))
    with pytest.raises(ValueError, match="unresolved"):
        import_memory(tmp_path, path)
    assert (tmp_path / "character-memory.json").read_bytes() == before


def test_mark_only_when_assignment_unchanged(tmp_path: Path) -> None:
    # Given baseline assignment; when changed to variant; then the mark creates an event.
    seed_memory(tmp_path)
    from artcurator.identity_labels import apply_labels, load_registry
    from artcurator.character_memory import load_memory
    path = tmp_path / "labels.json"
    raw = json.loads(path.read_text())
    raw["labels"][0]["mark"] = "variant"
    path.write_text(json.dumps(raw))
    apply_labels(tmp_path, path)
    assert len(load_registry(tmp_path).events) == 2
    assert load_memory(tmp_path).characters[0].baseline_faces == []
    assert load_memory(tmp_path).characters[0].variant_faces[0].face_id == "f_00000001"


def test_memory_similarity_when_saved_vector_matches(tmp_path: Path) -> None:
    # Given one reference and another query with its same visual embedding but different crop.
    seed_memory(tmp_path)
    import numpy as np
    from artcurator.identity_candidates_v2 import emit
    from artcurator.identity_store import file_digest, save_array
    save_array(tmp_path / "identities.npy", np.array([[1, 0, 0], [1, 0, 0], [0, 0, 1]], dtype=np.float16))
    ledger_path = tmp_path / "identity-embedding.json"
    ledger = json.loads(ledger_path.read_text())
    ledger["sha256"] = file_digest(tmp_path / "identities.npy")
    ledger_path.write_text(json.dumps(ledger))
    # When emitting; then query gets cosine support, exact self gets none, singleton abstains.
    result = emit(tmp_path)
    assert not any(c.source == "memory" for c in result.faces[0].candidates)
    assert result.faces[1].candidates[0].score == pytest.approx(1)
    assert result.faces[1].candidates[0].source == "memory"
    assert result.faces[1].abstained


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1.1])
def test_v2_when_invalid_score(value: float) -> None:
    # Given nonfinite/out-of-range evidence; when parsing; then reject it.
    from artcurator.candidates_schema_v2 import Option
    with pytest.raises(ValueError):
        Option(name="hero", source="model", score=value)


def test_v2_when_bucket_missing() -> None:
    # Given a malformed list; when parsing; then reject missing final actions.
    from artcurator.candidates_schema_v2 import FaceOptions
    with pytest.raises(ValueError, match="bucket/action"):
        FaceOptions(face_id="f_00000001", image_sha16="a" * 16, candidates=[])


def test_cli_when_memory_rename_requested() -> None:
    # Given a synthetic corpus within the write boundary.
    import subprocess
    import sys
    import tempfile
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(dir=root / ".test-tmp") as directory:
        out = Path(directory)
        seed_memory(out)
        # When invoking actual CLI; then the canonical namespace is changed.
        result = subprocess.run([sys.executable, "-m", "artcurator.cli", "character-memory",
            "--out", str(out), "--config", str(root / "config.example.yaml"),
            "--memory-op", "rename", "--name", "hero", "--target", "new-name"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=90)
        assert result.returncode == 0, result.stderr
        assert json.loads((out / "character-memory.json").read_text())["characters"][0]["name"] == "new-name"
