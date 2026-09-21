"""Snapshot-bound consent checks, not a G4 policy or G5 mapping publisher."""
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .identity_store import digest, save_model
from .ingest_schema import IngestError, Stage
from .ingest_storage import lease, long_path
from .negotiation_consent import (
    MODE_CONSEQUENCES, SCOPE_CONSEQUENCES, ConsentReceipt, Decision, InheritedSelection, Member,
)
from .negotiation_report import NegotiationReport


def selections(report: NegotiationReport, decision: Decision) -> tuple[InheritedSelection, ...]:
    folders = {f.folder_id: f for f in report.folders}
    selected = {f.folder_id for f in decision.folders}
    if len(selected) != len(decision.folders) or not selected.issubset(folders):
        raise IngestError("duplicate or unknown directory selection")
    if decision.inheritance == "none" and selected:
        raise IngestError("none inheritance must have no folders")
    if decision.inheritance == "all" and selected != folders.keys():
        raise IngestError("all inheritance must explicitly freeze every directory and type")
    result = []
    for selection in decision.folders:
        folder = folders[selection.folder_id]
        members = tuple(m for m in report.members if m.folder_id == selection.folder_id or (
            selection.descendants == "current-snapshot"
            and PurePosixPath(m.path).is_relative_to(PurePosixPath(folder.path))))
        result.append(InheritedSelection(selection=selection, members=members,
            measurement_ref=digest(folder.model_dump_json().encode())))
    return tuple(result)


def confirm(root: Path, decision: Decision) -> ConsentReceipt:
    """One receipt per operation; receipt and checkpoint commit in one job replacement."""
    from .negotiation import current
    # Parse copies too: callers cannot bypass affirmative constraints with model_copy(update=...).
    decision = Decision.model_validate_json(decision.model_dump_json())
    root = long_path(root)
    with lease(root):
        job, report, _ = current(root)
        state = job.negotiation
        if state is None:
            raise IngestError("missing consent state")
        if (decision.report_digest != report.report_digest or decision.snapshot_digest != report.snapshot_digest
                or decision.profile_digest != report.profile_digest):
            raise IngestError("decision digest mismatch")
        for receipt in state.history:
            if receipt.decision.operation_id == decision.operation_id:
                if receipt.status == "active" and receipt.decision == decision and state.active == receipt.receipt_id:
                    return receipt
                raise IngestError("operation already used or revoked; use a new operation ID")
        if state.active:
            raise IngestError("retract active consent before changing choices")
        if job.progress.stage != Stage.CONFIRM:
            raise IngestError("not awaiting CONFIRM")
        if decision.threshold_overrides:
            raise IngestError("threshold overrides unsupported; constitutional minima cannot be lowered")
        if not set(report.limitations).issubset(decision.acknowledged):
            raise IngestError("all report limitations require affirmative acknowledgement")
        inherited = selections(report, decision)
        consequences = (*MODE_CONSEQUENCES[decision.mode], *SCOPE_CONSEQUENCES[decision.inheritance],
                        "context-disabled", "G4-execution-guarded", "no-source-writes")
        if decision.mode == "inherit-only" and decision.inheritance == "none":
            consequences += ("browse-only-not-classification",)
        receipt = ConsentReceipt(receipt_id=digest(decision.model_dump_json().encode()), decision=decision,
            timestamp=datetime.now(timezone.utc).isoformat(), consequences=consequences,
            members=report.members, inherited=inherited, predicted=report.prediction,
            evidence_refs=(state.report_path, report.report_digest, report.snapshot_digest,
                           report.profile_digest, report.seal_digest, report.labels_digest))
        updated = state.model_copy(update={"active": receipt.receipt_id,
            "history": (*state.history, receipt), "dismissed": False})
        # Scheduling advances, but FIRST-PASS execution remains an explicit guard.
        progress = job.progress.model_copy(update={"stage": Stage.FIRST_PASS,
            "resume_stage": Stage.FIRST_PASS, "status": "paused", "checkpoint": receipt.receipt_id,
            "reason": "CONFIRM committed; FIRST-PASS execution not implemented (G4)",
            "next_action": "inspect consent or ingest-retract; no automatic mapping execution"})
        save_model(root / "job.json", job.model_copy(update={"negotiation": updated, "progress": progress}))
        return receipt


def authorize(root: Path, paths: tuple[str, ...]) -> ConsentReceipt:
    """A future consumer must request frozen occurrence paths, never just corpus membership.

    Returns consent intent ONLY. It grants no contextual use or mapping execution;
    future adapters must additionally enforce their own measured/visual/G4/G5 gates.
    """
    from .negotiation import current
    root = long_path(root)
    with lease(root):
        job, report, _ = current(root)
        state = job.negotiation
        if state is None or state.active is None:
            raise IngestError("affirmative active consent required")
        receipt = next((r for r in state.history if r.receipt_id == state.active and r.status == "active"), None)
        if receipt is None or receipt.decision.report_digest != report.report_digest:
            raise IngestError("missing or stale consent")
        allowed = {m.path for m in receipt.members}
        if not set(paths).issubset(allowed):
            raise IngestError("member outside consent snapshot; new scoped receipt required")
        return receipt
