"""Versioned publication messages; immutable preparation is not execution."""
import hashlib
from typing import Literal, Self, assert_never

from pydantic import Field, model_validator

from .album_map_schema import Hash, Identifier, MappingError, MappingRecord, Model


class Root(Model):
    library_id: Identifier
    revision: int = Field(ge=0)
    root_digest: Hash


class Artifact(Model):
    kind: Identifier
    logical_id: Identifier
    schema_version: Identifier
    payload_hex: str
    digest: Hash
    length: int = Field(ge=0)

    @model_validator(mode="after")
    def integrity(self) -> Self:
        payload = bytes.fromhex(self.payload_hex)
        if len(payload) != self.length or hashlib.sha256(payload).hexdigest() != self.digest:
            raise MappingError("artifact-digest")
        return self

    @classmethod
    def capture(cls, payload: bytes, kind: str = "evidence") -> Self:
        digest = hashlib.sha256(payload).hexdigest()
        return cls(kind=kind, logical_id=digest, schema_version="opaque-v1", payload_hex=payload.hex(),
                   digest=digest, length=len(payload))


class Support(Model):
    support_id: Identifier
    image_id: Hash
    subject_id: Identifier
    relation_id: Identifier
    entity_id: Identifier
    evidence_ref: Hash
    active: bool = True


class Mutation(Model):
    key: Identifier
    after: MappingRecord | Support | None


class BatchRequest(Model):
    schema_version: Literal["album-mapping-event-v1"] = "album-mapping-event-v1"
    parent: Root
    batch_id: Identifier
    operation_id: Identifier
    name: Identifier
    changes: tuple[Mutation, ...]
    artifacts: tuple[Artifact, ...]
    consent_ref: Hash
    inverse_of: Identifier | None = None
    conflicts: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_keys(self) -> Self:
        if len({c.key for c in self.changes}) != len(self.changes):
            raise MappingError("duplicate-mutation")
        for change in self.changes:
            match change.after:
                case MappingRecord() as record:
                    if record.image_id != change.key or record.library_id != self.parent.library_id:
                        raise MappingError("mutation-binding")
                case Support() as support:
                    if change.key != "support:" + support.support_id:
                        raise MappingError("support-binding")
                case None:
                    pass
                case unreachable:
                    assert_never(unreachable)
        return self

    @classmethod
    def create(cls, parent: Root, records: tuple[MappingRecord, ...], operation_id: str) -> Self:
        """Initialization/manual transport; affirmative preview digest is still required by prepare."""
        evidence = Artifact.capture(b"unavailable-evidence")
        return cls(parent=parent, batch_id=operation_id, operation_id=operation_id, name=operation_id,
                   changes=tuple(Mutation(key=r.image_id, after=MappingRecord.model_validate({
                       **r.model_dump(), "revision": parent.revision + 1, "parent_revision": parent.revision,
                       "batch_id": operation_id, "operation_id": operation_id})) for r in records),
                   artifacts=(evidence,), consent_ref=evidence.digest)


class Change(Model):
    key: Identifier
    before: MappingRecord | Support | None
    after: MappingRecord | Support | None
    before_token: str | None
    after_token: Hash
    before_digest: Hash
    after_digest: Hash


class Prepared(Model):
    request: BatchRequest
    request_digest: Hash
    authorization: Hash
    changes: tuple[Change, ...]


class ExecutionReceipt(Model):
    schema_version: Literal["album-mapping-execution-v1"] = "album-mapping-execution-v1"
    library_id: Identifier
    batch_id: Identifier
    operation_id: Identifier
    revision: int = Field(ge=1)
    parent_revision: int = Field(ge=0)
    root_digest: Hash
    manifest_digest: Hash
    consent_ref: Hash
    mapping_mutations: int = Field(ge=0)
    conflicts: tuple[str, ...] = ()
    partial_undo: bool = False
    inverse_of: str | None = None
    source_moves: Literal[0] = 0


class Snapshot(Model):
    root: Root
    records: tuple[MappingRecord, ...]
    supports: tuple[Support, ...]
    history: tuple[ExecutionReceipt, ...]


class Recovery(Model):
    root: Root
    prepared: tuple[str, ...]
    status: Literal["reconciled", "explicit-resume-or-abort"]
    sqlite_version: str
    power_loss_qualified: Literal[False] = False


def image_digest(value: MappingRecord | Support | None) -> str:
    return hashlib.sha256(b"null" if value is None else value.canonical()).hexdigest()


def next_root(parent: Root, manifest: str) -> Root:
    digest = hashlib.sha256(f"album-store-v1\n{parent.library_id}\n{parent.revision + 1}\n"
                            f"{parent.root_digest}\n{manifest}".encode()).hexdigest()
    return Root(library_id=parent.library_id, revision=parent.revision + 1, root_digest=digest)
