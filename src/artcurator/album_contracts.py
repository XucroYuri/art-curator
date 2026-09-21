"""Additive v2 boundaries. Frozen G2 producers and all copy literals are unchanged."""
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, ConfigDict, Field, TypeAdapter, model_validator

from .album_map_protocol import Root
from .album_map_schema import Disposition, Hash, Hypothesis, Identifier, MappingError, Model
from .identity_schema import Label as LabelV1, LabelEnvelope as LabelEnvelopeV1


class DispositionLabel(Model):
    action: Literal["set_disposition"]
    image_id: Hash
    subject_id: Identifier | None = None
    crop_id: Hash
    profile: Hash
    disposition: Disposition
    notes: str = ""
    hypotheses: tuple[Hypothesis, ...] = ()
    review_after: AwareDatetime | None = None


LabelV2 = LabelV1 | DispositionLabel


class LabelEnvelopeV2(Model):
    version: Literal[2]
    source: Literal["review-studio"]
    corpus_fingerprint: Hash
    labels: tuple[LabelV2, ...]


def read_labels(payload: bytes) -> LabelEnvelopeV1 | LabelEnvelopeV2:
    return TypeAdapter(Annotated[LabelEnvelopeV1 | LabelEnvelopeV2, Field(discriminator="version")]).validate_json(payload)


class ConsentV2(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    schema_version: Literal["album-consent-v2"] = "album-consent-v2"
    receipt_id: Hash
    preview_digest: Hash
    parent: Root
    actor: Identifier
    status: Literal["active", "revoked", "superseded"] = "active"
    mapping_mutations: Literal[0] = 0
    context_enabled: Literal[False] = False


class PredictionV2(Model):
    auto: int | None = Field(default=None, ge=0)
    review: int | None = Field(default=None, ge=0)
    none: int | None = Field(default=None, ge=0)
    audit: int | None = Field(default=None, ge=0)
    changed: int | None = Field(default=None, ge=0)
    denominator: int = Field(ge=0)
    policy_digest: Hash
    preview_digest: Hash
    parent: Root
    missingness_reason: Identifier | None = None
    estimate: Literal[True] = True

    @model_validator(mode="after")
    def missingness(self) -> Self:
        counts = (self.auto, self.review, self.none, self.audit, self.changed)
        if any(c is None for c in counts) and self.missingness_reason is None:
            raise MappingError("prediction-missingness-required")
        if any(c is not None and c > self.denominator for c in counts):
            raise MappingError("prediction-denominator")
        return self


class PresentationV2(Model):
    schema_version: Literal["album-presentation-v2"] = "album-presentation-v2"
    # Backend qualification is incomplete: no client may advertise an enabled executor.
    mapping_action_available: Literal[False] = False
    qualification: Literal["unqualified"] = "unqualified"


class NegotiationV2(Model):
    schema_version: Literal["album-negotiation-v2"] = "album-negotiation-v2"
    report_digest: Hash
    prediction: PredictionV2
    presentation: PresentationV2 = PresentationV2()
    context_enabled: Literal[False] = False
