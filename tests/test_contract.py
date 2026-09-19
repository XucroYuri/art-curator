"""Given/when/then contracts independent of downloaded models."""
import importlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, PngImagePlugin


def test_zscore_when_constant() -> None:
    # Given constant scores; when standardized; then finite zeroes.
    module = importlib.import_module("artcurator.cluster")
    assert np.array_equal(module.zscore(np.array([2.0, 2.0])), [0.0, 0.0])


def test_pixels_when_metadata_differs(tmp_path: Path) -> None:
    # Given identical pixels with different ancillary text.
    module = importlib.import_module("artcurator.scan")
    paths = [tmp_path / "one.png", tmp_path / "two.png"]
    for path, text in zip(paths, ["red", "blue"], strict=True):
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("prompt", text)
        Image.new("RGB", (32, 48), (80, 10, 25)).save(path, pnginfo=metadata)
    # When decoded through the pixel-only boundary.
    images = [module.pixels(path) for path in paths]
    # Then text cannot affect pixels or survive the decoder boundary.
    assert images[0].tobytes() == images[1].tobytes()


def test_family_when_transitive() -> None:
    # Given distances 6, 6, 12, with no cosine absorption.
    module = importlib.import_module("artcurator.cluster")
    hashes = [0, 63, 4095]
    # When union-find clustering; then the bridge connects all three.
    assert module.components(hashes, np.eye(3)) == [[0, 1, 2]]


def test_outputs_when_outside_project(tmp_path: Path) -> None:
    # Given an external destination; when checked; then it is rejected.
    module = importlib.import_module("artcurator.config")
    with pytest.raises(ValueError):
        module.output_path(module.ROOT.parent / "forbidden")


def test_csv_when_contract_loaded() -> None:
    # Given the frozen consumer contract; when loaded; then exact ordering.
    module = importlib.import_module("artcurator.db")
    assert ",".join(module.COLUMNS) == (
        "sha16,abs_path,path_rel,filename,width,height,filesize,phash,family_id,"
        "aes_v25,topiq_iaa,topiq_nr,qrealign,nsfw_prob,identity_sim,confusable_margin,novelty,"
        "consensus_z,disagreement,gaming_delta,flags,proposed_tier,thumb_rel"
    )
