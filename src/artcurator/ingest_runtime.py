"""Job checkpoints, responsive heartbeat and metered stage barriers."""
import logging
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event, RLock, Thread

from .identity_store import digest, save_model
from .ingest_adapters import Request, Result
from .ingest_schema import Frozen, Heartbeat, IngestError, Job, Progress, Receipt, Stage
from .ingest_storage import admit, artifacts, retained_bytes, valid


class Control(Frozen):
    command: str
    requested_at: float


class Stopped(Exception):
    """Cooperative scheduling stop, never a successful stage completion."""


def control(root: Path, command: str) -> None:
    if command not in {"pause", "resume", "cancel"}:
        raise IngestError(f"unknown control: {command}")
    save_model(root / "control.json", Control(command=command, requested_at=time.time()))


def requested(root: Path) -> str:
    path = root / "control.json"
    return Control.model_validate_json(path.read_bytes()).command if path.exists() else "resume"


class Runtime:
    """Single coordinator's mutable checkpoint, serialized with its heartbeat thread."""

    def __init__(self, root: Path, job: Job, execute: Callable[[Request], Result]) -> None:
        self.root, self.job, self.execute = root, job, execute
        self.previous: Job | None = None
        self.lock = RLock()
        self.done = Event()
        self.started = time.monotonic()
        self.thread = Thread(target=self._heartbeat, daemon=True)

    def save(self, progress: Progress) -> None:
        with self.lock:
            self.job = self.job.model_copy(update={"progress": progress})
            save_model(self.root / "job.json", self.job)
            save_model(self.root / "progress.json", Heartbeat(job_id=self.job.job_id, progress=progress))

    def _heartbeat(self) -> None:
        while not self.done.wait(0.5):
            with self.lock:
                state = self.job.progress
                stopping = requested(self.root) in {"pause", "cancel"}
                progress = state.model_copy(update={"heartbeat": time.time(),
                    "elapsed_seconds": time.monotonic() - self.started,
                    "status": "pausing" if stopping and state.status == "running" else state.status})
                self.job = self.job.model_copy(update={"progress": progress})
                save_model(self.root / "progress.json", Heartbeat(job_id=self.job.job_id, progress=progress))

    def start(self) -> None:
        self.save(self.job.progress)
        self.thread.start()

    def close(self) -> None:
        self.done.set()
        self.thread.join()

    def checkpoint(self) -> None:
        command = requested(self.root)
        if command in {"pause", "cancel"}:
            state = self.job.progress
            self.save(state.model_copy(update={"status": "paused" if command == "pause" else "cancelled",
                "running": 0, "resume_stage": state.stage, "reason": command,
                "next_action": "ingest-resume"}))
            raise Stopped

    def stage(self, stage: Stage) -> None:
        from .ingest_schema import transition
        with self.lock:
            state = self.job.progress
            target = transition(state.stage, stage)
            self.save(state.model_copy(update={"stage": target, "resume_stage": target,
                "status": "running", "heartbeat": time.time()}))
        self.checkpoint()

    def action(self, request: Request) -> Receipt:
        self.checkpoint()
        count, unit = len(request.paths), "unique images"
        if request.action != "scan":
            from .identity_store import load_document, manifest
            count = len(manifest(request.settings.out))
            if request.action != "detect" and (request.settings.out / "identities.json").exists():
                count, unit = load_document(request.settings.out).face_count, "faces"
        identity = [request.action, self.job.revision, self.job.profile_digest,
                    *[str(p) for p in request.paths]]
        key = digest("\n".join(identity).encode())
        commit = self.root / "commits" / (key + ".json")
        if commit.exists():
            prior = Receipt.model_validate_json(commit.read_bytes())
            if not valid(self.root, prior.artifacts):
                raise IngestError("committed stage payload inconsistent; recovery required")
            record = prior.model_copy(update={"outcome": "cached", "cache_hits": prior.items,
                "fresh_inference_items": 0, "wall_seconds": 0., "job_id": self.job.job_id, "write_bytes": 0})
        else:
            admit(self.root, 1024 * 1024, request.options)
            before = retained_bytes(self.root)
            started, cpu = time.perf_counter(), time.process_time()
            with self.lock:
                self.save(self.job.progress.model_copy(update={"running": count, "queued": 0,
                    "completed": 0, "cached": 0, "unavailable": 0, "failed": 0,
                    "denominator": count, "unit": unit, "next_action": request.action,
                    "provider": "CPU scan" if request.action == "scan" else request.options.provider}))
            failure: Exception | None = None
            try:
                result = self.execute(request)
            except Exception as error:
                # Stage execution boundary: meter failures before propagating the original exception.
                failure = error
                result = Result(outcome="failed", reason=f"{type(error).__name__}: {error}")
            elapsed = time.perf_counter() - started
            payloads = artifacts(self.root, result.paths)
            record = Receipt(operation_id=key, job_id=self.job.job_id, revision=self.job.revision,
                parent_revision=self.job.parent_revision, stage=self.job.progress.stage,
                action=request.action, input_digest=digest("\n".join(identity).encode()),
                profile_digest=self.job.profile_digest, outcome=result.outcome, reason=result.reason,
                artifacts=payloads, items=result.items or count, unit=unit,
                cache_hits=result.cached, wall_seconds=elapsed, cpu_seconds=time.process_time() - cpu,
                fresh_inference_items=max(0, (result.items or count) - result.cached)
                    if request.action in {"detect", "embed", "tag"} and result.outcome == "completed" else 0,
                read_bytes=sum(p.stat().st_size for p in request.paths),
                write_bytes=max(0, retained_bytes(self.root) - before), retained_bytes=retained_bytes(self.root),
                commit_state="uncommitted" if result.outcome == "failed" else "committed")
            budgets = {"scan": (.04149, .050), "detect": (.059, .18), "embed": (.135, .16),
                       "tag": (.13, .25) if request.options.provider == "CUDAExecutionProvider" else (3.3, 4.5)}
            if request.action in budgets:
                low, high = budgets[request.action]
                record = record.model_copy(update={"estimated_wall_seconds": (count * low, count * high)})
            if record.outcome == "failed":
                self.record(record)
                if failure is not None:
                    raise failure
                raise IngestError(record.reason)
            commit.parent.mkdir(exist_ok=True)
            save_model(commit, record)
        self.record(record)
        return record

    def record(self, receipt: Receipt) -> None:
        with self.lock:
            existing = tuple(r for r in self.job.receipts if r.operation_id != receipt.operation_id)
            receipts = (*existing, receipt)
            self.job = self.job.model_copy(update={"receipts": receipts})
            state = self.job.progress.model_copy(update={"running": 0, "checkpoint": receipt.operation_id,
                "unit": receipt.unit, "denominator": receipt.items,
                "completed": receipt.items - receipt.cache_hits if receipt.outcome == "completed" else 0,
                "cached": receipt.cache_hits,
                "unavailable": receipt.items if receipt.outcome == "unavailable" else 0,
                "failed": receipt.items if receipt.outcome == "failed" else 0,
                "actions_completed": len(receipts), "queued": 0,
                "heartbeat": time.time(), "elapsed_seconds": time.monotonic() - self.started})
            self.save(state)
        logging.info("ingest progress stage=%s completed=%d cached=%d unavailable=%d checkpoint=%s",
                     state.stage, state.completed, state.cached, state.unavailable, state.checkpoint)
