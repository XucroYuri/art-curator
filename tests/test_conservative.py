"""Conservative boundaries, fourth-scorer consensus and decoded-image inventory."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from artcurator import db
from artcurator.cluster import cluster
from artcurator.config import Settings
from artcurator.scan import scan


def prepare(root: Path) -> Settings:
    """Create 21 singleton families with known quantile positions."""
    settings = Settings(input=root, out=root, references=root, posted=root, characters_root=root,
                        quality_profile="four-means-v1")
    rows = [db.Row(sha16=f"{i + 100:08x}00000000", sha256=f"{i:064x}", abs_path="unused",
                   path_rel="unused", filename="unused", width=32, height=32, filesize=1,
                   phash=f"{((1 << 12) - 1) << (i * 12):064x}", mode="RGB",
                   aes_v25=float(i), topiq_iaa=float(i), topiq_nr=float(i), qrealign=float(i),
                   identity_sim=0.9, nsfw_prob=0.1) for i in range(21)]
    db.save_rows(root, rows)
    np.save(root / "embeddings.npy", np.eye(21, dtype=np.float16))
    db.write_json(root / "embeddings_ids.json", [r.sha256 for r in rows])
    return settings


@pytest.mark.parametrize(("index", "tier"), [(14, "archive_candidate"), (15, "review"),
                                             (17, "review"), (18, "queue")])
def test_tier_when_at_quantile_boundary(tmp_path: Path, index: int, tier: str) -> None:
    # Given exact 75% and 90% positions.
    settings = prepare(tmp_path)
    # When clustered.
    cluster(settings)
    # Then inclusive review/queue cutoffs and exclusive archive cutoff apply.
    assert db.load_rows(tmp_path)[index].proposed_tier == tier


def test_audit_when_low_tier_hash_selected(tmp_path: Path) -> None:
    # Given low-score hash 100, divisible by 20.
    settings = prepare(tmp_path)
    # When clustered.
    cluster(settings)
    # Then the archive candidate is flagged and promoted for human review.
    row = db.load_rows(tmp_path)[0]
    assert (row.flags, row.proposed_tier) == ("audit_sample", "review")


def test_review_when_low_score_flagged(tmp_path: Path) -> None:
    # Given a low score with a gaming flag and no audit-sample hash.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    rows[1].gaming_delta = 0.4
    db.save_rows(tmp_path, rows)
    # When clustered.
    cluster(settings)
    # Then flagged low scores cannot become archive candidates.
    row = db.load_rows(tmp_path)[1]
    assert (row.flags, row.proposed_tier) == ("gaming_suspect", "review")


def test_scan_when_jpg_and_sidecars_present(tmp_path: Path) -> None:
    # Given four supported formats, an invalid image and ignored sidecars.
    settings = Settings(input=tmp_path, out=tmp_path, references=tmp_path,
                        posted=tmp_path, characters_root=tmp_path)
    for suffix in ("png", "jpg", "jpeg", "webp"):
        Image.new("RGB", (32, 32), "red").save(tmp_path / f"Grok Imagine.{suffix}")
    for name in ("sidecar.db", "sidecar.json", ".backup-baseline-old", "broken.png"):
        (tmp_path / name).write_bytes(b"not an image")
    # When scanning.
    rows = scan(settings, None)
    # Then only decodable images enter the corpus.
    assert len(rows) == 4
    assert {Path(r.abs_path).suffix for r in rows} == {".png", ".jpg", ".jpeg", ".webp"}


def test_fourth_score_when_other_scores_constant(tmp_path: Path) -> None:
    # Given a varying fourth scorer and constant original three scorers.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)
    for row in rows:
        row.aes_v25 = row.topiq_iaa = row.topiq_nr = 1.0
    db.save_rows(tmp_path, rows)
    # When consensus is calculated.
    cluster(settings)
    # Then Q-ReAlign contributes to ranking, not just the export.
    results = db.load_rows(tmp_path)
    assert results[0].consensus_z < results[-1].consensus_z


def test_sql_view_when_reopening_legacy_manifest(tmp_path: Path) -> None:
    # Given an existing old-format SQL view.
    import sqlite3

    prepare(tmp_path)
    with sqlite3.connect(tmp_path / "manifest.sqlite") as connection:
        connection.execute("DROP VIEW scores")
        connection.execute("CREATE VIEW scores AS SELECT position FROM images")
        connection.execute("PRAGMA user_version=0")
    # When reopening through the persistence boundary.
    with db.connection(tmp_path) as connection:
        values = list(connection.execute("SELECT qrealign FROM scores"))
    # Then the additive schema works on existing outputs without deleting scores.
    assert values == [(float(i),) for i in range(21)]
