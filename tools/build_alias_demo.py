# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: uv run --no-project --python .venv/Scripts/python.exe python tools/build_alias_demo.py
"""Synthetic-only alias state harness; real images never enter screenshots."""
from __future__ import annotations

import json
from pathlib import Path

from build_gallery import build_payload, read_scores, write_gallery


def main() -> None:
    destination = Path("out/alias-synthetic")
    destination.mkdir(parents=True, exist_ok=True)
    source = Path("tests/fixtures/gallery/scores.csv")
    payload = build_payload(source.parent, read_scores(source))
    support = {"images": 1, "top1_images": 1, "minimum": .99, "p25": .99,
               "median": .99, "p75": .99, "maximum": .99}
    empty = {"images": 0, "top1_images": 0, "minimum": None, "p25": None,
             "median": None, "p75": None, "maximum": None}
    evidence = {"version": 1, "corpus_fingerprint": "c" * 64, "semantic_profile": "d" * 64,
        "banks": [{"reference_name": "A", "sources": ["folder-derived"], "reference_images": 1,
            "tagged_reference_images": 0, "cohort_images": 1, "tagged_cohort_images": 1,
            "candidates": [{"wd_tag": "hero_tag", "rank": 1, "direct": empty, "cohort": support,
                            "strength": "weak", "decision": "unconfirmed"}]},
            {"reference_name": "人物乙：长名称与中文换行核对", "sources": ["human-confirmed"], "reference_images": 3,
             "tagged_reference_images": 3, "cohort_images": 0, "tagged_cohort_images": 0,
             "candidates": [{"wd_tag": "another_character_(synthetic_long_tag_for_wrapping)", "rank": 1,
                "direct": {**support, "images": 3, "top1_images": 3}, "cohort": empty,
                "strength": "relatively-strong", "decision": "rejected"}]}]}
    identities = {"faces": [], "images": [], "clusters": []}
    identities["alias_reconciliation"] = evidence
    payload["identities"] = identities
    payload["memory"] = None
    payload["characters"] = None
    payload["grouping"] = None
    payload["source"] = (destination / "scores.csv").as_posix()
    print(write_gallery(destination, payload, "Alias review · Synthetic", "Placeholder evidence only"))
    (destination / "alias-candidates.json").write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
