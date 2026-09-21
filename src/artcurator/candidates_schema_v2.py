"""Frozen candidates v2 wire contract; no invented probability fusion."""
from typing import Literal, Self

from pydantic import Field, model_validator

from .identity_schema import FaceId, Record, ShortHash
from .wd_schema import Attributes, ModelSource


class Option(Record):
    name: str = Field(min_length=1)
    display: str | None = Field(default=None, exclude_if=lambda value: value is None)
    source: Literal["model", "memory", "bucket", "action"]
    score: float | None = Field(default=None, ge=-1, le=1, exclude_if=lambda value: value is None)
    score_model: float | None = Field(default=None, ge=0, le=1, exclude_if=lambda value: value is None)
    score_memory: float | None = Field(default=None, ge=-1, le=1, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def score_presence(self) -> Self:
        if self.source in {"model", "memory"} and self.score is None:
            raise ValueError("evidence candidate requires score")
        if self.source in {"bucket", "action"} and any(v is not None for v in (self.score, self.score_model, self.score_memory)):
            raise ValueError("actions and buckets cannot carry evidence scores")
        return self


class Suggested(Record):
    name: str
    source: Literal["model", "memory"]
    margin_vs_runner_up: float = Field(gt=0, le=2)


class ModelSuggestion(Record):
    name: str = Field(min_length=1)
    display: str
    score: float = Field(ge=.85, le=1)
    margin_vs_runner_up: float = Field(ge=.20, le=1)
    margin_basis: Literal["observed", "runner-up-upper-bound-0.35"]
    gate: Literal["wd-score-margin-v1"] = "wd-score-margin-v1"
    verified: Literal[False] = False


class Disagreement(Record):
    model_name: str
    evidence_name: str
    source: Literal["memory", "reference", "confirmed"]
    score: float = Field(ge=-1, le=1)
    reason: Literal["visual-evidence-disagrees", "reference-namespace-unresolved"] = "visual-evidence-disagrees"


class MemorySource(Record):
    path: Literal["character-memory.json"] = "character-memory.json"
    version: Literal[1, 2] = 2


class Sources(Record):
    model: ModelSource = Field(default_factory=ModelSource)
    memory: MemorySource = Field(default_factory=MemorySource)


class FaceOptions(Record):
    face_id: FaceId
    image_sha16: ShortHash
    candidates: list[Option]
    suggested: Suggested | None = None
    suggested_verified: Suggested | None = None
    suggested_model: ModelSuggestion | None = None
    model_demoted: bool = False
    disagreements: list[Disagreement] = Field(default_factory=list)
    abstained: bool = True
    attributes: Attributes = Field(default_factory=Attributes)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        names = [row.name for row in self.candidates]
        if len(names) != len(set(names)) or names[-2:] != ["其他", "新建角色"]:
            raise ValueError("candidates must be unique with bucket/action last")
        if self.abstained != (self.suggested is None):
            raise ValueError("suggestion and abstention disagree")
        if self.suggested_verified is not None and self.suggested_verified != self.suggested:
            raise ValueError("verified suggestion must equal compatibility alias")
        if self.model_demoted != bool(self.disagreements):
            raise ValueError("demotion requires recorded disagreements")
        if self.disagreements and self.suggested_model is None:
            raise ValueError("disagreement requires a model suggestion")
        if self.suggested_model and self.suggested_model.name not in names[:-2]:
            raise ValueError("model suggestion must refer to an evidence candidate")
        if self.suggested and self.suggested.name not in names[:-2]:
            raise ValueError("suggestion must refer to an evidence candidate")
        models = [c for c in self.candidates if c.source == "model" or c.score_model is not None]
        if len(models) > 5 or any((c.score_model if c.score_model is not None else c.score or 0) <= .35 for c in models):
            raise ValueError("model candidates must be top five above .35")
        return self


class CandidateDocumentV2(Record):
    version: Literal[2, 2.1] = 2.1
    sources: Sources = Field(default_factory=Sources)
    faces: list[FaceOptions]
