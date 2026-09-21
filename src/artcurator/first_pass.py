"""G4 coordinator: live G2 authority plus existing G5 prepared/publication/undo."""
from pathlib import Path

from .album_map import AlbumStore
from .album_map_protocol import ExecutionReceipt, Snapshot
from .album_map_schema import MappingError
from .first_pass_mapping import stage
from .first_pass_audit import guard
from .first_pass_schema import Preview, Run
from .ingest_storage import lease, long_path
from .negotiation import current
from .negotiation_consent import ConsentReceipt


def authority(root: Path, run: Run) -> ConsentReceipt:
    """Caller holds the G2 lease through publication; no revocation TOCTOU window."""
    job, report, _ = current(root)
    state = job.negotiation
    if state is None or state.active is None:
        raise MappingError("affirmative-active-consent-required")
    receipt = next((r for r in state.history if r.receipt_id == state.active and r.status == "active"), None)
    if receipt is None:
        raise MappingError("affirmative-active-consent-required")
    if (receipt.decision.report_digest != report.report_digest or
        receipt.decision.snapshot_digest != run.snapshot_digest or
        receipt.decision.profile_digest != report.profile_digest or
        run.profile != report.analysis_profile_digest):
        raise MappingError("first-pass-stale-consent-or-profile")
    allowed = {m.image_id for m in receipt.members}
    if not {r.image_id for r in run.rows} <= allowed:
        raise MappingError("first-pass-member-outside-consent")
    return receipt


def preview(snapshot: Snapshot, run: Run, root: Path) -> Preview:
    """Preview changes only; no mapping write, scoring, context use or source mutation."""
    parsed = Run.model_validate_json(run.model_dump_json())
    directory = long_path(root)
    with lease(directory):
        return stage(snapshot, parsed, authority(directory, parsed))


def execute(store: AlbumStore, supplied: Preview, approval: tuple[Path, str]) -> ExecutionReceipt:
    """Exact preview confirmation; revalidate authority even on idempotent retries."""
    proposal = Preview.model_validate_json(supplied.model_dump_json())
    root, token = approval
    if token != proposal.fingerprint():
        raise MappingError("affirmative-first-pass-preview-required")
    root = long_path(root)
    with lease(root):
        receipt = authority(root, proposal.run)
        if receipt != proposal.consent:
            raise MappingError("first-pass-consent-changed")
        if stage(proposal.before, proposal.run, receipt) != proposal:
            raise MappingError("first-pass-preview-tampered")
        guard(store, proposal.request.batch_id)
        live = store.snapshot()
        replay = any(r.batch_id == proposal.request.batch_id for r in live.history)
        if not replay and live != proposal.before:
            raise MappingError("first-pass-before-state-changed")
        # Store handles same-operation replay, parent conflicts and crash recovery.
        store.prepare(proposal.request, proposal.request.fingerprint())
        return store.publish(proposal.request.batch_id)
