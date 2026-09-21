"""Prospective descriptive statistics; never estimates of model correctness."""
import math
from typing import Literal

import numpy as np
from pydantic import ConfigDict

from .ingest_schema import Frozen, IngestError


class Proportion(Frozen):
    numerator: int | None
    denominator: int
    value: float | None
    interval: tuple[float, float] | None = None
    method: str
    limits: str = "Independence assumed; exact duplicates removed, near-duplicate dependence remains."


class Coherence(Frozen):
    denominator: int
    valid: int
    missing: int
    median: float | None
    p10: float | None
    scores: tuple[float | None, ...]
    method: str = "L2-normalized non-self leave-one-out centroid cosine; linear quantiles"
    limits: str = "Scene/style similarity can dominate; not identity purity; no population CI."


class HumanLabel(Frozen):
    image_id: str
    identity: str | None = None
    artist: str | None = None
    entity: str | None = None
    actor: str
    evidence_ref: str
    independent: bool


class Labels(Frozen):
    snapshot_digest: str
    labels: tuple[HumanLabel, ...] = ()
    # User declarations, never inferred from path spelling.
    targets: dict[str, str] = {}
    target_types: dict[str, Literal["character", "work", "artist", "original-series", "undetermined"]] = {}


class ImageEvidence(Frozen):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=True)
    image_id: str
    vector: tuple[float, ...] | None = None
    representation: str = "unavailable"
    profile: str | None = None
    face_clusters: tuple[int | None, ...] | None = None
    candidates: tuple[str, ...] | None = None
    conflict: bool | None = None


def proportion(numerator: int | None, denominator: int, population: int) -> Proportion:
    """Wilson z=1.96 for seeded SRS; census is descriptive, never a population CI."""
    if numerator is None or denominator == 0:
        return Proportion(numerator=numerator, denominator=denominator, value=None,
                          method="unavailable")
    if not 0 <= numerator <= denominator <= population:
        raise IngestError("invalid proportion counts")
    p = numerator / denominator
    if denominator == population:
        return Proportion(numerator=numerator, denominator=denominator, value=p, method="census-exact")
    z2 = 1.96**2
    center = (p + z2 / (2 * denominator)) / (1 + z2 / denominator)
    half = 1.96 * math.sqrt(p * (1-p) / denominator + z2 / (4 * denominator**2)) / (1 + z2/denominator)
    return Proportion(numerator=numerator, denominator=denominator, value=p,
                      interval=(max(0., center-half), min(1., center+half)), method="Wilson-95%-z=1.96-SRS")


def coherence(vectors: tuple[tuple[float, ...] | None, ...]) -> Coherence:
    """Missing/invalid rows stay in the sample denominator; zero LOO is unavailable."""
    dimensions = {len(v) for v in vectors if v and all(math.isfinite(x) for x in v)}
    valid = [(i, np.asarray(v, dtype=np.float64)) for i, v in enumerate(vectors)
             if v and len(dimensions) == 1 and all(math.isfinite(x) for x in v)
             and math.sqrt(sum(x*x for x in v)) > 1e-12]
    scores: list[float | None] = [None] * len(vectors)
    if len(valid) >= 2:
        matrix = np.stack([v / np.linalg.norm(v) for _, v in valid])
        others = matrix.sum(axis=0) - matrix
        for (index, _), row, other in zip(valid, matrix, others, strict=True):
            length = float(np.linalg.norm(other))
            if length > 1e-12:
                scores[index] = float(np.clip(np.dot(row, other / length), -1., 1.))
    available = [s for s in scores if s is not None]
    return Coherence(denominator=len(vectors), valid=len(valid), missing=len(vectors)-len(valid),
        median=float(np.quantile(available, .5, method="linear")) if available else None,
        p10=float(np.quantile(available, .1, method="linear")) if available else None,
        scores=tuple(scores))
