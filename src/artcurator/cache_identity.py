"""Versioned cache lineage and source-content verification."""
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

from . import db
from .models import Predictor


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def execution_digest() -> str:
    """Bind actual runtime packages/platform; no cross-profile reuse certificate implied."""
    inventory = sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())
    return digest(json.dumps([platform.platform(), platform.python_version(), inventory], sort_keys=True))


def namespace(predictor: Predictor, variant: str, execution: str) -> str:
    return digest(json.dumps(["cache-v2", digest(predictor.name + "@" + predictor.revision),
                              digest(predictor.preproc + "|" + variant), "outputs-v1", execution]))


def verify_content(row: db.Row) -> None:
    with Path(row.abs_path).open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != row.sha256:
        raise ValueError("Source content changed since snapshot")
