"""Durable, versioned G1 job contracts; later album stages fail explicitly."""
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import Settings


class Stage(StrEnum):
    IDLE = "IDLE"
    INGEST = "INGEST"
    ANALYZE = "ANALYZE"
    PROPOSE = "PROPOSE"
    CONFIRM = "CONFIRM"
    FIRST_PASS = "FIRST-PASS"
    REVIEW = "REVIEW"
    ARCHIVE = "ARCHIVE"


class IngestError(ValueError):
    """A rejected job, checkpoint or artifact, with a persisted reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class FutureStageError(NotImplementedError):
    def __init__(self, stage: Stage) -> None:
        self.stage = stage
        super().__init__(f"{stage} is not implemented: G1 stops at PROPOSE; G2-G6 required")


def transition(source: str, target: str) -> Stage:
    """Validate a logical barrier, never interpret a future stage as a no-op."""
    before, after = Stage(source), Stage(target)
    if after in {Stage.CONFIRM, Stage.FIRST_PASS, Stage.REVIEW, Stage.ARCHIVE}:
        raise FutureStageError(after)
    allowed = {(Stage.IDLE, Stage.INGEST), (Stage.INGEST, Stage.ANALYZE),
               (Stage.ANALYZE, Stage.PROPOSE), (Stage.PROPOSE, Stage.INGEST)}
    if (before, after) not in allowed:
        raise IngestError(f"invalid transition: {before} -> {after}")
    return after


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Options(Frozen):
    analysis: bool = True
    profile_from: Path | None = None
    anchors_from_folders: bool = False
    scan_batch_size: int = Field(default=64, ge=1, le=256)
    quota_bytes: int = Field(default=8 * 1024**3, gt=0)
    reserve_bytes: int = Field(default=1024**3, ge=0)
    provider: Literal["CPUExecutionProvider", "CUDAExecutionProvider"] = "CPUExecutionProvider"
    cuda_dll_directory: Path | None = None
    deadline_seconds: float = Field(default=240, gt=0)
    stage_deadline_seconds: float = Field(default=86400, gt=0)


class Launch(Frozen):
    settings: Settings
    options: Options


class Occurrence(Frozen):
    path: str
    sha256: str = ""
    size: int = 0
    mtime_ns: int = 0
    status: Literal["indexed", "duplicate", "unavailable", "failed"] = "indexed"
    reason: str = ""


class Inventory(Frozen):
    revision: str
    parent_revision: str | None
    occurrences: tuple[Occurrence, ...]
    added: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


class Artifact(Frozen):
    path: str
    sha256: str
    size: int


class Receipt(Frozen):
    operation_id: str
    job_id: str
    revision: str
    parent_revision: str | None
    stage: Stage
    action: str
    input_digest: str
    profile_digest: str
    artifacts: tuple[Artifact, ...] = ()
    outcome: Literal["completed", "cached", "failed", "unavailable", "cancelled"]
    reason: str = ""
    items: int = 0
    unit: str = "unique images"
    cache_hits: int = 0
    fresh_inference_items: int = 0
    estimated_wall_seconds: tuple[float, float] | None = None
    wall_seconds: float = 0
    cpu_seconds: float | None = None
    cpu_boundary: str = "coordinator process only, excludes subprocess CPU"
    gpu_active_seconds: float | None = None
    load_seconds: float | None = None
    compute_seconds: float | None = None
    io_seconds: float | None = None
    read_bytes: int = 0
    read_bytes_boundary: str = "source payload bytes scheduled, not a physical IO counter"
    write_bytes: int = 0
    write_bytes_boundary: str = "net derived size growth, excludes overwritten/repeated writes"
    retained_bytes: int = 0
    temporary_bytes: int | None = None
    peak_host_bytes: int | None = None
    peak_vram_bytes: int | None = None
    external_requests: int = 0
    service_charge: float = 0
    unmeasured_reason: str = "stage adapters do not expose load/compute/IO/GPU/peak meters"
    commit_state: Literal["committed", "uncommitted"] = "committed"


class Admission(Frozen):
    quota_bytes: int
    free_disk_reserve_bytes: int
    retained_bytes: int
    incremental_reservation_bytes: int
    original_bytes_excluded: int
    thumbnail_cap_bytes_per_image: int = 64 * 1024
    preview_cap_bytes_per_image: int = 192 * 1024
    compact_cap_bytes_per_image: int = 16 * 1024
    crop_cap_bytes_per_face: int = 64 * 1024
    matrix_bytes: int | None = None
    model_environment_bytes_excluded: int | None = None
    qualification: str = "experimental admission; native writer hard quotas and unknown face/matrix peaks unqualified"


class Progress(Frozen):
    stage: Stage = Stage.IDLE
    status: Literal["idle", "running", "pausing", "paused", "failed", "cancelled", "complete", "stalled"] = "idle"
    resume_stage: Stage = Stage.IDLE
    queued: int = 0
    running: int = 0
    completed: int = 0
    cached: int = 0
    failed: int = 0
    unavailable: int = 0
    denominator: int | None = None
    discovered: int = 0
    unit: str = "unique images"
    actions_completed: int = 0
    actions_total: int | None = None
    elapsed_seconds: float = 0
    load_seconds: float | None = None
    compute_seconds: float | None = None
    io_seconds: float | None = None
    provider: str = "not loaded"
    heartbeat: float = 0
    checkpoint: str = ""
    next_action: str = "start"
    eta_seconds: tuple[float, float] | None = None
    reason: str = ""


class Job(Frozen):
    schema_version: Literal[1] = 1
    job_id: str
    root: Path
    revision: str = ""
    parent_revision: str | None = None
    profile_digest: str
    progress: Progress = Progress()
    receipts: tuple[Receipt, ...] = ()


class Heartbeat(Frozen):
    job_id: str
    progress: Progress
