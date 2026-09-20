"""Versioned identity boundaries; frozen public names are shared with the studio."""
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ShortHash = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
FaceId = Annotated[str, Field(pattern=r"^f_[0-9a-f]{8}$")]
BBox = tuple[int, int, int, int]


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow", allow_inf_nan=False)


class IdentityOptions(Record):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    detector: Literal["anime_face_detection", "yunet"] = "anime_face_detection"
    variant: Literal["n", "s"] = "n"
    embedder: Literal["siglip", "ccip"] = "siglip"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    precision: Literal["float32", "float16"] = "float32"
    batch_size: int = Field(default=16, ge=1, le=32)
    cluster: Literal["hdbscan", "chinese_whispers", "dbscan"] = "hdbscan"
    min_cluster_size: int = Field(default=3, ge=2)
    min_face_px: int = Field(default=24, ge=1)
    det_threshold: float = Field(default=.3, gt=0, lt=1)
    nms_threshold: float = Field(default=.5, gt=0, lt=1)
    eps: float = Field(default=.15, gt=0, lt=2)
    threads: int = Field(default=4, ge=1, le=32)
    target_character: str | None = None
    ccip_license_accepted: bool = False


class ModelInfo(Record):
    name: str
    model: str
    revision: str


class DetectorInfo(ModelInfo):
    min_face_px: int = 24


class ClusteringInfo(Record):
    algorithm: str = "hdbscan"
    min_cluster_size: int = 3


class ImageFaces(Record):
    sha16: ShortHash
    path_rel: str
    faces: list[FaceId]


class Face(Record):
    face_id: FaceId
    image_sha16: ShortHash
    bbox: BBox
    det_score: float = Field(ge=0, le=1)
    crop_rel: str
    cluster_id: int | None = Field(default=None, ge=0)
    cluster_prob: float = Field(default=0, ge=0, le=1)
    is_outlier: bool = True
    cluster_margin: float | None = Field(default=None, ge=-1, le=1)

    @model_validator(mode="after")
    def valid_box(self) -> Self:
        x, y, width, height = self.bbox
        if min(x, y) < 0 or min(width, height) <= 0:
            raise ValueError("bbox must be positive xywh in decoded pixels")
        if self.crop_rel != f"faces/{self.face_id}.jpg":
            raise ValueError("crop path must match face_id")
        if self.is_outlier != (self.cluster_id is None):
            raise ValueError("outlier and cluster_id disagree")
        return self


class Cluster(Record):
    cluster_id: int = Field(ge=0)
    size: int = Field(ge=1)
    centroid_face_id: FaceId
    confidence: float = Field(ge=0, le=1)
    suggested_character: str | None = None
    confirmed_character: str | None = None
    representative_faces: list[FaceId]


class IdentityDocument(Record):
    version: Literal[1] = 1
    detector: DetectorInfo
    embedder: ModelInfo
    clustering: ClusteringInfo
    image_count: int = Field(ge=0)
    face_count: int = Field(ge=0)
    cluster_count: int = Field(ge=0)
    images: list[ImageFaces]
    faces: list[Face]
    clusters: list[Cluster]

    @model_validator(mode="after")
    def valid_links(self) -> Self:
        if (self.image_count, self.face_count, self.cluster_count) != (
            len(self.images), len(self.faces), len(self.clusters)
        ):
            raise ValueError("identity counts disagree")
        faces = {face.face_id: face for face in self.faces}
        clusters = {cluster.cluster_id: cluster for cluster in self.clusters}
        if len(faces) != self.face_count or len(clusters) != self.cluster_count:
            raise ValueError("duplicate face or cluster identity")
        linked = set()
        for image in self.images:
            for face_id in image.faces:
                if face_id not in faces or faces[face_id].image_sha16 != image.sha16:
                    raise ValueError("broken image-face link")
                linked.add(face_id)
        if linked != set(faces):
            raise ValueError("unlinked faces")
        for face in self.faces:
            if face.cluster_id is not None and face.cluster_id not in clusters:
                raise ValueError("unknown cluster")
        for cluster in self.clusters:
            members = {f.face_id for f in self.faces if f.cluster_id == cluster.cluster_id}
            if cluster.size != len(members) or cluster.centroid_face_id not in members:
                raise ValueError("invalid cluster membership")
            if not set(cluster.representative_faces) <= members:
                raise ValueError("invalid representatives")
        return self


class Provenance(Record):
    corpus_fingerprint: Digest
    semantic_profile: Digest
    contents: dict[ShortHash, Digest]
    crops: dict[FaceId, Digest]


class Label(Record):
    face_id: FaceId
    image_sha16: ShortHash
    character: str | None = None
    action: Literal["confirm", "new", "ignore", "wrong_box"]

    @model_validator(mode="after")
    def named_confirmation(self) -> Self:
        if self.action in {"confirm", "new"} and not (self.character and self.character.strip()):
            raise ValueError("confirm/new requires a nonempty character")
        return self


class LabelEnvelope(Record):
    version: Literal[1]
    source: Literal["review-studio"]
    corpus_fingerprint: Digest
    labels: list[Label]
