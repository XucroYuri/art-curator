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


def infer(rows: list[db.Row], job: Pass, transform: Callable[[Image.Image], Image.Image] | None = None) -> np.ndarray:
    started = time.perf_counter()
    fingerprint = "|".join((job.predictor.name, job.predictor.revision, job.predictor.preproc, job.variant))
    namespace = hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
    directory = job.out / "cache/predictions" / namespace
    directory.mkdir(parents=True, exist_ok=True)
    db.write_json(directory / "key.json", {"model": job.predictor.name, "revision": job.predictor.revision,
                                          "preproc": job.predictor.preproc, "variant": job.variant})
    missing = list({row.sha16: row for row in rows if not (directory / f"{row.sha16}.npy").exists()}.values())
    options = Prefetch(job.batch_size, job.workers, job.prefetch_batches, transform)
    with batches(missing, job.predictor, options) as prepared:
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
                destination = directory / f"{row.sha16}.npy"
                temporary = destination.with_suffix(".tmp")
                with temporary.open("wb") as handle:
                    np.save(handle, np.asarray(value, dtype=np.float32), allow_pickle=False)
                temporary.replace(destination)
            if index % 8 == 0:
                logging.info("pass progress name=%s completed=%d pending=%d", job.name,
                             index * job.batch_size + len(batch.rows), len(missing))
    values = np.stack([np.load(directory / f"{row.sha16}.npy", allow_pickle=False) for row in rows])
    elapsed = time.perf_counter() - started
    logging.info("pass complete name=%s images=%d inferred=%d cached=%d seconds=%.3f s/img=%.5f load_seconds=%.3f",
                 job.name, len(rows), len(missing), len(rows) - len(missing), elapsed, elapsed / len(rows), job.load_seconds)
    with db.connection(job.out) as connection:
        connection.execute("INSERT INTO timings VALUES (?,?,?,?,?)", (
            job.name, elapsed, len(rows), len(rows) - len(missing), job.load_seconds))
    db.meta(job.out, "model_" + job.name, fingerprint)
    return values
