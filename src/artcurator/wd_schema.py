"""WD compact evidence and isolated worker protocol, independent of torch."""
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from .identity_schema import Digest, FaceId, Record, ShortHash

REVISION: Final = "b25b82a03f7282e41aa2f257a52c7583b710bd1c"
PREPROCESS: Final = "wd-white-square-bicubic448-bgr-f32-0-255-v1"
PINS: Final = {"onnxruntime-gpu": "1.24.4", "numpy": "2.5.3", "Pillow": "12.3.0"}


class ModelSource(Record):
    name: Literal["wd-eva02-large-tagger-v3"] = "wd-eva02-large-tagger-v3"
    revision: Literal["b25b82a03f7282e41aa2f257a52c7583b710bd1c"] = REVISION
    license: Literal["Apache-2.0"] = "Apache-2.0"
    closed_set_size: Literal[2751] = 2751


class Tag(Record):
    tag: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)


class Attributes(Record):
    source: Literal["wd-tagger"] = "wd-tagger"
    hair_color: str | None = None
    hair_style: str | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=40)


class Evidence(Record):
    characters: list[Tag] = Field(default_factory=list, max_length=5)
    attributes: Attributes = Field(default_factory=Attributes)

    @model_validator(mode="after")
    def valid_characters(self) -> Self:
        if any(row.score <= .35 for row in self.characters):
            raise ValueError("character scores must exceed .35")
        if len({row.tag for row in self.characters}) != len(self.characters):
            raise ValueError("duplicate character tag")
        return self


class Handshake(Record):
    protocol: Literal["wd-worker-1.0"] = "wd-worker-1.0"
    build: Digest
    model: ModelSource = Field(default_factory=ModelSource)
    model_sha256: Digest
    tags_sha256: Digest
    preprocess: Literal["wd-white-square-bicubic448-bgr-f32-0-255-v1"] = PREPROCESS
    packages: dict[str, str]
    provider: Literal["CPUExecutionProvider", "CUDAExecutionProvider"] = "CPUExecutionProvider"
    threads: int = Field(default=8, ge=1, le=32)
    output_contract: Literal["wd-compact-v1"] = "wd-compact-v1"


class Request(Record):
    handshake: Handshake
    run_id: str
    request_id: str
    deadline: float
    model_dir: str
    cuda_dll_directory: str | None = None
    crops: list[str] = Field(min_length=1, max_length=16)
    input_ids: list[Digest] = Field(min_length=1, max_length=16)


class Response(Record):
    handshake: Handshake
    run_id: str
    request_id: str
    input_ids: list[Digest]
    evidence: list[Evidence]
    providers_available: list[str]
    providers_active: list[str]
    load_seconds: float = Field(ge=0)
    inference_seconds: float = Field(ge=0)


class TaggedFace(Record):
    face_id: FaceId
    image_sha16: ShortHash
    crop_sha256: Digest
    evidence: Evidence


class TagDocument(Record):
    version: Literal[1] = 1
    handshake: Handshake
    corpus_fingerprint: Digest
    faces: list[TaggedFace]
    batches: list[Response] = Field(default_factory=list)
    cached: int = 0
    wall_seconds: float = 0
