"""Failure, replay and zero-face coverage uses only synthetic temporary state."""
import json
import subprocess
import sys
import importlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from artcurator import db
from artcurator.identity_cluster import cluster_vectors
from artcurator.identity_detect import detect
from artcurator.identity_detector import Detector
from artcurator.identity_labels import apply_labels
from artcurator.identity_schema import DetectorInfo, IdentityOptions
from artcurator.identity_store import file_digest, load_document, load_provenance


def synthetic_manifest(out: Path) -> Path:
    image = out / "source.png"
    Image.new("RGB", (32, 32), "blue").save(image)
    sha = file_digest(image)
    db.save_rows(out, [db.Row(sha16=sha[:16], sha256=sha, abs_path=str(image), path_rel="source.png",
                             filename="source.png", width=32, height=32, filesize=image.stat().st_size,
                             phash="0", mode="RGB")])
    return image


def empty_detector() -> Detector:
    return Detector(DetectorInfo(name="synthetic", model="fixture", revision="v1"), "e" * 64, lambda image: [])


def test_detection_when_no_faces(tmp_path: Path) -> None:
    # Given a valid source and a detector that returns no face.
    synthetic_manifest(tmp_path)
    # When detection completes.
    detect(tmp_path, IdentityOptions(), empty_detector())
    # Then the image stays represented without a fabricated face.
    document = load_document(tmp_path)
    assert document.image_count == 1
    assert document.face_count == 0
    assert document.images[0].faces == []


def test_detection_when_source_missing(tmp_path: Path) -> None:
    # Given an inventoried source that disappears.
    image = synthetic_manifest(tmp_path)
    image.unlink()
    # When detection completes.
    detect(tmp_path, IdentityOptions(), empty_detector())
    # Then missing is explicit and not mistaken for a detector negative.
    status = json.loads((tmp_path / "identity-detection-status.json").read_text())
    assert status["unavailable"][0]["reason"] == "FileNotFoundError"
    assert load_document(tmp_path).image_count == 1


def test_detection_when_source_mutated(tmp_path: Path) -> None:
    # Given changed bytes after the snapshot.
    image = synthetic_manifest(tmp_path)
    Image.new("RGB", (32, 32), "red").save(image)
    # When detection attempts to reuse the manifest; then it fails closed.
    with pytest.raises(ValueError, match="source content changed"):
        detect(tmp_path, IdentityOptions(), empty_detector())


def test_detection_when_profile_changed(tmp_path: Path) -> None:
    # Given a completed profile.
    synthetic_manifest(tmp_path)
    detect(tmp_path, IdentityOptions(), empty_detector())
    # When resuming under different crop admission; then reuse is rejected.
    with pytest.raises(ValueError, match="profile/snapshot changed"):
        detect(tmp_path, IdentityOptions(min_face_px=32), empty_detector())


def test_labels_when_corpus_mismatch(tmp_path: Path) -> None:
    # Given zero-face output and a foreign naming envelope.
    synthetic_manifest(tmp_path)
    detect(tmp_path, IdentityOptions(), empty_detector())
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"version": 1, "source": "review-studio",
                               "corpus_fingerprint": "0" * 64, "labels": []}))
    # When replay is attempted; then no registry is published.
    with pytest.raises(ValueError, match="different corpus"):
        apply_labels(tmp_path, path)
    assert not (tmp_path / "characters.json").exists()


def test_labels_when_unknown_on_empty_corpus(tmp_path: Path) -> None:
    # Given a matching corpus with no detected faces.
    synthetic_manifest(tmp_path)
    detect(tmp_path, IdentityOptions(), empty_detector())
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"version": 1, "source": "review-studio",
        "corpus_fingerprint": load_provenance(tmp_path).corpus_fingerprint,
        "labels": [{"face_id": "f_00000001", "image_sha16": "a" * 16, "character": None, "action": "ignore"}]}))
    # When applying; then unknown references are reported without changing retrieval state.
    result = apply_labels(tmp_path, path)
    assert result.unknown_face_ids == ["f_00000001"]
    assert result.faces_changed == result.clusters_changed == 0


@pytest.mark.parametrize("algorithm", ["hdbscan", "chinese_whispers"])
def test_clustering_when_dense_groups(algorithm: str) -> None:
    # Given independent dense groups with an isolated orthogonal point.
    rng = np.random.default_rng(42)
    values = np.vstack([rng.normal(0, .005, (12, 3)) + [1, 0, 0],
                        rng.normal(0, .005, (12, 3)) + [0, 1, 0], [0, 0, 1]])
    # When clustered; then each dense group shares a label and unknown is rejected.
    labels, probabilities = cluster_vectors(values, IdentityOptions(cluster=algorithm, eps=.05))
    assert len(set(labels[:12])) == len(set(labels[12:24])) == 1
    assert labels[0] != labels[12]
    assert labels[-1] == -1
    assert np.isfinite(probabilities).all()


def test_cli_when_identity_help(tmp_path: Path) -> None:
    # Given the installed CLI; when requesting help; then identity commands are discoverable.
    result = subprocess.run([sys.executable, "-m", "artcurator.cli", "--help"], cwd=tmp_path,
                            check=True, capture_output=True, text=True)
    assert "identity-detect" in result.stdout
    assert "identity-apply" in result.stdout
    assert "--labels" in result.stdout


def test_snapshot_when_legacy_cache_contains_exact_revision(tmp_path: Path) -> None:
    # Given a pre-migration output cache containing the exact incumbent revision.
    module = importlib.import_module("artcurator.identity_embed")
    snapshot = tmp_path / "review/cache/huggingface/hub/models--google--siglip-test/snapshots" / ("a" * 40)
    snapshot.mkdir(parents=True)
    (snapshot / "preprocessor_config.json").write_text("{}")
    (snapshot / "model.safetensors").write_bytes(b"synthetic")
    # When resolving locally; then relocation doesn't cause a download or substitute revision.
    assert module.local_snapshot(tmp_path, "google/siglip-test", "a" * 40) == snapshot


def test_snapshot_when_revision_absent(tmp_path: Path) -> None:
    # Given no matching cached artifact; when resolving; then no model fallback occurs.
    module = importlib.import_module("artcurator.identity_embed")
    with pytest.raises(FileNotFoundError):
        module.local_snapshot(tmp_path, "google/siglip-test", "a" * 40)
