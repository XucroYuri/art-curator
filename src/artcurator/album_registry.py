"""Registry v2 is a revision-bound projection, not a replacement writable sidecar."""
from typing import Literal, Self

from pydantic import model_validator

from .album_map_protocol import Artifact, Root, Support
from .album_map_schema import Model
from .identity_labels import Registry as RegistryV1, read_registry
from .identity_schema import Provenance


class RegistryV2(Model):
    version: Literal[2] = 2
    root: Root
    original: Artifact
    provenance: Provenance
    supports: tuple[Support, ...] = ()
    writable: Literal[False] = False

    @model_validator(mode="after")
    def validate_legacy_chain(self) -> Self:
        self.legacy()
        return self

    def legacy(self) -> RegistryV1:
        return read_registry(bytes.fromhex(self.original.payload_hex), self.provenance)
