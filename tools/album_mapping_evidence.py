#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# ─── How to run ───
# 1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
# 2. uv run tools/album_mapping_evidence.py pytest-result.xml
# 3. Optional --destination selects an existing synthetic evidence directory.
# ──────────────────
"""Generate scoped, explicitly non-graduating G5 receipts from observed pytest XML."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

CRITERIA: Final = (
    ("FR-ALBUM-MAP-001", "partial", "test_exchange_preserves_history_when_restored", "Full schema/view/extension matrix remains open"),
    ("FR-ALBUM-MAP-002", "inconclusive", "", "G4 first-pass integration not implemented here"),
    ("FR-ALBUM-MAP-003", "partial", "test_undo_preserves_aba_when_later_edit_returns_to_same_value", "Nested-row undo and reference cascades remain open"),
    ("FR-ALBUM-MAP-004", "partial", "test_browser_draft_stages_then_commits_when_confirmed", "Split/merge and client walkthrough remain open"),
    ("FR-ALBUM-MAP-005", "partial", "test_unknown_pool_freezes_and_promotes_when_seed_has_ten_images", "Richer selection/lineage/coherence qualification remains open"),
    ("FR-ALBUM-MAP-006", "partial", "test_deferred_trigger_once_when_revision_repeated", "Automatic clock/evidence scheduling and filters remain open"),
    ("FR-ALBUM-MAP-007", "inconclusive", "", "G6 separately authorized physical-export integration remains open"),
    ("NFR-ALBUM-MAP-001", "partial", "test_old_or_complete_revision_when_cutpoint_raises", "Exception rollback only; process kill, physical faults, global enrollment and backup/migrations unqualified"),
    ("INV-M", "inconclusive", "", "No original I/O in synthetic adapters; all-eight-stage filesystem tracing not run"),
    ("FR-ALBUM-VISION-003", "partial", "test_v2_label_dispatch_when_disposition_added", "Full six-type/eight-state matrix remains open"),
    ("FR-ALBUM-VISION-005", "partial", "test_receipt_refuses_pass_claim_when_suite_failed", "No G5 graduation; complete seven-gap release manifest not qualified"),
    ("FR-ALBUM-NEGOTIATE-003", "partial", "test_consent_stays_zero_when_execution_count_supplied", "V2 authority lifecycle/dual-version consumer dispatch remains open"),
    ("FR-ALBUM-NEGOTIATE-004", "partial", "test_consent_when_granted_never_authorizes_context_or_mapping", "No UI changed or qualified; v2 capability remains disabled"),
    ("NFR-SPEC-001", "partial", "test_receipt_refuses_pass_claim_when_suite_failed", "Scoped trace only, not full SPEC-TREE certification"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = Path(args.destination) if args.destination else root / "specs" / "evidence"
    suites = ET.parse(args.report).getroot().findall(".//testsuite")
    totals = {key: sum(int(suite.get(key, "0")) for suite in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    cases = tuple(case for suite in suites for case in suite.findall("testcase"))
    passed = tuple(case.get("name", "") for case in cases
        if case.find("failure") is None and case.find("error") is None and case.find("skipped") is None)
    files = sorted((*root.glob("src/artcurator/album_*.py"), *root.glob("tests/test_album_*.py"),
        root / "src/artcurator/cli.py", root / "src/artcurator/identity_labels.py",
        root / "tools/album_mapping_evidence.py", root / "docs/pipeline/album-mapping.md",
        root / "docs/pipeline/album-mapping-audit.md",
        root / "specs/adr/ADR-0006-transactional-album-mapping.md", root / "specs/README.md"))
    inventory = []
    for path in files:
        payload = path.read_bytes()
        lines = payload.decode("utf-8").splitlines()
        inventory.append({"path": path.relative_to(root).as_posix(), "lines": len(lines),
            "nonblank_noncomment_lines": sum(bool(line.strip()) and not line.lstrip().startswith("#") for line in lines),
            "sha256": hashlib.sha256(payload).hexdigest()})
    run = {"schema_version": "album-mapping-evidence-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "pytest": totals, "junit_sha256": hashlib.sha256(Path(args.report).read_bytes()).hexdigest(),
        "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                    "os": platform.system(), "machine": platform.machine(), "filesystem_qualified": False},
        "configuration": {"journal_mode": "WAL", "synchronous": "FULL", "foreign_keys": True, "migration": 1},
        "g5_graduated": False, "power_loss_qualified": False, "performance_measured": False,
        "fault_model": "Python exceptions at eleven P/C/ack cutpoints, rollback and reopen; not process-kill or power loss",
        "lsp": "unavailable: basedpyright not installed; prior installation decline respected",
        "fixture": "ALBUM-MAP-v1 synthetic test recipes; post-run source digests, not a preregistered release fixture",
        "inventory": inventory, "limitations_document": "docs/pipeline/album-mapping.md"}
    (destination / "album-mapping-run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    for requirement, verdict, test, limitation in CRITERIA:
        evidence = tuple(name for name in passed if test and name.startswith(test))
        scoped = verdict if evidence and not totals["failures"] and not totals["errors"] else "inconclusive"
        receipt = {"schema_version": "album-ac-receipt-v1", "ac_id": "AC-" + requirement + "-01",
            "verdict": scoped, "implementation_verdict": verdict,
            "method": "synthetic regression tests plus implementation/spec audit",
            "fixture": "ALBUM-MAP-v1 scoped recipe; see run inventory hashes",
            "comparator": "exact state/receipt contract of the named executed regression, not the entire owning AC",
            "passed_test_names": evidence, "limitations": [limitation],
            "run_receipt": "album-mapping-run.json", "g5_graduated": False}
        suffix = ".g5.json" if requirement.startswith("FR-ALBUM-NEGOTIATE-") else ".json"
        (destination / (receipt["ac_id"] + suffix)).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pytest": totals, "receipts": len(CRITERIA), "g5_graduated": False,
        "inventory": [(item["path"], item["lines"]) for item in inventory]}, indent=2))


if __name__ == "__main__":
    main()
