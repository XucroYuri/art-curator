"""Durable human audit incident; no silent threshold retuning or automatic undo."""
from typing import Literal

from pydantic import AwareDatetime

from .album_map import AlbumStore
from .album_map_protocol import Artifact, Prepared
from .album_map_schema import Hash, Identifier, MappingError
from .album_map_storage import transaction
from .first_pass_schema import Contract


class Incident(Contract):
    batch_id: Identifier
    image_id: Hash
    actor: Identifier
    timestamp: AwareDatetime


class FrozenBatch(Contract):
    batch_id: Identifier
    incident_ref: Hash
    action: Literal["review-or-undo-entire-batch"] = "review-or-undo-entire-batch"
    published: bool


def guard(store: AlbumStore, batch_id: str) -> None:
    """Persisted artifacts survive restart and refuse retry after an audit freeze."""
    for (payload,) in store.connection.execute("SELECT payload FROM artifacts"):
        artifact = Artifact.model_validate_json(payload)
        if artifact.kind == "first-pass-audit-error" and artifact.logical_id == batch_id:
            raise MappingError("first-pass-audit-frozen")


def freeze(store: AlbumStore, incident: Incident) -> FrozenBatch:
    """Abort any remaining prepared publication and offer one existing batch undo."""
    row = store.connection.execute("SELECT state,manifest FROM batches WHERE batch_id=?",
                                   (incident.batch_id,)).fetchone()
    if row is None:
        raise MappingError("unknown-first-pass-batch")
    prepared = Prepared.model_validate_json(row[1])
    if not any(a.kind == "first-pass-input" for a in prepared.request.artifacts):
        raise MappingError("audit-requires-first-pass-batch")
    if incident.image_id not in {change.key for change in prepared.changes}:
        raise MappingError("audit-member-outside-batch")
    artifact = Artifact.capture(incident.canonical(), "first-pass-audit-error").model_copy(
        update={"logical_id": incident.batch_id})
    with transaction(store.connection):
        store.connection.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?)",
                                 (artifact.digest, artifact.model_dump_json()))
        store.connection.execute("UPDATE batches SET state='aborted' WHERE batch_id=? AND state='prepared'",
                                 (incident.batch_id,))
    return FrozenBatch(batch_id=incident.batch_id, incident_ref=artifact.digest, published=row[0] == "committed")
