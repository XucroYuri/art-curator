# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["numpy", "pydantic>=2", "PyYAML"]
# ///
# Run: uv run --no-project --python .venv-identity/Scripts/python.exe python tools/run_identity_grouping.py out/library out/review out/similarity
"""Measure additive grouping on existing snapshots; retain private run receipts."""
import json
import sys
import time
from pathlib import Path

from artcurator.config import ROOT, confine_writes, environment, load, output_path
from artcurator.identity import run
from artcurator.identity_anchor import load_anchors
from artcurator.identity_group_schema import GroupDocument
from artcurator.identity_store import atomic_bytes, file_digest, load_document


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    base = load(ROOT / "config.yaml")
    for index, argument in enumerate(sys.argv[1:]):
        out = output_path(Path(argument))
        settings = base.model_copy(update={"out": out})
        environment(out)
        confine_writes()
        legacy = {name: file_digest(out / name) for name in
                  ("scores.csv", "families.json", "manifest.sqlite", "identities.json", "identities.npy")}
        started = time.perf_counter()
        reused = (out / "anchors.json").exists()
        if not reused:
            run(settings, "identity-anchor")
        anchor_wall = time.perf_counter() - started
        anchors, _ = load_anchors(out)
        started = time.perf_counter()
        run(settings, "identity-group")
        group_wall = time.perf_counter() - started
        result = GroupDocument.model_validate_json((out / "character-groups.json").read_bytes())
        after = {name: file_digest(out / name) for name in legacy}
        if after != legacy:
            raise RuntimeError("additive grouping changed legacy evidence")
        identity = load_document(out)
        ab = json.loads((out / "identity-ab.json").read_bytes())
        candidates = {face.image_sha16 for face in identity.faces if face.cluster_id in ab["target_clusters"]}
        candidate_named = set().union(*(set(c.images) & candidates for c in result.characters))
        receipt = {"corpus_alias": ("library", "review", "similarity")[index],
            "anchor_reused": reused, "anchor_command_wall_seconds": anchor_wall,
            "anchor_build_wall_seconds": anchors.wall_seconds, "group_command_wall_seconds": group_wall,
            "thresholds": result.thresholds.model_dump(),
            "anchor_counts": {name: counts["accepted"] for name, counts in anchors.folders.items()},
            "characters": {c.character: c.image_count for c in result.characters},
            "images": result.provenance.images, "faces": result.provenance.faces,
            "abstained_faces": result.abstained.face_count,
            "abstained_face_rate": result.abstained.face_count / max(result.provenance.faces, 1),
            "unassigned_images": result.provenance.unassigned_images,
            "any_abstained_images": result.provenance.any_abstained_images,
            "multi_character_images": result.provenance.multi_character_images,
            "candidate_images": len(candidates),
            "candidate_character_images": {c.character: len(set(c.images) & candidates) for c in result.characters},
            "candidate_unassigned_images": len(candidates - candidate_named),
            "legacy_unchanged": after == legacy, "legacy_sha256": legacy}
        atomic_bytes(out / "identity-grouping-run.json", json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8"))
        print(json.dumps(receipt, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
