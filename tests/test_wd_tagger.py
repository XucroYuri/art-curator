"""Compact WD evidence and versioned exchange contracts."""
import importlib
import json
from pathlib import Path

import numpy as np

from artcurator.wd_schema import PINS, Evidence, Handshake, Tag, TagDocument, TaggedFace


def test_compact_when_scores_include_many_characters() -> None:
    # Given six characters, an attribute and a rating (never an attribute).
    module = importlib.import_module("artcurator.wd_worker")
    tags = [(f"hero_{i}", 4) for i in range(6)] + [("black_hair", 0), ("general", 9)]
    # When selecting evidence; then keep only five characters and general tags.
    result = module.compact(np.array([.9, .8, .7, .6, .5, .4, .95, .99]), tags)
    assert len(result.characters) == 5
    assert [row.tag for row in result.attributes.tags] == ["black_hair"]
    assert result.attributes.hair_color == "black"


def test_compact_when_threshold_is_exact() -> None:
    # Given a score exactly on the strict character threshold.
    module = importlib.import_module("artcurator.wd_worker")
    # When reducing; then never invent a candidate at or below .35.
    result = module.compact(np.array([.35]), [("hero", 4)])
    assert result.characters == []


def test_document_when_saved_before_anchor_field_parses(tmp_path: Path) -> None:
    # Given bytes from a wd-tagger.json written before reference-anchor evidence existed.
    current = TagDocument(
        handshake=Handshake(build="a" * 64, model_sha256="b" * 64, tags_sha256="c" * 64, packages={}),
        corpus_fingerprint="d" * 64, faces=[TaggedFace(face_id="f_00000001", image_sha16="e" * 16,
            crop_sha256="f" * 64, evidence=Evidence(characters=[Tag(tag="hero", score=.9)]))])
    legacy = json.loads(current.model_dump_json())
    del legacy["anchors"]
    path = tmp_path / "wd-tagger.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    # When parsing the old document; then face evidence is unchanged and anchors default empty.
    parsed = TagDocument.model_validate_json(path.read_bytes())
    assert parsed.faces == current.faces
    assert parsed.anchors == []
