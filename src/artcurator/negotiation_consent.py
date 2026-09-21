"""Strict consent wire schema; a receipt is authority, never an executed mapping."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Mode = Literal["human-first", "auto-first", "inherit-only"]
Scope = Literal["all", "selected", "none"]
EntityType = Literal["work", "artist", "original-series", "character", "ordinary-person", "undetermined"]


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class FolderSelection(Contract):
    folder_id: Hash
    relation_type: EntityType
    descendants: Literal["current-snapshot", "direct-only"] = "current-snapshot"


class Decision(Contract):
    actor: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    affirmative: Literal[True]
    report_digest: Hash
    snapshot_digest: Hash
    profile_digest: Hash
    mode: Mode
    inheritance: Scope
    folders: tuple[FolderSelection, ...] = ()
    threshold_overrides: tuple[str, ...] = ()
    cost_ceiling_seconds: float = Field(ge=0)
    acknowledged: tuple[str, ...]


class Member(Contract):
    image_id: Hash
    occurrence_id: Hash
    path: str
    folder_id: Hash


class InheritedSelection(Contract):
    selection: FolderSelection
    members: tuple[Member, ...]
    source: Literal["inherited"] = "inherited"
    verified: Literal[False] = False
    measurement_ref: Hash
    # These are planned collections. G5 owns materialization and batch undo.
    effect: Literal["pending-human-directed-collection"] = "pending-human-directed-collection"


class Prediction(Contract):
    auto: int | None = None
    review: int | None = None
    none: int | None = None
    audit: int | None = None
    changed: int | None = None
    reason: str = "Unknown: G4 policy not implemented; no mapping changes in G2."
    estimate: Literal[True] = True


class ConsentReceipt(Contract):
    receipt_id: Hash
    decision: Decision
    timestamp: str
    status: Literal["active", "revoked", "superseded"] = "active"
    revoked_at: str | None = None
    revoked_by: str | None = None
    consequences: tuple[str, ...]
    members: tuple[Member, ...]
    inherited: tuple[InheritedSelection, ...]
    predicted: Prediction
    evidence_refs: tuple[str, ...]
    context_enabled: Literal[False] = False
    mapping_mutations: Literal[0] = 0


class NegotiationState(Contract):
    report_path: str
    report_digest: Hash
    active: Hash | None = None
    history: tuple[ConsentReceipt, ...] = ()
    dismissed: bool = False


MODE_CONSEQUENCES: dict[Mode, tuple[str, ...]] = {
    "human-first": ("representative-wall", "await-cluster-typed-name-confirmation",
                    "machine-assignments-remain-proposals", "manual-batch-naming-available"),
    "auto-first": ("MAP-002-gated-only", "verified-false", "audit-5%-review-none-lanes",
                   "no-reference-free-WD-identity-assignment"),
    "inherit-only": ("selected-directories-as-unverified-virtual-collections",
                     "no-AI-first-pass-or-post-confirmation-recognition",
                     "analysis-inspectable", "later-recognition-requires-new-consent"),
}
SCOPE_CONSEQUENCES: dict[Scope, tuple[str, ...]] = {
    "all": ("freeze-all-snapshot-directory-IDs-and-selected-types", "undetermined-stays-undetermined"),
    "selected": ("freeze-checked-directory-IDs-types-descendant-policy", "exclude-future-files"),
    "none": ("source-tree-browsing-only", "zero-inherited-relations", "zero-context-assisted-grouping"),
}
