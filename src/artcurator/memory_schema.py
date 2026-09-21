"""User-curated namespace; references are retrieval state, never model training."""
from datetime import datetime, timezone
from typing import Literal, Self

from pydantic import Field, model_validator

from .identity_schema import FaceId, Record


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Variant(Record):
    face_id: FaceId
    note: str = ""


class Character(Record):
    name: str = Field(min_length=1, pattern=r"^[^|\r\n]+$")
    origin: Literal["model", "user", "mixed"] = "user"
    aliases: list[str] = Field(default_factory=list)
    baseline_faces: list[FaceId] = Field(default_factory=list)
    variant_faces: list[Variant] = Field(default_factory=list)
    assigned_faces: list[FaceId] = Field(default_factory=list)
    attribute_profile: dict[str, dict[str, float]] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=timestamp)

    @property
    def face_ids(self) -> set[str]:
        return set(self.baseline_faces + self.assigned_faces + [v.face_id for v in self.variant_faces])


class Memory(Record):
    version: Literal[1] = 1
    characters: list[Character] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_namespace(self) -> Self:
        names = [name for char in self.characters for name in [char.name, *char.aliases]]
        if any(not name.strip() for name in names) or len(names) != len(set(names)):
            raise ValueError("memory names and aliases must be unique and nonempty")
        owners: set[str] = set()
        for char in self.characters:
            if owners & char.face_ids:
                raise ValueError("memory face assigned to multiple characters")
            owners.update(char.face_ids)
        return self
