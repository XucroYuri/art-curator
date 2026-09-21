"""Deferred tray proposals; archive and revisit never authorize a confirmation."""
from datetime import datetime, timezone
from typing import Literal, assert_never

from .album_map_protocol import BatchRequest, Snapshot
from .album_map_schema import Hash, Identifier, MappingError, MappingRecord, Model


class TrayAction(Model):
    image_id: Hash
    operation_id: Identifier
    action: Literal["archive", "reopen", "defer", "unknown-foreign", "notify"]
    trigger_revision: Hash | None = None


def deferred(snapshot: Snapshot) -> tuple[MappingRecord, ...]:
    """Archive does not filter unresolved membership."""
    return tuple(r for r in snapshot.records if r.disposition == "deferred"
                 or any(s.disposition == "deferred" for s in r.subjects))


def tray_request(snapshot: Snapshot, action: TrayAction) -> BatchRequest:
    record = next((r for r in snapshot.records if r.image_id == action.image_id), None)
    if record is None:
        raise MappingError("unknown-tray-image")
    data = record.model_dump()
    match action.action:
        case "archive":
            data["archived"] = True
        case "notify":
            if action.trigger_revision is None:
                raise MappingError("trigger-revision-required")
            data["trigger_revisions"] = tuple(dict.fromkeys((*record.trigger_revisions, action.trigger_revision)))
        case "reopen" | "defer" | "unknown-foreign":
            if record.subjects:
                raise MappingError("explicit-subject-selection-required")
            data["disposition"] = {"reopen": "pending", "defer": "deferred", "unknown-foreign": "unknown-foreign"}[action.action]
            data["verified"] = False
        case unreachable:
            assert_never(unreachable)
    data["updated_at"] = datetime.now(timezone.utc)
    return BatchRequest.create(snapshot.root, (MappingRecord.model_validate(data),), action.operation_id)
