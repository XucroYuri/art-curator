# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Run: .venv\Scripts\python.exe tools\conservative_receipt.py
"""Retain conservative-run provenance, JPG decode evidence and wall-clock intervals."""
import importlib.metadata
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from artcurator import db
from artcurator.config import ROOT, confine_writes, environment, load
from artcurator.report import report
from artcurator.scan import pixels


def timestamp(line: str) -> datetime:
    return datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")


def main() -> None:
    base = load(ROOT / "config.yaml")
    environment(ROOT / "out/library")
    confine_writes()
    for folder, corpus in (("library", "queue"), ("review", "review")):
        out = ROOT / "out" / folder
        settings = base.model_copy(update={"out": out, "input": base.input.parent / corpus})
        rows = db.load_rows(out)
        lines = (out / "run.log").read_text(encoding="utf-8").splitlines()
        start_at = next(line[:23] for line in lines if "command start" in line)
        end = next(timestamp(line) for line in lines
                   if line[:23] >= start_at and "command complete name=report" in line)
        wall = (end - timestamp(start_at)).total_seconds()
        db.meta(out, "conservative_wall_seconds_including_resume", str(wall))
        db.meta(out, "conservative_wall_interval_local", f"{start_at} to {end.isoformat()}")
        sizes = Counter(Counter(row.family_id for row in rows).values())
        duplicates: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            duplicates[row.sha256].append(row.path_rel)
        jpgs = [row for row in rows if Path(row.abs_path).suffix.lower() in {".jpg", ".jpeg"}]
        jpg_evidence = []
        for row in jpgs:
            image = pixels(Path(row.abs_path))
            if image.size != (row.width, row.height) or image.mode != "RGB":
                raise RuntimeError(f"JPG decode disagrees with manifest: {row.sha16}")
            jpg_evidence.append({"path_rel": row.path_rel, "sha16": row.sha16,
                                 "size": image.size, "mode": image.mode})
        result = {"rows": len(rows), "unique_hashes": len(duplicates),
                  "extensions": dict(Counter(Path(r.abs_path).suffix.lower() for r in rows)),
                  "tiers": dict(Counter(r.proposed_tier for r in rows)),
                  "flags": dict(Counter(f for r in rows for f in r.flags.split("|") if f)),
                  "family_size_counts": dict(sizes), "wall_seconds_including_resume": wall,
                  "duplicate_content_paths": [paths for paths in duplicates.values() if len(paths) > 1],
                  "jpg_decode_evidence": jpg_evidence}
        db.write_json(out / "conservative-receipt.json", result)
        versions = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
        db.write_json(out / "conservative-main-environment.json", dict(sorted(versions.items())))
        report(settings)
        print(json.dumps({key: value for key, value in result.items() if key != "jpg_decode_evidence"},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
