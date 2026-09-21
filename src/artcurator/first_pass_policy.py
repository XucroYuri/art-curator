"""MAP-002 pure policy. Engineering thresholds are not calibrated precision claims."""
from hashlib import sha256
from typing import assert_never

from .album_map_schema import Metric, Scores
from .first_pass_schema import Audit, Entity, Evidence, Outcome, Policy
from .negotiation_consent import Mode


def evaluate(row: Evidence, policy: Policy, mode: Mode) -> Outcome:
    """Evaluate supplied profile-validated evidence; publication validates live authority."""
    base = dict(image_id=row.image_id, subject_id=row.subject_id)
    match mode:
        case "inherit-only":
            return Outcome(**base, tier="none", reasons=("inherit-only-no-ai",))
        case "human-first" | "auto-first":
            pass
        case unreachable:
            assert_never(unreachable)
    if not row.valid:
        return Outcome(**base, tier="review", reasons=("invalid-evidence",))
    usable = tuple(v for v in row.visuals if v.profile_valid and row.image_id not in v.reference_images
                   and row.crop_id not in v.reference_crops)
    candidates = tuple(v for v in usable if max(v.centroid, v.individual) > policy.enumeration)
    model = row.model
    reasons = list(row.conflicts)
    # Contradiction uses the strongest independent individual reference, NOT auto gates.
    strongest = max((v.individual for v in usable), default=-1)
    leaders = {v.entity_id for v in usable if v.individual == strongest}
    if model is not None and strongest > .35 and model.entity_id not in leaders:
        reasons.append("model_demoted")
    scores = Scores()
    if model is not None:
        scores = Scores(wd=Metric(value=model.score, unit="probability", profile=model.profile),
            model_margin=Metric(value=model.score - (model.runner_up if model.runner_up is not None else .35),
                unit="score-difference", profile=model.profile,
                bound="exact" if model.runner_up is not None else "lower"))
    winner = max(candidates, key=lambda v: (v.centroid, v.entity_id), default=None)
    entity = Entity(entity_id=winner.entity_id, entity_type=winner.entity_type, name=winner.name) if winner else None
    source = winner.source if winner else "model"
    if winner is not None:
        others = tuple(v for v in usable if v.entity_id != winner.entity_id)
        margin = min(winner.centroid - max((v.centroid for v in others), default=1),
                     winner.individual - max((v.individual for v in others), default=1))
        scores = Scores(**{**scores.model_dump(),
            "visual": Metric(value=winner.centroid, unit="cosine", profile=row.profile),
            "stable_margin": Metric(value=margin, unit="cosine-difference", profile=row.profile)})
        calibration = row.calibration
        gates = (
            (len(usable) >= 2, "insufficient-competing-identities"),
            (margin > 0, "ambiguous-or-disagreeing-winners"),
            (bool(winner.human_support_refs), "human-support-required"),
            (calibration is not None and calibration.profile == row.profile
             and calibration.reference_digest == row.reference_digest, "calibration-required"),
            (winner.centroid >= max(policy.min_similarity, calibration.min_similarity if calibration else .90),
             "similarity-below-policy"),
            (margin >= max(policy.min_margin, calibration.min_margin if calibration else .05),
             "margin-below-policy"),
        )
        reasons.extend(reason for passed, reason in gates if not passed)
        match mode:
            case "human-first":
                reasons.append("human-first")
            case "auto-first":
                pass
            case unreachable:
                assert_never(unreachable)
        if not reasons:
            return Outcome(**base, tier="auto", reasons=("reference-gates-passed",),
                           winner=entity, source=source, scores=scores)
    if model is not None and model.score > policy.enumeration:
        if entity is None:
            entity = Entity(entity_id=model.entity_id, entity_type=model.entity_type, name=model.name)
        margin = model.score - (model.runner_up if model.runner_up is not None else .35)
        reasons.append("model-only-hypothesis" if model.score >= policy.model_score
                       and margin >= policy.model_margin else "enumerated-model-candidate")
    if reasons or candidates or entity is not None or len(usable) != len(row.visuals):
        return Outcome(**base, tier="review", reasons=tuple(reasons) or ("reference-gate-failed",),
                       winner=entity, source=source, scores=scores)
    return Outcome(**base, tier="none", reasons=("no-actionable-evidence",), eligible_none=True)


def audit(auto: tuple[str, ...], none: tuple[str, ...], snapshot: str) -> Audit:
    """Unique full-image strata; integer ceiling avoids float rounding of five percent."""
    selected = []
    denominators = []
    for tier, images in (("auto", auto), ("none", none)):
        unique = set(images)
        ranked = sorted(unique, key=lambda image: (sha256(
            f"album-first-pass-v1\n{snapshot}\n{tier}\n{image}".encode()).hexdigest(), image))
        selected.append(tuple(ranked[:(len(unique) + 19) // 20]))
        denominators.append(len(unique))
    return Audit(snapshot_digest=snapshot, auto_denominator=denominators[0],
                 none_denominator=denominators[1], auto_ids=selected[0], none_ids=selected[1])
