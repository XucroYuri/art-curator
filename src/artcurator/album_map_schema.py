"""album-map-v1: content identity and open-world mapping, never file destinations."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1)]
Disposition = Literal["assigned", "hypothesis", "deferred", "unknown-foreign",
                      "original-design", "ordinary", "non-character", "pending"]
EntityType = Literal["work", "artist", "original-series", "character", "ordinary-person", "undetermined"]


class MappingError(ValueError):
    """Stable machine-readable refusal; suspect evidence must not be repaired implicitly."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow", allow_inf_nan=False)

    def canonical(self) -> bytes:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical()).hexdigest()


class Decider(Model):
    kind: Literal["human", "policy"]
    identity: Identifier
    version: Identifier


class Metric(Model):
    value: float | None
    unit: Identifier
    profile: Identifier
    bound: Literal["exact", "lower", "upper", "unavailable"] = "exact"


class Scores(Model):
    wd: Metric | None = None
    visual: Metric | None = None
    stable_margin: Metric | None = None
    model_margin: Metric | None = None

    @model_validator(mode="after")
    def ranges(self) -> Self:
        for metric, low, high in ((self.wd, 0, 1), (self.visual, -1, 1),
                                  (self.stable_margin, -2, 2), (self.model_margin, -1, 1)):
            if metric is not None and metric.value is not None and not low <= metric.value <= high:
                raise MappingError("metric-range")
        return self


class Hypothesis(Model):
    entity_id: Identifier
    entity_type: EntityType
    name: str
    scores: Scores = Scores()
    evidence_refs: tuple[Hash, ...] = Field(min_length=1)


class DecisionFields(Model):
    disposition: Disposition
    source: Literal["model", "memory", "anchors", "inherited", "human"]
    decider: Decider
    scores: Scores = Scores()
    verified: bool = False
    confirmation_members: tuple[Identifier, ...] = ()
    evidence_refs: tuple[Hash, ...] = Field(min_length=1)
    flags: tuple[str, ...] = ()
    notes: str = ""
    hypotheses: tuple[Hypothesis, ...] = ()
    review_after: AwareDatetime | None = None
    trigger_revisions: tuple[Hash, ...] = ()
    created_at: AwareDatetime
    updated_at: AwareDatetime
    batch_id: Identifier
    operation_id: Identifier

    @model_validator(mode="after")
    def human_verification(self) -> Self:
        if self.verified and (self.source != "human" or self.decider.kind != "human"
                              or not self.confirmation_members):
            raise MappingError("explicit-human-confirmation-required")
        if self.updated_at < self.created_at:
            raise MappingError("timestamp-order")
        return self


class Relation(DecisionFields):
    relation_id: Identifier
    entity_id: Identifier
    entity_type: EntityType
    role: Identifier
    subject_id: Identifier | None = None


class Subject(DecisionFields):
    subject_id: Identifier
    image_id: Hash
    crop_id: Hash
    detection_profile: Hash
    relations: tuple[Relation, ...] = ()


class Occurrence(Model):
    occurrence_id: Identifier
    locator: str
    observed_hash: Hash
    available: bool


class MappingRecord(DecisionFields):
    schema_version: Literal["album-map-v1"] = "album-map-v1"
    library_id: Identifier
    revision: int = Field(default=0, ge=0)
    parent_revision: int | None = Field(default=None, ge=0)
    image_id: Hash
    occurrences: tuple[Occurrence, ...] = ()
    subjects: tuple[Subject, ...] = ()
    relations: tuple[Relation, ...] = ()
    archived: bool = False

    @model_validator(mode="after")
    def bindings(self) -> Self:
        ids = {s.subject_id for s in self.subjects}
        if len(ids) != len(self.subjects) or any(s.image_id != self.image_id for s in self.subjects):
            raise MappingError("subject-binding")
        relations = (*self.relations, *(r for s in self.subjects for r in s.relations))
        if len({r.relation_id for r in relations}) != len(relations):
            raise MappingError("duplicate-relation")
        if any(r.subject_id is not None and r.subject_id not in ids for r in relations):
            raise MappingError("relation-binding")
        if any(r.subject_id != s.subject_id for s in self.subjects for r in s.relations):
            raise MappingError("relation-owner")
        if any(o.observed_hash != self.image_id for o in self.occurrences):
            raise MappingError("occurrence-binding")
        if self.subjects and self.disposition != summarize(tuple(s.disposition for s in self.subjects)):
            raise MappingError("summary-disposition")
        if self.verified and not {self.image_id, *ids, *(r.relation_id for r in relations)} <= set(self.confirmation_members):
            raise MappingError("incomplete-image-confirmation")
        return self

    @classmethod
    def pending(cls, image_id: str, library_id: str) -> Self:
        now = datetime.now(timezone.utc)
        return cls(image_id=image_id, library_id=library_id, disposition="pending", source="model",
                   decider=Decider(kind="policy", identity="pending-initialization", version="v1"),
                   evidence_refs=(hashlib.sha256(b"unavailable-evidence").hexdigest(),),
                   flags=("unavailable-evidence",), created_at=now, updated_at=now,
                   batch_id="pending", operation_id="pending")


def summarize(states: tuple[Disposition, ...]) -> Disposition:
    """Unresolved priority is independent of accepted relation visibility."""
    for state in ("pending", "deferred", "hypothesis", "unknown-foreign"):
        if state in states:
            return state
    if states and len(set(states)) == 1:
        return states[0]
    return "hypothesis" if states else "pending"
