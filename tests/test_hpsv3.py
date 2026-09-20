"""HPSv3 schema, equal-weight consensus and native uncertainty contracts."""
from pathlib import Path

import numpy as np
import pytest

from artcurator import db
from artcurator.cluster import cluster, zscore
from artcurator.config import Settings
from test_conservative import prepare as prepare_legacy


def prepare(root: Path) -> Settings:
    return prepare_legacy(root).model_copy(update={"quality_profile": "five-means-v1"})


def test_columns_when_hpsv3_added() -> None:
    # Given the frozen existing column order.
    start = db.COLUMNS.index("qrealign")
    # When selecting the additive scorer columns.
    actual = db.COLUMNS[start:start + 4]
    # Then both outputs precede safety without moving existing columns.
    assert actual == ("qrealign", "hpsv3_mu", "hpsv3_sigma", "nsfw_prob")


def test_consensus_when_five_scores_disagree(tmp_path: Path) -> None:
    # Given four increasing scorers and an independently varying fifth scorer.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    fifth = np.asarray([float((i * 7) % 21) for i in range(21)])
    for i, row in enumerate(rows):
        row.hpsv3_mu = float(fifth[i])
        row.hpsv3_sigma = 0.0
    db.save_rows(tmp_path, rows)
    expected = zscore((4 * zscore(np.arange(21.0)) + zscore(fifth)) / 5)
    # When recomputing consensus.
    cluster(settings)
    # Then each scorer contributes exactly one fifth before final standardization.
    assert [row.consensus_z for row in db.load_rows(tmp_path)] == pytest.approx(expected)


def test_uncertainty_when_native_sigma_present(tmp_path: Path) -> None:
    # Given identical standardized means and sigma equal to HPS population SD.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    for i, row in enumerate(rows):
        row.hpsv3_mu = float(i)
        row.hpsv3_sigma = float(np.arange(21.0).std())
    db.save_rows(tmp_path, rows)
    # When combining between-scorer variance with native within-scorer variance.
    cluster(settings)
    # Then sigma contributes once, with the HPS mixture weight 1/5, not as a sixth vote.
    assert [row.disagreement for row in db.load_rows(tmp_path)] == pytest.approx([np.sqrt(0.2)] * 21)


def test_sigma_when_negative_rejected() -> None:
    # Given serialized invalid native standard deviation.
    data = dict(sha16="0" * 16, sha256="0" * 64, abs_path="unused", path_rel="unused",
                filename="unused", width=1, height=1, filesize=1, phash="0", mode="RGB", hpsv3_sigma=-1)
    # When parsing the disk boundary, then negative standard deviation is invalid.
    with pytest.raises(ValueError):
        db.Row.model_validate(data)


def test_cluster_when_hpsv3_partially_scored(tmp_path: Path) -> None:
    # Given one completed pair in an otherwise legacy manifest.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    rows[0].hpsv3_mu, rows[0].hpsv3_sigma = 3.0, 0.1
    db.save_rows(tmp_path, rows)
    # When clustering, then partial evidence widens abstention across the cohort.
    cluster(settings)
    results = db.load_rows(tmp_path)
    assert all(row.proposed_tier == "review" and row.consensus_z is None for row in results)
    assert "signal_unavailable:hpsv3_mu" in results[1].flags


def test_uncertainty_when_hpsv3_constant(tmp_path: Path) -> None:
    # Given an unidentifiable HPS scale, with nonzero native sigma.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    for row in rows:
        row.hpsv3_mu, row.hpsv3_sigma = 5.0, 2.0
    db.save_rows(tmp_path, rows)
    expected = np.std(np.column_stack([zscore(np.arange(21.0))] * 4 + [np.zeros(21)]), axis=1)
    # When clustered, then the zero-scale native term is omitted rather than dividing by zero.
    cluster(settings)
    assert [row.disagreement for row in db.load_rows(tmp_path)] == pytest.approx(expected)


def test_gallery_when_hpsv3_columns_present(tmp_path: Path) -> None:
    from tools import build_gallery
    from test_build_gallery import _write_scores_csv

    # Given the real extended CSV header with updated downstream aggregates.
    path = tmp_path / "scores.csv"
    _write_scores_csv(path, db.COLUMNS, hpsv3_mu="5.25", hpsv3_sigma="0.03",
                      consensus_z="1.4", disagreement="1.3", flags="uncertain", proposed_tier="review")
    # When the unchanged gallery parses it.
    row = build_gallery.read_scores(path)[0]
    # Then extra raw columns are tolerated and the new proposals/aggregates survive.
    assert (row.consensus_z, row.disagreement, row.flags, row.proposed_tier) == (1.4, 1.3, ("uncertain",), "review")
