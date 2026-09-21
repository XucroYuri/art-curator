"""G2 CONFIRM coordinator; job.json is the single atomic consent publication root."""
from datetime import datetime, timezone
from pathlib import Path

from .identity_store import save_model
from .ingest_inventory import verify_sources
from .ingest_profile import profile_digest
from .ingest_schema import IngestError, Job, Launch, Stage
from .ingest_storage import lease, long_path, validate_paths
from .negotiation_consent import NegotiationState
from .negotiation_metrics import Labels
from .negotiation_report import NegotiationReport, build_report, policy_digest, report_digest
from .negotiation_sources import Evidence, read_evidence


def current(root: Path) -> tuple[Job, NegotiationReport, Evidence]:
    """Revalidate on every consumption, not just once at confirmation."""
    evidence = read_evidence(root)
    job = evidence.job
    state = job.negotiation
    if state is None:
        raise IngestError("no negotiation report/consent")
    path = (root / state.report_path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise IngestError("report missing or escapes derived root; re-consent required")
    report = NegotiationReport.model_validate_json(path.read_bytes())
    if (report.report_digest != report_digest(report) or state.report_digest != report.report_digest
            or report.snapshot_digest != job.revision or report.analysis_profile_digest != job.profile_digest
            or report.seal_digest != evidence.seal_digest or report.profile_digest != policy_digest()):
        raise IngestError("stale report/snapshot/profile digest; re-consent required")
    launch_path = root / "launch.json"
    if launch_path.exists():
        launch = Launch.model_validate_json(launch_path.read_bytes())
        validate_paths(launch.settings)
        if profile_digest(launch.settings, launch.options) != job.profile_digest:
            raise IngestError("analysis profile digest changed; re-analysis required")
    verify_sources(job.root, evidence.inventory.occurrences)
    return job, report, evidence


def prepare(root: Path, labels: Labels | None = None) -> NegotiationReport:
    """Park at CONFIRM; preparing/prefilling a report never grants consent."""
    root = long_path(root)
    with lease(root):
        evidence = read_evidence(root)
        if evidence.job.progress.stage not in {Stage.PROPOSE, Stage.CONFIRM, Stage.FIRST_PASS}:
            raise IngestError("CONFIRM requires a completed sealed PROPOSE")
        verify_sources(evidence.job.root, evidence.inventory.occurrences)
        report = build_report(evidence, labels or Labels(snapshot_digest=evidence.job.revision))
        directory = root / "negotiation" / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (report.report_digest + ".json")
        prior = evidence.job.negotiation
        if prior and prior.report_digest == report.report_digest:
            # Reopening never revokes or reactivates a receipt.
            current(root)
            return report
        save_model(path, report)
        # A new report supersedes the old *proposal*, never an un-retracted receipt:
        # revocation stays explicit, and the stale receipt cannot authorize the new report.
        history = tuple(r.model_copy(update={"status": "superseded"}) if r.status == "active"
                        and r.receipt_id != prior.active else r for r in prior.history) if prior else ()
        state = NegotiationState(report_path=path.relative_to(root).as_posix(),
                                 report_digest=report.report_digest,
                                 active=prior.active if prior else None, history=history)
        progress = evidence.job.progress.model_copy(update={"stage": Stage.CONFIRM,
            "resume_stage": Stage.CONFIRM, "status": "paused", "running": 0, "queued": 0,
            "reason": "awaiting affirmative human decision; closing/timeout grants nothing",
            "next_action": "ingest-confirm --decision <JSON>; or ingest-dismiss"})
        save_model(root / "job.json",
                   evidence.job.model_copy(update={"negotiation": state, "progress": progress}))
        return report


def dismiss(root: Path) -> None:
    root = long_path(root)
    with lease(root):
        job, _, _ = current(root)
        state = job.negotiation
        if state is None or state.active:
            raise IngestError("active consent requires explicit retraction, not dismissal")
        save_model(root / "job.json",
                   job.model_copy(update={"negotiation": state.model_copy(update={"dismissed": True})}))


def retract(root: Path, actor: str) -> None:
    """Revoke even stale evidence; no evidence access is needed to remove authority."""
    if not actor.strip():
        raise IngestError("retraction requires actor")
    root = long_path(root)
    with lease(root):
        job = Job.model_validate_json((root / "job.json").read_bytes())
        state = job.negotiation
        if state is None or state.active is None:
            return
        history = tuple(r.model_copy(update={"status": "revoked", "revoked_by": actor,
            "revoked_at": datetime.now(timezone.utc).isoformat()}) if r.receipt_id == state.active else r
            for r in state.history)
        progress = job.progress.model_copy(update={"stage": Stage.CONFIRM, "resume_stage": Stage.CONFIRM,
            "status": "paused", "reason": "consent retracted; G2 had no mapping/index/cache effects",
            "next_action": "new scoped affirmative consent required"})
        save_model(root / "job.json", job.model_copy(update={"progress": progress,
            "negotiation": state.model_copy(update={"active": None, "history": history})}))


# Public coordinator surface; mutation helpers import current lazily to avoid a cycle.
from .negotiation_authority import authorize, confirm  # noqa: F401
