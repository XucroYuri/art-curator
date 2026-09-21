"""Schema-side projection from model-space scores; the cache stores raw vectors untouched.

Projection runs at read time so that adding or changing optional output fields costs zero
inference. :data:`PROJECTION` names the projection contract that legacy (already-projected)
cache entries must match to be reused.
"""
import base64
import csv
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from .wd_schema import Attributes, Evidence, Tag

PROJECTION: Final = "wd-compact-v1"

COLORS: Final = {"black", "brown", "blonde", "white", "grey", "gray", "red", "blue",
                 "green", "pink", "purple", "orange", "silver", "multicolored"}


def compact(scores: NDArray, tags: list[tuple[str, int]]) -> Evidence:
    """Discard the full vector immediately after thresholded top-K selection."""
    if len(scores) != len(tags) or not np.isfinite(scores).all():
        raise ValueError("invalid WD scores")
    ranked = sorted(zip(tags, scores, strict=True), key=lambda item: (-float(item[1]), item[0][0]))
    characters = [Tag(tag=name, score=float(score)) for (name, category), score in ranked
                  if category == 4 and score > .35][:5]
    attributes = [Tag(tag=name, score=float(score)) for (name, category), score in ranked
                  if category == 0 and score > .35][:40]
    colors = [row.tag[:-5] for row in attributes if row.tag.endswith("_hair") and row.tag[:-5] in COLORS]
    styles = [row.tag.replace("_", " ") for row in attributes
              if row.tag.endswith("_hair") and row.tag[:-5] not in COLORS]
    return Evidence(characters=characters, attributes=Attributes(
        tags=attributes, hair_color=colors[0] if colors else None, hair_style=styles[0] if styles else None))


def encode_raw(scores: NDArray) -> str:
    """Little-endian float32 bytes as base64; exact on little-endian hosts, portable otherwise."""
    return base64.b64encode(np.ascontiguousarray(scores, dtype="<f4").tobytes()).decode("ascii")


def decode_raw(text: str) -> NDArray[np.float32]:
    values = np.frombuffer(base64.b64decode(text, validate=True), dtype="<f4")
    if not np.isfinite(values).all():
        raise ValueError("invalid WD model-space scores")
    return values


def load_tags(path: Path) -> list[tuple[str, int]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [(row["name"], int(row["category"])) for row in csv.DictReader(handle)]
