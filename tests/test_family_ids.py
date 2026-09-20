"""Snapshot IDs bind grouping semantics and unique full content identities."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from artcurator import db
from artcurator.cluster import cluster
from test_conservative import prepare


def test_family_ids_survive_unrelated_addition(tmp_path: Path) -> None:
    # Given stable singleton member sets.
    settings = prepare(tmp_path)
    cluster(settings)
    rows = db.load_rows(tmp_path)
    before = {row.sha256: row.family_id for row in rows}
    added = rows[0].model_copy(update={"sha16": "0" * 16, "sha256": "f" * 64,
                                      "phash": f"{((1 << 12) - 1) << 260:x}"})
    rows.insert(0, added)
    db.save_rows(tmp_path, rows)
    np.save(tmp_path / "embeddings.npy", np.eye(len(rows), dtype=np.float16))
    db.write_json(tmp_path / "embeddings_ids.json", [row.sha256 for row in rows])
    # When an unrelated image sorts before all existing families.
    cluster(settings)
    # Then no existing content-set ID is renumbered.
    after = {row.sha256: row.family_id for row in db.load_rows(tmp_path)}
    assert all(after[content] == family for content, family in before.items())


def test_family_digest_uses_unique_full_hashes(tmp_path: Path) -> None:
    # Given duplicate content and colliding short IDs in one family.
    settings = prepare(tmp_path)
    rows = db.load_rows(tmp_path)[:2]
    rows[0].sha256 = "a" * 16 + "0" * 48
    rows[1].sha256 = "a" * 16 + "1" * 48
    for row in rows:
        row.sha16 = "a" * 16
        row.phash = "0"
    rows.append(rows[0].model_copy())
    rows.reverse()
    db.save_rows(tmp_path, rows)
    np.save(tmp_path / "embeddings.npy", np.eye(3, dtype=np.float16))
    db.write_json(tmp_path / "embeddings_ids.json", [row.sha256 for row in rows])
    profile = "phash6-or-phash10-cosine096-connected-v1"
    members = ["a" * 16 + "0" * 48, "a" * 16 + "1" * 48]
    canonical = json.dumps([profile, members], ensure_ascii=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    # When the snapshot is grouped.
    cluster(settings)
    # Then the exact digest is independently reproducible without short-ID aliasing.
    families = json.loads((tmp_path / "families.json").read_text(encoding="utf-8"))
    assert len(families) == 1
    assert families[0]["family_id"] == expected
    assert families[0]["member_content_ids"] == members
    assert families[0]["grouping_profile_id"] == profile
    assert {row.family_id for row in db.load_rows(tmp_path)} == {expected}


def test_family_digest_changes_with_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the same fixed content with an explicitly different grouping profile.
    from importlib import import_module

    module = import_module("artcurator.cluster")
    settings = prepare(tmp_path)
    cluster(settings)
    before = [row.family_id for row in db.load_rows(tmp_path)]
    monkeypatch.setattr(module, "GROUPING_PROFILE_ID", "different-grouping-v2")
    # When grouping under a new semantic identity.
    cluster(settings)
    # Then every snapshot ID changes even if its members happen to match.
    assert all(row.family_id != old for row, old in zip(db.load_rows(tmp_path), before, strict=True))


def test_family_ids_survive_permutation_and_duplicate(tmp_path: Path) -> None:
    # Given a fixed set of family members, reordered with a duplicate file row.
    settings = prepare(tmp_path)
    cluster(settings)
    rows = db.load_rows(tmp_path)
    before = {row.sha256: row.family_id for row in rows}
    rows = list(reversed(rows)) + [rows[0].model_copy()]
    db.save_rows(tmp_path, rows)
    np.save(tmp_path / "embeddings.npy", np.eye(len(rows), dtype=np.float16))
    db.write_json(tmp_path / "embeddings_ids.json", [row.sha256 for row in rows])
    # When the same content sets are regrouped.
    cluster(settings)
    # Then neither ordering nor duplicate row count enters the snapshot digest.
    assert {row.sha256: row.family_id for row in db.load_rows(tmp_path)} == before


def test_family_id_changes_when_members_merge(tmp_path: Path) -> None:
    # Given two formerly separate families with new grouping evidence linking them.
    settings = prepare(tmp_path)
    cluster(settings)
    rows = db.load_rows(tmp_path)
    old_ids = {rows[0].family_id, rows[1].family_id}
    rows[1].phash = rows[0].phash
    db.save_rows(tmp_path, rows)
    # When the member content set changes.
    cluster(settings)
    # Then a merged family is a new snapshot identity, not a reused lineage label.
    results = db.load_rows(tmp_path)
    assert results[0].family_id == results[1].family_id
    assert results[0].family_id not in old_ids
