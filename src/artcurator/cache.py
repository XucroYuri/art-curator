"""Content-addressed batch inference and durable per-pass timings."""
import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from . import db
from .models import Predictor
from .prefetch import Prefetch, batches
from .cache_identity import digest, execution_digest, namespace, verify_content
from .resources import Budgets, ByteBudget, record_budget


@dataclass(frozen=True, slots=True)
class Pass:
    out: Path
    name: str
    batch_size: int
    predictor: Predictor
    load_seconds: float = 0
    variant: str = "original"
    workers: int = 8
    prefetch_batches: int = 2
    execution: str = ""


def validate_value(name: str, value: np.ndarray) -> None:
    """Apply output shape/range contracts equally to fresh and cached evidence."""
    if not np.isfinite(value).all():
        raise ValueError("Nonfinite cached or fresh evidence")
    if name == "hpsv3":
        if value.shape != (2,) or value[1] < 0:
            raise ValueError("Invalid HPS pair")
    elif name in {"qrealign", "nsfw_prob", "aes_v25", "topiq_iaa", "topiq_nr", "gaming_jpeg", "gaming_saturation"}:
        if value.shape != ():
            raise ValueError("Invalid scalar output shape")
        if name in {"qrealign", "nsfw_prob"} and not 0 <= float(value) <= 1:
            raise ValueError("Invalid probability output range")
    elif name == "siglip" and (value.ndim != 1 or value.size == 0):
        raise ValueError("Invalid embedding output shape")


def infer(rows: list[db.Row], job: Pass, transform: Callable[[Image.Image], Image.Image] | None = None) -> np.ndarray:
    started = time.perf_counter()
    fingerprint = "|".join((job.predictor.name, job.predictor.revision, job.predictor.preproc, job.variant))
    execution = job.execution or digest(f"{execution_digest()}|batch={job.batch_size}|workers={job.workers}|"
                                         f"prefetch={job.prefetch_batches}|{job.predictor.preproc}")
    directory = job.out / "cache/predictions" / namespace(job.predictor, job.variant, execution)
    directory.mkdir(parents=True, exist_ok=True)
    db.write_json(directory / "key.json", {"model": job.predictor.name, "revision": job.predictor.revision,
                                          "preproc": job.predictor.preproc, "variant": job.variant,
                                          "execution": execution, "output_contract": "outputs-v1"})
    for row in rows:
        verify_content(row)
    missing = list({row.sha256: row for row in rows if not (directory / f"{row.sha256}.npy").exists()}.values())
    budget = ByteBudget(min(Budgets.current().host_bytes // 4, 512 * 1024**2))
    db.meta(job.out, "resource_budget_" + job.name, str(budget.cap))
    options = Prefetch(job.batch_size, job.workers, job.prefetch_batches, transform, budget)
    with record_budget(job.out, job.name, budget), batches(missing, job.predictor, options) as prepared:
        for index, batch in enumerate(prepared):
            try:
                predictions = (job.predictor.cpu.predict(batch.tensors) if job.predictor.cpu
                               else job.predictor.predict(batch.images))
            finally:
                for image in batch.images:
                    image.close()
            if len(predictions) != len(batch.rows) or not np.isfinite(predictions).all():
                raise ValueError(f"Invalid model output: {job.name}")
            for row, value in zip(batch.rows, predictions, strict=True):
                validate_value(job.name, np.asarray(value))
                verify_content(row)
                destination = directory / f"{row.sha256}.npy"
                temporary = destination.with_suffix(".tmp")
                with temporary.open("wb") as handle:
                    np.save(handle, np.asarray(value, dtype=np.float32), allow_pickle=False)
                temporary.replace(destination)
                destination.with_suffix(".sha256").write_text(hashlib.sha256(destination.read_bytes()).hexdigest())
            if index % 8 == 0:
                logging.info("pass progress name=%s completed=%d pending=%d", job.name,
                             index * job.batch_size + len(batch.rows), len(missing))
    restored = []
    for row in rows:
        path = directory / f"{row.sha256}.npy"
        if hashlib.sha256(path.read_bytes()).hexdigest() != path.with_suffix(".sha256").read_text():
            raise ValueError("Cache payload integrity mismatch")
        value = np.load(path, allow_pickle=False)
        validate_value(job.name, value)
        restored.append(value)
    values = np.stack(restored)
    elapsed = time.perf_counter() - started
    logging.info("pass complete name=%s images=%d inferred=%d cached=%d seconds=%.3f s/img=%.5f load_seconds=%.3f",
                 job.name, len(rows), len(missing), len(rows) - len(missing), elapsed, elapsed / len(rows), job.load_seconds)
    with db.connection(job.out) as connection:
        connection.execute("INSERT INTO timings VALUES (?,?,?,?,?)", (
            job.name, elapsed, len(rows), len(rows) - len(missing), job.load_seconds))
    db.meta(job.out, "model_" + job.name, fingerprint)
    return values
