"""Versioned falsifiable folder hypotheses; numerical gates, no fabricated probability."""
from typing import Literal, assert_never

from .ingest_schema import Frozen


class Features(Frozen):
    valid_images: int
    eligible_faces: int = 0
    V: float | None = None
    F: float | None = None
    K: int | None = None
    Q: float | None = None
    A: float | None = None
    artist_labels: int = 0
    entities: int = 0


class Gate(Frozen):
    feature: str
    value: float | None
    operator: Literal[">=", "<"]
    threshold: float
    passed: bool | None


class Detector(Frozen):
    regime: str
    gates: tuple[Gate, ...]
    status: Literal["pass", "fail", "unavailable"]
    consequence: str


class Regimes(Frozen):
    profile: Literal["folder-regime-v1"] = "folder-regime-v1"
    features: Features
    detectors: tuple[Detector, ...]
    passing: tuple[str, ...]
    status: Literal["recommended", "ambiguous", "undetermined", "insufficient-evidence"]
    confidence: None = None
    limits: str = "heuristic/unvalidated; thresholds are engineering policy, not measured accuracy optima"


def gate(feature: str, value: float | None, boundary: tuple[Literal[">=", "<"], float]) -> Gate:
    operator, threshold = boundary
    match operator:
        case ">=":
            passed = value >= threshold if value is not None else None
        case "<":
            passed = value < threshold if value is not None else None
        case unreachable:
            assert_never(unreachable)
    return Gate(feature=feature, value=value, operator=operator, threshold=threshold, passed=passed)


def detect(f: Features) -> Regimes:
    """Return every detector, including absent evidence and overlapping passes."""
    minimum = gate("valid_images", f.valid_images, (">=", 30))
    rows = (
        ("session-set", (minimum, gate("V", f.V, (">=", .90)), gate("F", f.F, (">=", .80)),
                         gate("eligible_faces", f.eligible_faces, (">=", 30))),
         "Inspect one coherent set; session does not imply identity."),
        ("mixed-pile", (minimum, gate("V", f.V, ("<", .80)), gate("F", f.F, ("<", .50)),
                        gate("K", f.K, (">=", 3))), "Cluster-first review; no automatic character inheritance."),
        ("scenario/documentary", (minimum, gate("V", f.V, (">=", .85)), gate("Q", f.Q, (">=", .50)),
                                  gate("F", f.F, ("<", .80))), "Scene organization; no no-person conclusion."),
        ("artist-portfolio", (minimum, gate("A", f.A, (">=", .80)),
                              gate("artist_labels", f.artist_labels, (">=", 30)),
                              gate("entities", f.entities, (">=", 3))),
         "Artist axis independent of character; visual style cannot certify artist."),
    )
    detectors = tuple(Detector(regime=name, gates=gates, consequence=consequence,
        status="unavailable" if any(g.passed is None for g in gates) else
        "pass" if all(g.passed for g in gates) else "fail") for name, gates, consequence in rows)
    passing = tuple(d.regime for d in detectors if d.status == "pass")
    status = "ambiguous" if len(passing) > 1 else "recommended" if passing else "undetermined"
    if not passing and (f.valid_images < 30 or all(d.status == "unavailable" for d in detectors)):
        status = "insufficient-evidence"
    return Regimes(features=f, detectors=detectors, passing=passing, status=status)
