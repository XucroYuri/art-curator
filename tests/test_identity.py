"""Synthetic identity contracts; no corpus or downloaded model is used."""
import importlib
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def test_crop_when_repeated(tmp_path: Path) -> None:
    # Given a canonical RGB image and a full content identity.
    module = importlib.import_module("artcurator.identity_detect")
    image = Image.new("RGB", (120, 90), "red")
    bbox = (5, 6, 60, 30)
    # When cropping twice.
    first = module.crop_bytes(image, bbox)
    second = module.crop_bytes(image, bbox)
    (tmp_path / "crop.jpg").write_bytes(first)
    # Then output bytes and IDs are stable, longest side is 256, metadata absent.
    assert first == second
    expected = "f_" + hashlib.sha256(("a" * 64 + "[5,6,60,30]").encode()).hexdigest()[:8]
    assert module.face_id("a" * 64, bbox) == expected
    with Image.open(tmp_path / "crop.jpg") as crop:
        assert crop.size == (256, 128)
        assert not crop.getexif()
        assert "icc_profile" not in crop.info


def test_cluster_when_separated_with_outlier() -> None:
    # Given two dense groups and one isolated vector.
    module = importlib.import_module("artcurator.identity_cluster")
    schema = importlib.import_module("artcurator.identity_schema")
    vectors = np.array([[1, .01 * i, 0] for i in range(6)] +
                       [[.01 * i, 1, 0] for i in range(6)] + [[0, 0, 1]], dtype=np.float32)
    # When density clustering with a declared radius.
    labels, probabilities = module.cluster_vectors(vectors, schema.IdentityOptions(cluster="dbscan", eps=.05))
    # Then clusters are distinct and the isolated face remains unknown.
    assert len(set(labels) - {-1}) == 2
    assert labels[-1] == -1
    assert probabilities[-1] == 0


def test_cluster_when_empty() -> None:
    # Given an empty face matrix; when clustered; then there are no assignments.
    module = importlib.import_module("artcurator.identity_cluster")
    schema = importlib.import_module("artcurator.identity_schema")
    labels, probabilities = module.cluster_vectors(np.empty((0, 0)), schema.IdentityOptions())
    assert labels.size == probabilities.size == 0


def test_contract_when_fixture_loaded() -> None:
    # Given the frontend fixture; when parsed; then all frozen links resolve.
    module = importlib.import_module("artcurator.identity_schema")
    path = Path(__file__).parent / "fixtures/identity/identities.json"
    document = module.IdentityDocument.model_validate_json(path.read_text(encoding="utf-8"))
    assert document.face_count == 3
    assert document.faces[0].crop_rel == "faces/f_00000001.jpg"


def test_contract_when_nonfinite_rejected() -> None:
    # Given untrusted face data; when parsed; then nonfinite scores fail closed.
    module = importlib.import_module("artcurator.identity_schema")
    with pytest.raises(ValueError):
        module.Face(face_id="f_00000001", image_sha16="a" * 16, bbox=(0, 0, 24, 24),
                    det_score=float("nan"), crop_rel="faces/f_00000001.jpg")


def test_labels_when_unknown_and_confirmed(tmp_path: Path) -> None:
    # Given a valid fixture and matching content-bound label envelope.
    module = importlib.import_module("artcurator.identity_labels")
    schema = importlib.import_module("artcurator.identity_schema")
    fixture = Path(__file__).parent / "fixtures/identity/identities.json"
    document = schema.IdentityDocument.model_validate_json(fixture.read_text(encoding="utf-8"))
    (tmp_path / "identities.json").write_text(document.model_dump_json(), encoding="utf-8")
    provenance = {"corpus_fingerprint": "b" * 64, "semantic_profile": "c" * 64,
                  "contents": {"a" * 16: "a" * 64},
                  "crops": {face.face_id: "d" * 64 for face in document.faces}}
    (tmp_path / "identity-provenance.json").write_text(json.dumps(provenance))
    labels = {"version": 1, "source": "review-studio", "corpus_fingerprint": "b" * 64,
              "labels": [{"face_id": "f_00000001", "image_sha16": "a" * 16,
                          "character": "Character A", "action": "confirm"},
                         {"face_id": "f_ffffffff", "image_sha16": "a" * 16,
                          "character": "Character A", "action": "confirm"}]}
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(labels))
    # When labels are applied.
    result = module.apply_labels(tmp_path, path)
    # Then an unknown face is reported without losing the valid pin.
    assert result.unknown_face_ids == ["f_ffffffff"]
    assert result.faces_changed == 1
    assert result.clusters_changed == 1
    updated = schema.IdentityDocument.model_validate_json(
        (tmp_path / "identities.json").read_text(encoding="utf-8")
    )
    assert updated.clusters[0].confirmed_character == "Character A"
    assert (tmp_path / "characters.json").exists()
