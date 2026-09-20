"""Synthetic full-content identity regressions; no inference models required."""
import csv
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from artcurator import db
from artcurator.cache import Pass, infer
from artcurator.models import Predictor
from artcurator.scan import inspect


def test_cache_when_prefixes_collide(tmp_path: Path) -> None:
    # Given distinct actual image bytes with deliberately colliding display hints.
    rows = []
    for index, color in enumerate((20, 200)):
        path = tmp_path / f"image-{index}.png"
        Image.new("RGB", (4, 4), (color, 0, 0)).save(path)
        rows.append(inspect(path, tmp_path).model_copy(update={"sha16": "a" * 16}))
    predictor = Predictor("synthetic", "v1", "rgb-v1",
                          lambda images: np.asarray([im.getpixel((0, 0))[0] for im in images]))
    # When the same prefix is used in a real cached inference pass.
    values = infer(rows, Pass(tmp_path, "synthetic", 2, predictor))
    # Then neither deduplication nor cache paths alias the two contents.
    assert values.tolist() == [20, 200]
    assert {p.stem for p in (tmp_path / "cache/predictions").rglob("*.npy")} == {r.sha256 for r in rows}


def test_cache_when_source_changes(tmp_path: Path) -> None:
    # Given a snapshot followed by an external edit.
    path = tmp_path / "image.png"
    Image.new("RGB", (4, 4)).save(path)
    row = inspect(path, tmp_path)
    path.write_bytes(b"changed")
    predictor = Predictor("synthetic", "v1", "rgb-v1", lambda images: np.zeros(len(images)))
    # When evidence is requested; then stale snapshot binding is rejected.
    with pytest.raises(ValueError, match="content"):
        infer([row], Pass(tmp_path, "synthetic", 1, predictor))


def test_gallery_when_legacy_hash_unavailable(tmp_path: Path) -> None:
    # Given a legacy CSV without a full content identity.
    from tools import build_gallery
    path = tmp_path / "scores.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sha16", "proposed_tier"])
        writer.writeheader()
        writer.writerow({"sha16": "a" * 16, "proposed_tier": "review"})
    # When parsed; then missing full SHA is explicit, not a substituted short hash.
    assert build_gallery.read_scores(path)[0].sha256 is None
    assert db.COLUMNS[-1] == "sha256"


def test_cache_when_execution_profile_changes(tmp_path: Path) -> None:
    # Given one content and two execution profiles without a compatibility certificate.
    path = tmp_path / "image.png"
    Image.new("RGB", (4, 4)).save(path)
    rows = [inspect(path, tmp_path)]
    calls = []

    def predict(images):
        calls.append(len(images))
        return np.zeros(len(images))

    predictor = Predictor("stub", "v1", "rgb", predict)
    infer(rows, Pass(tmp_path, "stub", 1, predictor, execution="a" * 64))
    # When a different execution profile requests the same content; then it is a cache miss.
    infer(rows, Pass(tmp_path, "stub", 1, predictor, execution="b" * 64))
    assert calls == [1, 1]


def test_cache_when_payload_corrupted(tmp_path: Path) -> None:
    # Given a published prediction and later corrupted payload bytes.
    path = tmp_path / "image.png"
    Image.new("RGB", (4, 4)).save(path)
    rows = [inspect(path, tmp_path)]
    predictor = Predictor("stub", "v1", "rgb", lambda images: np.zeros(len(images)))
    job = Pass(tmp_path, "stub", 1, predictor)
    infer(rows, job)
    cached = next((tmp_path / "cache/predictions").rglob("*.npy"))
    cached.write_bytes(b"corrupted")
    # When read as a hit; then integrity verification refuses it.
    with pytest.raises(ValueError, match="integrity"):
        infer(rows, job)
