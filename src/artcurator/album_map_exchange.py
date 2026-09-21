"""Logical full-history exchange; locators are data, never filesystem instructions."""
from typing import Literal, Self

from pydantic import model_validator

from .album_map import AlbumStore
from .album_map_protocol import Artifact, Prepared, Snapshot
from .album_map_recovery import reconcile
from .album_map_schema import Hash, Identifier, MappingError, Model
from .album_map_storage import transaction


class ManifestMember(Model):
    legacy_id: Identifier
    image_id: Hash
    subject_id: Identifier
    crop_id: Hash
    profile: Hash


class Manifest(Model):
    schema_version: Literal["album-member-manifest-v1"] = "album-member-manifest-v1"
    members: tuple[ManifestMember, ...]

    def resolve(self, legacy_id: str) -> ManifestMember:
        matches = tuple(m for m in self.members if m.legacy_id == legacy_id)
        if len(matches) != 1:
            raise MappingError("missing-or-ambiguous-member:" + legacy_id)
        return matches[0]


class ArchivedBatch(Model):
    prepared: Prepared
    state: Literal["prepared", "committed", "aborted"]


class Bundle(Model):
    schema_version: Literal["album-map-export-v1"] = "album-map-export-v1"
    restorable_history: Literal[True] = True
    snapshot: Snapshot
    artifacts: tuple[Artifact, ...]
    batches: tuple[ArchivedBatch, ...]


class Export(Model):
    bundle: Bundle
    digest: Hash

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.digest != self.bundle.fingerprint():
            raise MappingError("export-digest")
        return self


def export_bundle(store: AlbumStore) -> Export:
    """The coordinator holds admission throughout serialization of one revision."""
    reconcile(store.connection)
    bundle = Bundle(snapshot=store.snapshot(), artifacts=tuple(Artifact.model_validate_json(row[0])
        for row in store.connection.execute("SELECT payload FROM artifacts ORDER BY digest")),
        batches=tuple(ArchivedBatch(prepared=Prepared.model_validate_json(payload), state=state)
        for payload, state in store.connection.execute("SELECT manifest,state FROM batches ORDER BY batch_id")))
    return Export(bundle=bundle, digest=bundle.fingerprint())


def restore_bundle(store: AlbumStore, exported: Export) -> None:
    """Explicit empty-store restore, not merge or last-writer-wins; rollback on any mismatch."""
    exported = Export.model_validate_json(exported.model_dump_json())
    current = store.snapshot()
    bundle = exported.bundle
    if current.root.revision or store.connection.execute("SELECT count(*) FROM batches").fetchone()[0]:
        raise MappingError("restore-requires-empty-store")
    if current.root.library_id != bundle.snapshot.root.library_id:
        raise MappingError("restore-library-binding")
    with transaction(store.connection):
        for artifact in bundle.artifacts:
            store.connection.execute("INSERT INTO artifacts VALUES(?,?)", (artifact.digest, artifact.model_dump_json()))
        # Original-before-inverse ordering satisfies the self-referencing foreign key.
        for batch in sorted(bundle.batches, key=lambda b: b.prepared.request.parent.revision):
            prepared = batch.prepared
            request = prepared.request
            store.connection.execute("INSERT INTO batches VALUES(?,?,?,?,?,?,?)", (request.batch_id,
                request.operation_id, prepared.request_digest, batch.state, prepared.model_dump_json(),
                prepared.fingerprint(), request.inverse_of))
        batches = {b.prepared.request.batch_id: b.prepared for b in bundle.batches}
        for receipt in bundle.snapshot.history:
            store.connection.execute("INSERT INTO commits VALUES(?,?,?)",
                (receipt.revision, receipt.batch_id, receipt.model_dump_json()))
            for index, change in enumerate(batches[receipt.batch_id].changes):
                store.connection.execute("INSERT INTO events VALUES(?,?,?)",
                    (receipt.revision, index, change.model_dump_json()))
                store.connection.execute("INSERT OR REPLACE INTO materialized VALUES(?,?,?,?)", (change.key,
                    None if change.after is None else change.after.model_dump_json(), change.after_token, change.after_digest))
        store.connection.execute("UPDATE root SET payload=?", (bundle.snapshot.root.model_dump_json(),))
        reconcile(store.connection)
        # Compare supplied live projection to replay, including unknown optional record fields.
        live = {row[0] for row in store.connection.execute("SELECT payload FROM materialized WHERE payload IS NOT NULL")}
        expected = {r.model_dump_json() for r in (*bundle.snapshot.records, *bundle.snapshot.supports)}
        if live != expected:
            raise MappingError("export-projection-divergence")
