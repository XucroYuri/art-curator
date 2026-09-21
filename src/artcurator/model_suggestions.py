"""Uncalibrated WD proposal policy, separate from all visual verification gates."""
from typing import Final, Literal

from .candidates_schema_v2 import Disagreement, ModelSuggestion, Option

MIN_SCORE: Final = .85
MIN_MARGIN: Final = .20
OMITTED_CEILING: Final = .35


def propose(model: list[Option]) -> ModelSuggestion | None:
    """Use compact-output censoring conservatively, never invent a zero runner-up."""
    ranked = sorted(model, key=lambda row: (-(row.score or 0), row.name))
    if not ranked:
        return None
    top = ranked[0]
    score = top.score or 0
    runner = ranked[1].score if len(ranked) > 1 else OMITTED_CEILING
    # Decimal score boundaries must not fail due to binary subtraction noise.
    margin = round(score - (runner or 0), 12)
    if score < MIN_SCORE or margin < MIN_MARGIN:
        return None
    return ModelSuggestion(name=top.name, display=top.display or top.name, score=score,
        margin_vs_runner_up=margin,
        margin_basis="observed" if len(ranked) > 1 else "runner-up-upper-bound-0.35")


def disagreement(model: ModelSuggestion | None, evidence: list[Option],
                 source: Literal["memory", "reference", "confirmed"]) -> list[Disagreement]:
    """A different strongest visual candidate demotes, even below verification gates.

    Tied leaders including the model are ambiguous, not contradictory. A tied set
    excluding the model records every leading name. No score fusion is performed.
    """
    if model is None or not evidence:
        return []
    strongest = max(row.score or 0 for row in evidence)
    leaders = [row for row in evidence if row.score == strongest]
    if strongest <= .35 or any(row.name == model.name for row in leaders):
        return []
    return [Disagreement(model_name=model.name, evidence_name=row.name, source=source,
                         score=strongest) for row in leaders]
