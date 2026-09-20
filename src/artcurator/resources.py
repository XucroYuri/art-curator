"""Availability-aware admission and owned byte reservations."""
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import TypedDict
import json
import uuid

import psutil
from PIL import Image
from pathlib import Path


class Deferral(TypedDict):
    reason: str
    requested_bytes: int
    used_bytes: int
    cap_bytes: int


class Deferred(RuntimeError):
    """Work remains unavailable because its reservation cannot be admitted."""


@dataclass(frozen=True, slots=True)
class Budgets:
    host_bytes: int
    gpu_bytes: tuple[int, ...]

    @classmethod
    def choose(cls, tier: int, installed: int, available: int,
               devices: list[tuple[int, int]]) -> "Budgets":
        """Apply independent host and per-device policy ceilings in bytes."""
        return cls(int(min(tier, .65 * installed, .75 * available)),
                   tuple(int(min(.80 * total, .85 * free)) for total, free in devices))

    @classmethod
    def current(cls) -> "Budgets":
        memory = psutil.virtual_memory()
        return cls.choose(20 * 1024**3, memory.total, memory.available, [])


@dataclass(slots=True)
class ByteBudget:
    """Mutable reservation owner; release on consumption, cancellation or exception."""
    cap: int
    used: int = 0
    peak: int = 0
    events: list[Deferral] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)

    @contextmanager
    def reserve(self, size: int) -> Iterator[None]:
        with self.lock:
            if size < 0 or size + self.used > self.cap:
                self.events.append(Deferral(reason="byte_budget_exceeded", requested_bytes=size,
                                            used_bytes=self.used, cap_bytes=self.cap))
                raise Deferred("byte_budget_exceeded")
            self.used += size
            self.peak = max(self.peak, self.used)
        try:
            yield
        finally:
            with self.lock:
                self.used -= size


def decode_estimate(path: Path) -> int:
    """Read dimensions without decoding; reserve source copies and RGB/tensor transients."""
    with Image.open(path) as image:
        width, height = image.size
    return 4 * path.stat().st_size + 48 * width * height + 16 * 1024**2


@contextmanager
def record_budget(out: Path, name: str, budget: ByteBudget) -> Iterator[None]:
    """Run metadata survives a deferral/exception as well as successful consumption."""
    from . import db
    admitted = Budgets.current()
    try:
        yield
    finally:
        db.meta(out, "resources_" + name + "_" + uuid.uuid4().hex, json.dumps({"host_cap_bytes": admitted.host_bytes,
            "queue_cap_bytes": budget.cap, "queue_peak_reserved_bytes": budget.peak,
            "deferrals": budget.events, "prefetch_policy": "serial-byte-reserved-v1"}))


def admit_gpu(out: Path) -> None:
    """Set per-device allocator ceiling and record available capacity before model loading."""
    import torch
    from . import db
    devices = [torch.cuda.mem_get_info(i) for i in range(torch.cuda.device_count())]
    memory = psutil.virtual_memory()
    budgets = Budgets.choose(20 * 1024**3, memory.total, memory.available,
                             [(total, free) for free, total in devices])
    db.meta(out, "resource_admission", json.dumps({"host_cap_bytes": budgets.host_bytes,
            "gpu_cap_bytes": budgets.gpu_bytes, "available_gpu_bytes": [free for free, _ in devices],
            "tier": "T2", "estimated_model_peaks": "unqualified"}))
    for index, (_, total) in enumerate(devices):
        torch.cuda.set_per_process_memory_fraction(budgets.gpu_bytes[index] / total, index)
