"""Atomic identity evidence, read-only manifest access and content binding."""
import hashlib
import importlib.metadata
import io
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from .db import Row
from .identity_schema import IdentityDocument, Provenance


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def atomic_bytes(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def save_model(path: Path, model: BaseModel) -> None:
    atomic_bytes(path, model.model_dump_json(indent=2).encode("utf-8"))


def save_array(path: Path, values: NDArray) -> None:
    buffer = io.BytesIO()
    np.save(buffer, values, allow_pickle=False)
    atomic_bytes(path, buffer.getvalue())


def manifest(out: Path) -> list[Row]:
    connection = sqlite3.connect((out / "manifest.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = [Row.model_validate_json(r[0]) for r in connection.execute(
            "SELECT payload FROM images ORDER BY position")]
    finally:
        connection.close()
    hashes: dict[str, str] = {}
    for row in rows:
        if row.sha16 in hashes and hashes[row.sha16] != row.sha256:
            raise ValueError("manifest short-hash collision")
        hashes[row.sha16] = row.sha256
    return rows


def fingerprint(rows: list[Row]) -> str:
    return digest("\n".join(sorted({r.sha256 for r in rows})).encode())


def load_document(out: Path) -> IdentityDocument:
    return IdentityDocument.model_validate_json((out / "identities.json").read_bytes())


def load_provenance(out: Path) -> Provenance:
    return Provenance.model_validate_json((out / "identity-provenance.json").read_bytes())


def normalized(values: NDArray) -> NDArray[np.float32]:
    result = np.asarray(values, dtype=np.float32)
    if result.ndim != 2 or not np.isfinite(result).all():
        raise ValueError("invalid embedding matrix")
    lengths = np.linalg.norm(result, axis=1, keepdims=True)
    if np.any(lengths <= 1e-12):
        raise ValueError("zero embedding")
    return result / lengths


def load_vectors(out: Path, document: IdentityDocument) -> NDArray[np.float32]:
    path = out / "identities.npy"
    ledger = json.loads((out / "identity-embedding.json").read_bytes())
    if ledger["faces"] != [f.face_id for f in document.faces] or ledger["sha256"] != file_digest(path):
        raise ValueError("embedding payload/order integrity mismatch")
    if ledger["semantic_profile"] != load_provenance(out).semantic_profile:
        raise ValueError("embedding semantic profile mismatch")
    values = np.load(path, allow_pickle=False)
    if values.dtype != np.float16 or len(values) != document.face_count:
        raise ValueError("embedding contract mismatch")
    return normalized(values)


@contextmanager
def stage(out: Path, name: str) -> Iterator[None]:
    """Exclusive coordinator ownership; process high-water RSS includes model loading."""
    import psutil
    lock = out / "identity.lock"
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    started = time.perf_counter()
    succeeded = False
    try:
        yield
        succeeded = True
    finally:
        elapsed = time.perf_counter() - started
        memory = psutil.Process().memory_info()
        peak = getattr(memory, "peak_wset", memory.rss)
        record = {"stage": name, "seconds": elapsed, "peak_ram_bytes": peak,
                  "peak_method": "process high-water RSS on Windows; final RSS elsewhere",
                  "completed": succeeded}
        with (out / "identity-timings.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        lock.unlink()


def record_environment(out: Path) -> None:
    path = out / "environment-versions.json"
    existing = json.loads(path.read_bytes()) if path.exists() else {}
    existing["identity_v2"] = {p: importlib.metadata.version(p) for p in (
        "onnxruntime", "scikit-learn", "numpy", "Pillow", "torch", "transformers", "psutil")}
    existing["identity_v2"]["provider"] = "detection: CPUExecutionProvider; embedding: see identity-embedding.json execution"
    atomic_bytes(path, json.dumps(existing, indent=2).encode())
