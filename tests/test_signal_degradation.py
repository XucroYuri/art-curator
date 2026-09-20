"""Conservative completion bounds for missing requested evidence."""
import csv
from pathlib import Path

import pytest

from artcurator import db
from artcurator.cluster import cluster
from artcurator.config import Settings
from artcurator.report import report
from test_conservative import prepare


@pytest.mark.parametrize("signal", ["aes_v25", "topiq_iaa", "topiq_nr", "qrealign"])
def test_missing_scorer_cannot_promote_queue(tmp_path: Path, signal: str) -> None:
    # Given a complete cohort whose last row qualifies for queue.
    settings = prepare(tmp_path)
    cluster(settings)
    rows = db.load_rows(tmp_path)
    assert rows[-1].proposed_tier == "queue"
    setattr(rows[-1], signal, None)
    db.save_rows(tmp_path, rows)
    # When evidence is removed and the report is rebuilt.
    cluster(settings)
    report(settings)
    # Then neither surviving-score means nor uncertain cohort quantiles authorize quality tiers.
    results = db.load_rows(tmp_path)
    assert all(row.proposed_tier == "review" for row in results)
    assert all(row.consensus_z is None and row.disagreement is None for row in results)
    assert f"signal_unavailable:{signal}" in results[-1].flags.split("|")
    assert "quality_population_unavailable" in results[0].flags.split("|")
    with (tmp_path / "scores.csv").open(encoding="utf-8", newline="") as stream:
        exported = list(csv.DictReader(stream))
    assert f"signal_unavailable:{signal}" in exported[-1]["flags"]
    assert f"signal_unavailable:{signal}" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_default_roster_requires_absent_hps(tmp_path: Path) -> None:
    # Given the default requested roster with no HPS output at all.
    settings = Settings.model_validate(prepare(tmp_path).model_dump(exclude={"quality_profile"}))
    # When clustering the incomplete cohort.
    cluster(settings)
    # Then absence does not silently select the four-mean policy.
    assert all("signal_unavailable:hpsv3_mu" in row.flags for row in db.load_rows(tmp_path))
    assert all(row.proposed_tier == "review" for row in db.load_rows(tmp_path))


@pytest.mark.parametrize("signal", ["nsfw_prob", "identity_sim"])
def test_missing_gate_abstains(tmp_path: Path, signal: str) -> None:
    # Given a low-quality row lacking required gate evidence.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    setattr(rows[1], signal, None)
    db.save_rows(tmp_path, rows)
    # When proposing tiers.
    cluster(settings)
    # Then missing evidence is visible and cannot authorize archive.
    result = db.load_rows(tmp_path)[1]
    assert result.proposed_tier == "review"
    assert f"signal_unavailable:{signal}" in result.flags


def test_no_quality_values_abstains_without_zero_imputation(tmp_path: Path) -> None:
    # Given an entirely unscored quality cohort.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    for row in rows:
        row.aes_v25 = row.topiq_iaa = row.topiq_nr = row.qrealign = None
    db.save_rows(tmp_path, rows)
    # When clustering without evidence bounds.
    cluster(settings)
    # Then absence is not represented by a numeric zero.
    assert all(row.consensus_z is None and row.proposed_tier == "review" for row in db.load_rows(tmp_path))


@pytest.mark.parametrize("signal", ["hpsv3_mu", "hpsv3_sigma"])
def test_missing_hps_output_invalidates_quality_population(tmp_path: Path, signal: str) -> None:
    # Given a five-mean population with one missing required HPS output.
    settings = prepare(tmp_path).model_copy(update={"quality_profile": "five-means-v1"})
    rows = db.load_rows(tmp_path)
    for i, row in enumerate(rows):
        row.hpsv3_mu, row.hpsv3_sigma = float(i), 0.0
    setattr(rows[-1], signal, None)
    db.save_rows(tmp_path, rows)
    # When computing proposals.
    cluster(settings)
    # Then sigma is required evidence too, not silently omitted on partial runs.
    results = db.load_rows(tmp_path)
    assert all(row.consensus_z is None and row.proposed_tier == "review" for row in results)
    assert f"signal_unavailable:{signal}" in results[-1].flags


def test_conflicting_completion_grid_abstains(tmp_path: Path) -> None:
    # Given a finite set of admissible completions with conflicting quality decisions.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    decisions: set[str] = set()
    for value in (-1000.0, 0.0, 20.0, 1000.0):
        rows[-1].qrealign = value
        db.save_rows(tmp_path, rows)
        cluster(settings)
        decisions.add(db.load_rows(tmp_path)[-1].proposed_tier)
    assert decisions == {"queue", "review"}
    rows[-1].qrealign = None
    db.save_rows(tmp_path, rows)
    # When the completion is unknown (and continuous bounds are undeclared).
    cluster(settings)
    # Then no plug-in average can authorize one of the conflicting decisions.
    assert db.load_rows(tmp_path)[-1].proposed_tier == "review"


def test_rescored_cohort_clears_unavailability(tmp_path: Path) -> None:
    # Given a previously incomplete population, now fully restored.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    rows[-1].qrealign = None
    db.save_rows(tmp_path, rows)
    cluster(settings)
    rows = db.load_rows(tmp_path)
    rows[-1].qrealign = 20.0
    db.save_rows(tmp_path, rows)
    # When recomputing from the restored evidence.
    cluster(settings)
    # Then stale abstention flags and null scores do not survive recovery.
    result = db.load_rows(tmp_path)[-1]
    assert result.proposed_tier == "queue" and result.flags == ""
    assert result.consensus_z is not None


def test_missing_quality_preserves_safety_assessment_route(tmp_path: Path) -> None:
    # Given unavailable quality but observed safety-routing evidence.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    rows[-1].qrealign, rows[-1].nsfw_prob = None, 0.9
    db.save_rows(tmp_path, rows)
    # When proposing human assessment.
    cluster(settings)
    # Then the non-quality assessment request retains precedence, with missingness visible.
    result = db.load_rows(tmp_path)[-1]
    assert result.proposed_tier == "route_nsfw"
    assert "signal_unavailable:qrealign" in result.flags
