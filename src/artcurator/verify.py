"""Independent output contract checks and read-only input inventory."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from . import db
from .config import ROOT, load


def inventory() -> None:
    settings = load(ROOT / "config.yaml")
    result = {}
    for role, root in [("input", settings.input), ("references", settings.references), ("posted", settings.posted)]:
        files = [p for p in root.rglob("*") if p.is_file()]
        signatures = Counter()
        for path in files:
            with path.open("rb") as handle:
                signatures[handle.read(8).hex()] += 1
        result[role] = {"total": len(files), "extensions": dict(Counter(p.suffix.lower() for p in files)),
                        "signatures": dict(signatures)}
    db.write_json(ROOT / "out/library/input-inventory.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def verify(out: Path, expected: int) -> None:
    raw = (out / "scores.csv").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "Unexpected BOM"
    with (out / "scores.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(db.COLUMNS)
        rows = list(reader)
    assert len(rows) == expected, (len(rows), expected)
    allowed = {"uncertain", "gaming_suspect", "nsfw", "id_low", "near_dup_runnerup", "audit_sample"}
    numeric = list(db.COLUMNS[9:db.COLUMNS.index("flags")])
    for row in rows:
        for key in ("aes_v25", "topiq_iaa", "topiq_nr", "qrealign", "hpsv3_mu", "hpsv3_sigma", "nsfw_prob", "identity_sim", "novelty", "consensus_z", "disagreement"):
            assert row[key] != "", (row["sha16"], key, "missing required score")
        for key in numeric:
            assert not row[key] or math.isfinite(float(row[key])), (row["sha16"], key)
        assert set(filter(None, row["flags"].split("|"))) <= allowed
        assert (out / row["thumb_rel"]).is_file()
    embeddings = np.load(out / "embeddings.npy", allow_pickle=False)
    ids = json.loads((out / "embeddings_ids.json").read_text(encoding="utf-8"))
    assert embeddings.dtype == np.float16 and embeddings.shape[0] == expected
    assert np.isfinite(embeddings).all()
    assert ids == [r["sha16"] for r in rows]
    with db.connection(out) as connection:
        count = connection.execute("SELECT count(*) FROM scores").fetchone()[0]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        timings = list(connection.execute("SELECT * FROM timings"))
    assert count == expected
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert len(summary) > 500
    originals = db.load_rows(out)
    with db.connection(out) as connection:
        thresholds = json.loads(connection.execute("SELECT value FROM meta WHERE key='thresholds'").fetchone()[0])
    for row in originals:
        assert 0 <= row.qrealign <= 1, (row.sha16, "qrealign range")
        if row.proposed_tier == "archive_candidate":
            assert not row.flags and row.consensus_z < thresholds["review"]
            assert int(row.sha16[:8], 16) % 20 != 0
        if "audit_sample" in row.flags.split("|"):
            assert row.proposed_tier == "review" and row.consensus_z < thresholds["review"]
            assert int(row.sha16[:8], 16) % 20 == 0
        if row.flags and not row.proposed_tier.startswith("route_"):
            assert row.proposed_tier == "review"
        if row.proposed_tier == "queue":
            assert not row.flags and row.consensus_z >= thresholds["queue"]
    references = json.loads((out / "cache/reference_manifest.json").read_text(encoding="utf-8"))
    originals.extend(db.Row.model_validate(r) for group in references["groups"].values() for r in group)
    for row in originals:
        with Path(row.abs_path).open("rb") as handle:
            assert hashlib.file_digest(handle, "sha256").hexdigest() == row.sha256, row.abs_path
    quality = np.array([[float(r[k]) for k in ("aes_v25", "topiq_iaa", "topiq_nr", "qrealign", "hpsv3_mu")] for r in rows])
    deviation = quality.std(axis=0, ddof=0)
    standardized = (quality - quality.mean(axis=0)) / np.where(deviation > 1e-12, deviation, 1)
    mean = standardized.mean(axis=1)
    expected_consensus = (mean - mean.mean()) / (mean.std(ddof=0) or 1)
    assert np.allclose(expected_consensus, [float(r["consensus_z"]) for r in rows])
    sigma = np.array([float(r["hpsv3_sigma"]) for r in rows])
    assert (sigma >= 0).all()
    native = (sigma / deviation[-1]) ** 2 / 5 if deviation[-1] > 1e-12 else np.zeros(len(rows))
    assert np.allclose(np.sqrt(standardized.var(axis=1) + native), [float(r["disagreement"]) for r in rows])
    sample_size = sum(int(r["sha16"][:8], 16) % 5 == 0 for r in rows)
    assert sample_size == sum(bool(r["gaming_delta"]) for r in rows)
    result = {"csv_rows": len(rows), "sqlite_rows": count, "thumbs": len(list((out / "thumbs").glob("*.jpg"))),
              "embedding_shape": list(embeddings.shape), "embedding_dtype": str(embeddings.dtype),
              "finite_scores": True, "sqlite_integrity": "ok", "summary_utf8_readable": True,
              "tier_counts": dict(Counter(r["proposed_tier"] for r in rows)),
              "flags": dict(Counter(f for r in rows for f in r["flags"].split("|") if f)),
              "source_hashes_unchanged": len(originals), "gaming_sample": sample_size,
              "consensus_independently_verified": True, "timings": timings}
    db.write_json(out / f"verification-{expected}.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--expected", type=int, default=1219)
    parser.add_argument("--out", type=Path, default=ROOT / "out/library")
    args = parser.parse_args()
    if args.inventory:
        inventory()
    else:
        verify(args.out, args.expected)


if __name__ == "__main__":
    main()
