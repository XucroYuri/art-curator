"""Read-only G1 coordinator: durable IDLE -> INGEST -> ANALYZE -> PROPOSE."""
import logging
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from .config import Settings
from .identity_store import digest, save_model
from .ingest_adapters import Action, Request, Result, execute as inline_execute
from .ingest_catalog import assemble, lookup, publish
from .ingest_inventory import discover, freeze, verify_sources
from .ingest_profile import Seal, profile_digest, seed
from .ingest_report import propose
from .ingest_runtime import Runtime, Stopped, control
from .ingest_schema import Admission, IngestError, Inventory, Job, Launch, Options, Progress, Receipt, Stage
from .ingest_storage import admit, artifacts, lease, long_path, protect_sources, valid, validate_paths


def _scan(runtime: Runtime, inventory: Inventory, launch: Launch) -> None:
    settings, options = launch.settings, launch.options
    unique = {r.sha256: r for r in reversed(inventory.occurrences)
              if r.sha256 and r.status != "unavailable"}
    pending = []
    for sha, occurrence in sorted(unique.items()):
        hit = lookup(settings.out, sha)
        if hit is None:
            pending.append(occurrence)
        else:
            runtime.record(Receipt(operation_id=digest(("scan:" + sha).encode()), job_id=runtime.job.job_id,
                revision=inventory.revision, parent_revision=inventory.parent_revision, stage=Stage.INGEST,
                action="scan", input_digest=sha, profile_digest="scan-rgb-v1", outcome="cached",
                items=1, cache_hits=1, artifacts=hit.artifacts, reason=hit.reason))
    for offset in range(0, len(pending), options.scan_batch_size):
        batch = pending[offset:offset + options.scan_batch_size]
        key = digest("\n".join(r.sha256 for r in batch).encode())
        location = settings.out / "scan" / key
        receipt = runtime.action(Request(settings=settings.model_copy(update={"out": location}),
            options=options, action="scan", paths=tuple(settings.input / r.path for r in batch)))
        publish(settings.out, inventory, receipt.artifacts)
        runtime.checkpoint()


def _barrier(runtime: Runtime, out: Path, names: tuple[str, ...]) -> None:
    state = runtime.job.progress.stage
    payload = artifacts(runtime.root, tuple(out / name for name in names))
    receipt = Receipt(operation_id=digest((runtime.job.revision + state).encode()),
        job_id=runtime.job.job_id, revision=runtime.job.revision,
        parent_revision=runtime.job.parent_revision, stage=state, action="barrier",
        input_digest=runtime.job.revision, profile_digest=runtime.job.profile_digest,
        artifacts=payload, outcome="completed")
    save_model(out / f"barrier-{state}.json", receipt)


def _pipeline(runtime: Runtime, inventory: Inventory, launch: Launch) -> None:
    settings, options = launch.settings, launch.options
    out = settings.out / "revisions" / inventory.revision
    out.mkdir(parents=True, exist_ok=True)
    for name in ("barrier-IDLE.json", "barrier-INGEST.json"):
        barrier_path = out / name
        if barrier_path.exists():
            barrier = Receipt.model_validate_json(barrier_path.read_bytes())
            if (barrier.revision != inventory.revision or barrier.profile_digest != runtime.job.profile_digest
                    or not valid(settings.out, barrier.artifacts)):
                raise IngestError(f"{name} barrier payload inconsistent; recovery required")
    if not (out / "inventory.json").exists():
        save_model(out / "inventory.json", inventory)
        save_model(out / "snapshot.json", inventory)
    _barrier(runtime, out, ("snapshot.json",))
    runtime.stage(Stage.INGEST)
    _scan(runtime, inventory, launch)
    runtime.checkpoint()
    decoded = []
    for occurrence in inventory.occurrences:
        content = lookup(settings.out, occurrence.sha256) if occurrence.sha256 else None
        if content and content.row is None and occurrence.status != "unavailable":
            occurrence = occurrence.model_copy(update={"status": "failed", "reason": content.reason})
        decoded.append(occurrence)
    inventory = inventory.model_copy(update={"occurrences": tuple(decoded)})
    save_model(out / "inventory.json", inventory)
    stage_settings = settings.model_copy(update={"out": out})
    if not (out / "barrier-INGEST.json").exists():
        assemble(settings.out, inventory, settings.input)
        seed(stage_settings, runtime.previous, options)
        _barrier(runtime, out, ("inventory.json", "manifest.sqlite", "manifest-order.sha256"))
    runtime.stage(Stage.ANALYZE)
    actions: tuple[Action, ...] = ("detect", "embed", "cluster", "anchors", "group", "tag", "candidates")
    for action in actions:
        verify_sources(settings.input, inventory.occurrences)
        runtime.action(Request(settings=stage_settings, options=options, action=action))
    _barrier(runtime, out, ("barrier-INGEST.json",))
    runtime.stage(Stage.PROPOSE)
    verify_sources(settings.input, inventory.occurrences)
    if profile_digest(settings, options) != runtime.job.profile_digest:
        raise IngestError("profile/reference inputs changed during analysis; proposal refused")
    _barrier(runtime, out, ("barrier-ANALYZE.json",))
    propose(settings.out, inventory, runtime.job)
    admit(settings.out, 0, options)
    runtime.save(runtime.job.progress.model_copy(update={"status": "complete", "queued": 0,
        "running": 0, "next_action": "ingest-negotiate: measured report and explicit CONFIRM",
        "heartbeat": time.time()}))


def run(settings: Settings, options: Options | None = None, *,
        execute: Callable[[Request], Result] = inline_execute) -> Job:
    """Explicit synchronous owner; CLI starts this in an independent background process."""
    selected = options or Options()
    validate_paths(settings)
    settings = settings.model_copy(update={"out": long_path(settings.out)})
    admit(settings.out, 1024 * 1024, selected)
    with lease(settings.out), protect_sources(settings, selected.profile_from):
        path = settings.out / "job.json"
        prior = Job.model_validate_json(path.read_bytes()) if path.exists() else None
        if prior and prior.root.resolve() != settings.input.resolve():
            raise IngestError("output already belongs to a different source root")
        job = Job(job_id=uuid.uuid4().hex, root=settings.input.resolve(), profile_digest="pending-admission",
                  negotiation=prior.negotiation if prior else None,
                  progress=Progress(status="running", heartbeat=time.time(), next_action="discover"))
        runtime = Runtime(settings.out, job, execute)
        runtime.previous = prior
        control(settings.out, "resume")
        runtime.start()
        try:
            profile = profile_digest(settings, selected)
            with runtime.lock:
                runtime.job = runtime.job.model_copy(update={"profile_digest": profile})
            previous_path = settings.out / "revisions" / prior.revision / "inventory.json" if prior else None
            previous = Inventory.model_validate_json(previous_path.read_bytes()) if previous_path and previous_path.exists() else None
            if (prior and previous and prior.progress.status != "complete"
                    and prior.progress.stage not in {Stage.CONFIRM, Stage.FIRST_PASS}
                    and prior.profile_digest == profile):
                inventory = previous
                verify_sources(settings.input, inventory.occurrences)
            else:
                def notify(count: int) -> None:
                    with runtime.lock:
                        runtime.job = runtime.job.model_copy(update={"progress":
                            runtime.job.progress.model_copy(update={"discovered": count})})
                    runtime.checkpoint()
                inventory = freeze(discover(settings.input, notify), previous, profile)
            runtime.job = runtime.job.model_copy(update={"revision": inventory.revision,
                "parent_revision": inventory.parent_revision})
            # Worst-case scan/preview metadata reservation plus replacement/headroom.
            reservation = len(inventory.occurrences) * 272 * 1024 + 1024 * 1024
            retained = admit(settings.out, reservation, selected)
            save_model(settings.out / "admission.json", Admission(quota_bytes=selected.quota_bytes,
                free_disk_reserve_bytes=selected.reserve_bytes, retained_bytes=retained,
                incremental_reservation_bytes=reservation,
                original_bytes_excluded=sum(r.size for r in inventory.occurrences if r.status != "unavailable")))
            validation = Receipt(operation_id=digest((job.job_id + "validation").encode()), job_id=job.job_id,
                revision=inventory.revision, parent_revision=inventory.parent_revision, stage=Stage.IDLE,
                action="inventory-validation", input_digest=inventory.revision, profile_digest=profile,
                outcome="completed", unit="files", items=len(inventory.occurrences),
                read_bytes=sum(r.size for r in inventory.occurrences if r.status != "unavailable"),
                wall_seconds=time.monotonic() - runtime.started)
            sealed_path = settings.out / "revisions" / inventory.revision / "seal.json"
            if sealed_path.exists():
                seal = Seal.model_validate_json(sealed_path.read_bytes())
                if seal.revision != inventory.revision or not valid(settings.out, seal.artifacts):
                    raise IngestError("sealed revision inconsistent; recovery required")
                receipts = tuple(r.model_copy(update={"outcome": "cached", "cache_hits": r.items,
                    "fresh_inference_items": 0, "wall_seconds": 0., "write_bytes": 0,
                    "read_bytes": 0, "job_id": job.job_id}) for r in prior.receipts
                    if r.action != "inventory-validation") if prior else ()
                runtime.job = runtime.job.model_copy(update={"receipts": receipts})
                runtime.record(validation.model_copy(update={"read_bytes": validation.read_bytes +
                    sum(a.size for a in seal.artifacts)}))
                runtime.save(Progress(stage=Stage.PROPOSE, resume_stage=Stage.PROPOSE, status="complete",
                    cached=len(receipts), denominator=len(receipts), discovered=len(inventory.occurrences),
                    heartbeat=time.time(), next_action="read sealed analysis report"))
            else:
                runtime.record(validation)
                runtime.save(runtime.job.progress.model_copy(update={"actions_total":
                    len({r.sha256 for r in inventory.occurrences if r.sha256}) + 7}))
                _pipeline(runtime, inventory, Launch(settings=settings, options=selected))
        except Stopped:
            logging.info("ingest scheduling stopped job=%s", runtime.job.job_id)
        except Exception as error:
            # CLI/job-owner boundary: persist unexpected failures and re-raise, never manufacture success.
            state = runtime.job.progress
            runtime.save(state.model_copy(update={"status": "failed", "running": 0,
                "resume_stage": state.stage, "failed": state.failed + 1,
                "reason": f"{type(error).__name__}: {error}", "next_action": "ingest-resume"}))
            logging.exception("ingest failed job=%s", runtime.job.job_id)
            raise
        finally:
            runtime.close()
            runs = settings.out / "runs"
            runs.mkdir(exist_ok=True)
            save_model(runs / (runtime.job.job_id + ".json"), runtime.job)
        return runtime.job
