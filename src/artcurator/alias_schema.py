"""Versioned alias review boundaries; scores describe support, not truth."""
from typing import Annotated, Literal

from pydantic import Field

from .identity_schema import Digest, Record

type AliasName = Annotated[str, Field(min_length=1, pattern=r"^[^|\r\n]+$")]
type AliasDecision = Literal["confirmed", "rejected"]


class AliasError(ValueError):
    """Mutable exception traceback is required by the stage context manager."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class AliasChoice(Record):
    reference_name: AliasName
    wd_tag: AliasName
    decision: AliasDecision


class AliasEnvelope(Record):
    version: Literal[1] = 1
    source: Literal["review-studio"] = "review-studio"
    corpus_fingerprint: Digest
    semantic_profile: Digest
    decisions: list[AliasChoice]


class AliasRecord(Record):
    wd_tag: AliasName
    decision: AliasDecision
    actor: Literal["review-studio"] = "review-studio"
    updated_at: str


class Support(Record):
    images: int = 0
    top1_images: int = 0
    minimum: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    maximum: float | None = None


class AliasCandidate(Record):
    wd_tag: str
    rank: int
    direct: Support
    cohort: Support
    strength: Literal["weak", "relatively-strong"]
    decision: Literal["unconfirmed", "confirmed", "rejected"] = "unconfirmed"


class AliasBank(Record):
    reference_name: str
    sources: list[str]
    reference_images: int
    tagged_reference_images: int
    cohort_images: int
    tagged_cohort_images: int
    candidates: list[AliasCandidate]


class AliasDocument(Record):
    version: Literal[1] = 1
    corpus_fingerprint: Digest
    semantic_profile: Digest
    input_digests: dict[str, str]
    policy: Literal["image-cooccurrence-v1"] = "image-cooccurrence-v1"
    banks: list[AliasBank]
