"""Compact WD evidence and versioned exchange contracts."""
import importlib

import numpy as np


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
