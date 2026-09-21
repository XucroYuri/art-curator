"""Strict backend-only first-pass wire values; no client assertion grants authority."""
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from .album_map_protocol import BatchRequest, Snapshot
from .album_map_schema import EntityType, Hash, Identifier, MappingError, Model, Scores
from .negotiation_consent import ConsentReceipt

Cosine = Annotated[float, Field(ge=-1, le=1)]
Probability = Annotated[float, Field(ge=0, le=1)]
Tier = Literal["auto", "review", "none"]


class Contract(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class Policy(Contract):
    version: Literal["album-first-pass-v1"] = "album-first-pass-v1"
    min_similarity: float = Field(default=.90, ge=.90, le=1)
    min_margin: float = Field(default=.05, ge=.05, le=2)
    enumeration: Probability = .35
    model_score: Probability = .85
    model_margin: Probability = .20
    evaluation_ref: Hash | None = None

    @model_validator(mode="after")
    def changed_policy(self) -> Self:
        if ((self.min_similarity, self.min_margin, self.enumeration, self.model_score,
             self.model_margin) != (.90, .05, .35, .85, .20) and self.evaluation_ref is None):
            raise MappingError("custom-policy-requires-predeclared-evaluation")
        return self


class Entity(Contract):
    entity_id: Identifier
    entity_type: EntityType
    name: str


class ModelAdvice(Entity):
    score: Probability
    runner_up: Probability | None = None
    profile: Identifier = "wd-character-v2"


class Visual(Entity):
    source: Literal["memory", "anchors"]
    centroid: Cosine
    individual: Cosine
    reference_images: tuple[Hash, ...] = Field(min_length=1)
    reference_crops: tuple[Hash, ...] = Field(min_length=1)
    human_support_refs: tuple[Hash, ...] = ()
    profile_valid: bool = True


class Calibration(Contract):
    profile: Hash
    reference_digest: Hash
    method: Literal["reference-only-leave-one-out"]
    min_similarity: Cosine
    min_margin: float = Field(ge=0, le=2)


class Evidence(Contract):
    image_id: Hash
    subject_id: Identifier | None = None
    crop_id: Hash | None = None
    profile: Hash
    snapshot_digest: Hash
    reference_digest: Hash | None = None
    valid: bool = True
    visuals: tuple[Visual, ...] = ()
    model: ModelAdvice | None = None
    calibration: Calibration | None = None
    conflicts: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_identities(self) -> Self:
        if len({v.entity_id for v in self.visuals}) != len(self.visuals):
            raise MappingError("duplicate-competing-identity")
        if (self.subject_id is None) != (self.crop_id is None):
            raise MappingError("subject-crop-binding")
        return self


class Outcome(Contract):
    image_id: Hash
    subject_id: Identifier | None = None
    tier: Tier
    reasons: tuple[str, ...]
    source: Literal["model", "memory", "anchors"] = "model"
    winner: Entity | None = None
    scores: Scores = Scores()
    eligible_none: bool = False


class Audit(Contract):
    seed: Literal["album-first-pass-v1"] = "album-first-pass-v1"
    snapshot_digest: Hash
    auto_denominator: int
    none_denominator: int
    auto_ids: tuple[Hash, ...]
    none_ids: tuple[Hash, ...]


class Run(Contract):
    schema_version: Literal["album-first-pass-input-v1"] = "album-first-pass-input-v1"
    operation_id: Identifier
    timestamp: AwareDatetime
    snapshot_digest: Hash
    profile: Hash
    policy: Policy = Policy()
    rows: tuple[Evidence, ...]

    @model_validator(mode="after")
    def unique_targets(self) -> Self:
        if len({(r.image_id, r.subject_id) for r in self.rows}) != len(self.rows):
            raise MappingError("duplicate-first-pass-target")
        if any(r.snapshot_digest != self.snapshot_digest or r.profile != self.profile for r in self.rows):
            raise MappingError("first-pass-evidence-binding")
        return self


class Summary(Contract):
    tiers: dict[str, int]
    reasons: dict[str, int]
    evidence_bases: dict[str, int]
    changed_images: int
    source_moves: Literal[0] = 0
    semantic_precision: Literal["unqualified-engineering-policy"] = "unqualified-engineering-policy"


class Preview(Contract):
    schema_version: Literal["album-first-pass-preview-v1"] = "album-first-pass-preview-v1"
    run: Run
    consent: ConsentReceipt
    before: Snapshot
    outcomes: tuple[Outcome, ...]
    audit: Audit
    summary: Summary
    request: BatchRequest
