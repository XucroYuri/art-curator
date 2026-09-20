"""Versioned reference and grouping boundaries, separate from identity v2 columns."""
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from .identity_profiles import ExecutionProfile
from .identity_schema import BBox, Digest, ModelInfo, Record


@dataclass(frozen=True, slots=True)
class GroupingError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


class Thresholds(Record):
    min_sim: float = Field(ge=-1, le=1)
    min_margin: float = Field(ge=0, le=2)


class EmbeddingLedger(Record):
    model: ModelInfo
    preprocess: str
    execution: ExecutionProfile
    semantic_profile: Digest
    sha256: Digest
    faces: list[str]


class Anchor(Record):
    character: str = Field(min_length=1, pattern=r"^[^|\r\n]+$")
    source: Literal["folder-derived", "human-confirmed"]
    source_folder: str
    image_sha256: Digest
    crop_sha256: Digest
    bbox: BBox
    det_score: float = Field(ge=0, le=1)
    phash: str
    event_id: str | None = None


class Calibration(Record):
    method: str = "reference-only-leave-one-crop-out-v1"
    samples: int
    genuine: list[float]
    impostor: list[float]
    stable_margin: list[float]
    defaults: Thresholds


class AnchorDocument(Record):
    version: Literal[1] = 1
    label_knowledge: str = "user-organized folders treated as human labels; never query path features"
    model: ModelInfo
    preprocess: str
    execution: ExecutionProfile
    detector: ModelInfo
    detector_sha256: Digest
    detector_options: dict[str, str | int | float]
    licenses: dict[str, str]
    folders: dict[str, dict[str, int]]
    excluded_folders: list[str]
    anchors: list[Anchor]
    matrix_sha256: Digest
    calibration: Calibration
    wall_seconds: float


class Decision(Record):
    character: str | None = None
    sim: float | None = None
    margin: float | None = None
    centroid_margin: float | None = None
    individual_margin: float | None = None


class CharacterGroup(Record):
    character: str
    image_count: int
    face_count: int
    images: list[str]
    mean_sim: float | None
    min_margin: float | None


class ClusterGroup(Record):
    cluster_id: int | None
    face_count: int
    images: list[str]


class Abstained(Record):
    face_count: int
    cluster_groups: list[ClusterGroup]


class GroupProvenance(Record):
    algorithm: str = "anchor-centroid-v1"
    corpus_fingerprint: Digest
    identities_sha256: Digest
    embedding_sha256: Digest
    anchors_sha256: Digest
    effective_references_sha256: Digest
    reference_version: int
    execution: ExecutionProfile
    model: ModelInfo
    preprocess: str
    label_knowledge: str
    licenses: dict[str, str]
    source_counts: dict[str, int]
    images: int
    faces: int
    zero_face_images: int
    unassigned_images: int
    any_abstained_images: int
    multi_character_images: int
    wall_seconds: float


class GroupDocument(Record):
    version: Literal[1] = 1
    provenance: GroupProvenance
    thresholds: Thresholds
    characters: list[CharacterGroup]
    abstained: Abstained
