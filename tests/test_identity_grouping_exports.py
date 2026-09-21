"""Disk-bound grouping contract and actual CLI regression scenarios."""
import csv
import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

from artcurator.identity_schema import (ClusteringInfo, DetectorInfo, Face, IdentityDocument,
                                       ImageFaces, ModelInfo, Provenance)
from artcurator.identity_store import file_digest, save_array, save_model


def fixture(out: Path) -> None:
    schema = importlib.import_module("artcurator.identity_group_schema")
    profiles = importlib.import_module("artcurator.identity_profiles")
    faces = [Face(face_id=f"f_{i:08x}", image_sha16="a" * 16, bbox=(i, 0, 24, 24),
                  det_score=.9, crop_rel=f"faces/f_{i:08x}.jpg") for i in range(1, 4)]
    model = ModelInfo(name="siglip", model="synthetic", revision="fixed")
    document = IdentityDocument(detector=DetectorInfo(name="synthetic", model="synthetic", revision="fixed"),
        embedder=model, clustering=ClusteringInfo(), image_count=2, face_count=3, cluster_count=0,
        images=[ImageFaces(sha16="a" * 16, path_rel="query.png", faces=[f.face_id for f in faces]),
                ImageFaces(sha16="b" * 16, path_rel="empty.png", faces=[])], faces=faces, clusters=[])
    save_model(out / "identities.json", document)
    provenance = Provenance(corpus_fingerprint="c" * 64, semantic_profile="d" * 64,
        contents={"a" * 16: "a" * 64, "b" * 16: "b" * 64},
        crops={f.face_id: str(i) * 64 for i, f in enumerate(faces, 1)})
    save_model(out / "identity-provenance.json", provenance)
    save_array(out / "identities.npy", np.eye(3, dtype=np.float16))
    execution = profiles.ExecutionProfile(device="cpu", precision="float32", batch_size=1, runtime={})
    save_model(out / "identity-embedding.json", schema.EmbeddingLedger(model=model,
        preprocess="synthetic", execution=execution, semantic_profile=provenance.semantic_profile,
        sha256=file_digest(out / "identities.npy"), faces=[f.face_id for f in faces]))
    save_array(out / "anchors.npy", np.eye(3, dtype=np.float32)[:2])
    references = [schema.Anchor(character=name, source="folder-derived", source_folder=name,
        image_sha256=str(i) * 64, crop_sha256=str(i) * 64, bbox=(0, 0, 24, 24), det_score=.9, phash="0")
        for i, name in enumerate(("A", "B"), 4)]
    save_model(out / "anchors.json", schema.AnchorDocument(model=model, preprocess="synthetic", execution=execution,
        detector=document.detector, detector_sha256="e" * 64, detector_options={}, licenses={"images": "synthetic"},
        folders={}, excluded_folders=[], anchors=references, matrix_sha256=file_digest(out / "anchors.npy"),
        calibration=schema.Calibration(samples=0, genuine=[], impostor=[], stable_margin=[],
                                       defaults=schema.Thresholds(min_sim=.9, min_margin=.1)), wall_seconds=0))


def test_exports_when_image_has_multiple_characters(tmp_path: Path) -> None:
    # Given A, B and unknown faces in one image, plus a no-face image.
    fixture(tmp_path)
    module = importlib.import_module("artcurator.identity_group")
    options = importlib.import_module("artcurator.identity_schema").IdentityOptions()
    before = file_digest(tmp_path / "identities.json")
    # When producing additive group exports.
    result = module.group(tmp_path, options)
    # Then the frozen JSON and CSV contract preserves many-to-many and abstention.
    assert set(result.model_dump()) == {"version", "provenance", "thresholds", "characters", "abstained"}
    assert [(g.character, g.image_count, g.face_count) for g in result.characters] == [("A", 1, 1), ("B", 1, 1)]
    assert result.abstained.face_count == 1
    assert result.provenance.multi_character_images == 1
    with (tmp_path / "character-groups-by-image.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert set(rows[0]) == {"sha16", "filename", "characters"}
    assert rows[0]["characters"] == "A|B|未知人物"
    assert rows[1]["characters"] == ""
    assert file_digest(tmp_path / "identities.json") == before


def test_integrity_when_anchor_matrix_corrupted(tmp_path: Path) -> None:
    # Given a matrix changed after publication.
    fixture(tmp_path)
    save_array(tmp_path / "anchors.npy", np.ones((2, 3)))
    module = importlib.import_module("artcurator.identity_anchor")
    # When loading; then digest mismatch fails closed.
    with pytest.raises(ValueError, match="digest"):
        module.load_anchors(tmp_path)


def test_confirmations_when_replayed_and_retracted(tmp_path: Path) -> None:
    # Given a content-bound confirmation accepted by the existing learning loop.
    fixture(tmp_path)
    labels = {"version": 1, "source": "review-studio", "corpus_fingerprint": "c" * 64,
              "labels": [{"face_id": "f_00000003", "image_sha16": "a" * 16,
                          "character": "C", "action": "confirm"}]}
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(labels))
    apply = importlib.import_module("artcurator.identity_labels").apply_labels
    apply(tmp_path, path)
    module = importlib.import_module("artcurator.identity_anchor")
    # When the effective retrieval set is rebuilt.
    refs, bank = module.effective_references(tmp_path, *module.load_anchors(tmp_path))
    # Then a confirmed source is added, but an exact self-query remains excluded.
    assert bank.labels == ("A", "B", "C")
    assert refs[-1].source == "human-confirmed"
    assert refs[-1].event_id
    labels["labels"][0]["action"] = "ignore"
    path.write_text(json.dumps(labels))
    apply(tmp_path, path)
    assert module.effective_references(tmp_path, *module.load_anchors(tmp_path))[1].labels == ("A", "B")


def test_cli_when_grouping_saved_vectors() -> None:
    # Given a synthetic output inside the enforced project write boundary.
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(dir=root / ".test-tmp") as directory:
        out = Path(directory)
        fixture(out)
        # When invoking the real CLI (no inference/download required).
        completed = subprocess.run([sys.executable, "-m", "artcurator.cli", "identity-group",
                                    "--config", str(root / "config.example.yaml"), "--out", str(out)],
                                   cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=90)
        # Then public exports exist and stdout did not mask an error.
        assert completed.returncode == 0, completed.stderr
        assert json.loads((out / "character-groups.json").read_text(encoding="utf-8"))["abstained"]["face_count"] == 1


def test_profile_when_execution_mismatched(tmp_path: Path) -> None:
    # Given query vectors from another execution profile.
    fixture(tmp_path)
    path = tmp_path / "identity-embedding.json"
    ledger = json.loads(path.read_text())
    ledger["execution"]["runtime"]["threads"] = "different"
    path.write_text(json.dumps(ledger))
    module = importlib.import_module("artcurator.identity_anchor")
    # When merging references; then cross-profile vectors are rejected.
    with pytest.raises(ValueError, match="profiles"):
        module.effective_references(tmp_path, *module.load_anchors(tmp_path))


def test_labels_when_conflicting_crop_names(tmp_path: Path) -> None:
    # Given a folder crop claimed as two different characters.
    fixture(tmp_path)
    module = importlib.import_module("artcurator.identity_anchor")
    document, values = module.load_anchors(tmp_path)
    conflicting = document.anchors[0].model_copy(update={"character": "C"})
    document = document.model_copy(update={"anchors": [*document.anchors, conflicting]})
    # When merging; then conflicting supervision is excluded instead of tie-broken by text.
    refs, bank = module.effective_references(tmp_path, document, np.vstack([values, values[0]]))
    assert bank.labels == ("B",)
    assert len(refs) == 1


def test_export_when_threshold_override_abstains(tmp_path: Path) -> None:
    # Given explicit conservative thresholds above both margins.
    fixture(tmp_path)
    options = importlib.import_module("artcurator.identity_schema").IdentityOptions(anchor_min_margin=1.1)
    module = importlib.import_module("artcurator.identity_group")
    # When grouping; then overrides are honored and recorded exactly.
    result = module.group(tmp_path, options)
    assert result.abstained.face_count == 3
    assert result.thresholds.min_margin == 1.1


def test_candidates_when_grouping_writes_sidecar(tmp_path: Path) -> None:
    # Given the existing synthetic grouping fixture.
    fixture(tmp_path)
    module = importlib.import_module("artcurator.identity_group")
    options = importlib.import_module("artcurator.identity_schema").IdentityOptions()
    # When grouping reuses saved matrices.
    module.group(tmp_path, options)
    document = importlib.import_module("artcurator.identity_candidates").CandidateDocument.model_validate_json(
        (tmp_path / "identity-candidates.json").read_bytes())
    # Then every face is ranked, suggestions follow existing gates, and CSV matches JSON.
    assert [face.face_id for face in document.faces] == ["f_00000001", "f_00000002", "f_00000003"]
    assert [face.suggested for face in document.faces] == ["A", "B", None]
    assert [face.abstained for face in document.faces] == [False, False, True]
    assert all(len(face.candidates) <= 5 for face in document.faces)
    assert document.faces[0].candidates[0].character == "A"
    assert document.faces[2].suggested is None
    with (tmp_path / "identity-candidates.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["face_id"] for row in rows} == {"f_00000001", "f_00000002", "f_00000003"}
    assert rows[0]["suggested"] == "A"
    assert any(row["face_id"] == "f_00000003" and row["abstained"] == "True" for row in rows)


def test_labels_when_other_and_new_names_apply(tmp_path: Path) -> None:
    # Given the existing review-studio envelope with 其他 and a typed new name.
    fixture(tmp_path)
    labels = {"version": 1, "source": "review-studio", "corpus_fingerprint": "c" * 64,
              "labels": [
                  {"face_id": "f_00000001", "image_sha16": "a" * 16, "character": "其他", "action": "confirm"},
                  {"face_id": "f_00000002", "image_sha16": "a" * 16, "character": "新角色", "action": "new"},
              ]}
    envelope = importlib.import_module("artcurator.identity_schema").LabelEnvelope.model_validate(labels)
    dumped = envelope.model_dump()
    path = tmp_path / "character_labels.json"
    path.write_text(json.dumps(labels), encoding="utf-8")
    # When parsed and applied through identity-apply.
    result = importlib.import_module("artcurator.identity_labels").apply_labels(tmp_path, path)
    # Then required label fields are unchanged and both names are accepted.
    assert set(dumped) == {"version", "source", "corpus_fingerprint", "labels"}
    assert set(dumped["labels"][0]) == {"face_id", "image_sha16", "character", "action"}
    assert result.faces_changed == 2
    registry = json.loads((tmp_path / "characters.json").read_text(encoding="utf-8"))
    assert registry["references"]["f_00000001"] == "其他"
    assert registry["references"]["f_00000002"] == "新角色"


def test_export_when_query_names_are_misleading(tmp_path: Path) -> None:
    # Given identical vectors but filenames suggesting opposite character labels.
    fixture(tmp_path)
    path = tmp_path / "identities.json"
    document = json.loads(path.read_text())
    document["images"][0]["path_rel"] = "B/not-A.png"
    path.write_text(json.dumps(document))
    module = importlib.import_module("artcurator.identity_group")
    options = importlib.import_module("artcurator.identity_schema").IdentityOptions()
    # When using the entire export path; then both known roles still come from pixels.
    result = module.group(tmp_path, options)
    assert [(g.character, g.image_count) for g in result.characters] == [("A", 1), ("B", 1)]
