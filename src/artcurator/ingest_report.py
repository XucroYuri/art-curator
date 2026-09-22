"""Sealed G1 analysis digest, not negotiation consent or a virtual-album mutation."""
import json
from pathlib import Path
from typing import get_args

from .identity_store import atomic_bytes, save_model
from .ingest_catalog import lookup
from .ingest_profile import Seal
from .ingest_schema import Inventory, Job
from .ingest_storage import artifacts


def propose(root: Path, inventory: Inventory, job: Job) -> None:
    from .album_map_cli import Operation
    from .ingest_cli import COMMANDS
    out = root / "revisions" / inventory.revision
    live = [r for r in inventory.occurrences if r.status != "unavailable"]
    unique = {r.sha256 for r in live if r.sha256}
    failures = [sha for sha in unique if (entry := lookup(root, sha)) is None or entry.row is None]
    folders: dict[str, int] = {}
    for occurrence in live:
        folder = Path(occurrence.path).parent.as_posix()
        folders[folder] = folders.get(folder, 0) + 1
    unknown = [r.action for r in job.receipts if r.reason]
    from .identity_schema import IdentityDocument
    identity_path = out / "identities.json"
    identities = IdentityDocument.model_validate_json(identity_path.read_bytes()) if identity_path.exists() else None
    report = {"schema_version": 1, "revision": inventory.revision,
        "parent_revision": inventory.parent_revision, "profile_digest": job.profile_digest,
        "stage": "PROPOSE", "sealed": True, "partial": bool(unknown or failures),
        "backend_commands": list(COMMANDS), "album_operations": get_args(Operation),
        "occurrences": len(live), "unique_images": len(unique), "decode_failed": failures,
        "detected_faces": identities.face_count if identities else None,
        "cluster_count": identities.cluster_count if identities else None,
        "analysis_artifacts": [a.model_dump() for receipt in job.receipts
                               if receipt.stage == "ANALYZE" for a in receipt.artifacts],
        "unavailable_signals": unknown, "folder_measurements": [
            {"folder": folder, "occurrences": count, "purity": None, "coherence": None,
             "measurement_status": "not_run",
             "reason": "G2 negotiation is a separate explicit step; not measured by this G1 report"}
            for folder, count in sorted(folders.items())],
        "representatives": [f"previews/{sha}.jpg" for sha in sorted(unique)[:24]
                            if (out / "previews" / f"{sha}.jpg").exists()],
        "proposed_inheritance": [], "consent": None, "mapping_mutations": 0,
        "first_pass_estimate": {"eligible": None, "manual_review": len(unique),
                                 "reason": "downstream contracts exist but were not executed by G1; no automatic decisions"},
        "costs": [r.model_dump(mode="json") for r in job.receipts],
        "planning_estimate": {"images": 26876, "hours": [2, 3], "wd_seconds_per_image": [.13, .22],
            "hardware": "RTX 5060 Ti", "qualified": False,
            "reason": "historical component estimate, not measured full-library guarantee"},
        "unverified": ["cross-file crash-atomicity; per-file replacement only",
            "full-library throughput, native-code source sandbox, GPU-active/energy/peak meters",
            "hard per-write quota enforcement inside third-party/native stage writers"],
        "guards": ["CONFIRM", "FIRST-PASS", "REVIEW", "ARCHIVE"]}
    atomic_bytes(out / "analysis-report.json", json.dumps(report, indent=2, ensure_ascii=False).encode())
    markdown = (f"# G1 analysis report\n\nRevision: `{inventory.revision}`\n\n"
                f"{len(live)} occurrences / {len(unique)} unique images. Partial: {report['partial']}.\n\n"
                "No source files or mappings modified. Downstream backend contracts are available separately; "
                "this G1 run does not execute negotiation, consent, mapping, first-pass or archive actions.\n\n"
                "26,876-image first pass: **2–3 hours estimated**, not guaranteed; WD 0.13–0.22 s/image "
                "on RTX 5060 Ti. Fixture walls do not qualify inference throughput.\n\n"
                "**Unverified:** cross-file crash-atomicity, native-code sandbox and hard per-write quotas.\n")
    markdown += "\n## Available backend command contracts (not run by this report)\n\n"
    markdown += ", ".join(f"`{command}`" for command in COMMANDS)
    markdown += "\n\n`album-map --album-op`: " + ", ".join(f"`{operation}`" for operation in get_args(Operation)) + "\n"
    markdown += "\n## Representative previews (not identity assignments)\n\n"
    markdown += "\n".join(f"![{sha[:12]}](previews/{sha}.jpg)" for sha in sorted(unique)[:24]
                          if (out / "previews" / f"{sha}.jpg").exists())
    atomic_bytes(out / "analysis-report.md", markdown.encode())
    paths = tuple(p for p in out.rglob("*") if p.is_file() and p.name != "seal.json")
    save_model(out / "seal.json", Seal(revision=inventory.revision, artifacts=artifacts(root, paths)))
