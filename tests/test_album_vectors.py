"""Saved evidence adapter and representative selection reuse, without model execution."""
import hashlib
import json
from pathlib import Path

import numpy as np

from artcurator.album_map_exchange import Manifest, ManifestMember
from artcurator.album_map_vectors import SavedVectors, Wall, representative_wall, saved_vectors
from artcurator.identity_schema import IdentityOptions
from artcurator.identity_store import file_digest
from test_album_discovery_lineage import inputs


def test_wall_uses_full_hash_tie_break_when_legacy_alias_order_is_reversed() -> None:
    # Given equal vectors, fifteen distinct images and deliberately reversed aliases.
    members = tuple(v.model_copy(update={"legacy_id": str(100 - i)}) for i, v in enumerate(inputs(15).vectors))
    # When sampling, then the lowest full content hash wins and cap twelve is respected.
    wall = representative_wall(Wall(members=members))
    assert wall.representatives[0] == "100"
    assert len(wall.representatives) == 12
    assert wall.members == members


def test_saved_vectors_use_integrity_loader_when_manifest_is_bound(tmp_path: Path) -> None:
    # Given a real saved float16 embedding, document, ledger and provenance.
    image = hashlib.sha256(b"synthetic image").hexdigest()
    crop = hashlib.sha256(b"synthetic crop").hexdigest()
    face = "f_00000001"
    model = {"name": "analytic", "model": "fixture", "revision": "v1"}
    document = {"detector": model, "embedder": model, "clustering": {}, "image_count": 1,
        "face_count": 1, "cluster_count": 0, "images": [{"sha16": image[:16], "path_rel": "not-opened",
        "faces": [face]}], "faces": [{"face_id": face, "image_sha16": image[:16], "bbox": [0, 0, 20, 20],
        "det_score": 1., "crop_rel": f"faces/{face}.jpg"}], "clusters": []}
    (tmp_path / "identities.json").write_text(json.dumps(document), encoding="utf-8")
    (tmp_path / "identity-provenance.json").write_text(json.dumps({"corpus_fingerprint": "d" * 64,
        "semantic_profile": "c" * 64, "contents": {image[:16]: image}, "crops": {face: crop}}), encoding="utf-8")
    np.save(tmp_path / "identities.npy", np.asarray([[3., 4.]], dtype=np.float16), allow_pickle=False)
    (tmp_path / "identity-embedding.json").write_text(json.dumps({"faces": [face],
        "sha256": file_digest(tmp_path / "identities.npy"), "semantic_profile": "c" * 64}), encoding="utf-8")
    manifest = Manifest(members=(ManifestMember(legacy_id=face, image_id=image, subject_id=face,
        crop_id=crop, profile="c" * 64),))
    # When adapting, then the existing loader verifies and normalizes the actual saved bytes.
    result = saved_vectors(SavedVectors(directory=tmp_path, manifest=manifest, options=IdentityOptions()))
    assert np.allclose(result.vectors[0].vector, (.6, .8))
    assert result.vectors[0].image_id == image
