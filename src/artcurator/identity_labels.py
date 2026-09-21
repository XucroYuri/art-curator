"""Content-bound reversible naming events are retrieval state, never training."""
import json
from pathlib import Path
from typing import Literal, assert_never

from pydantic import Field

from .identity_schema import Digest, FaceId, IdentityDocument, Label, LabelEnvelope, Provenance, Record
from .identity_store import digest, load_document, load_provenance, save_model


class NamingEvent(Record):
    sequence: int
    event_id: Digest
    previous_event: str
    actor_local_id: str
    semantic_profile: Digest
    image_sha256: Digest
    crop_sha256: Digest
    label: Label


class Registry(Record):
    version: Literal[1] = 1
    corpus_fingerprint: Digest
    reference_version: int = 0
    events: list[NamingEvent] = Field(default_factory=list)
    references: dict[FaceId, str] = Field(default_factory=dict)
    excluded: list[FaceId] = Field(default_factory=list)


class ApplyResult(Record):
    faces_changed: int
    clusters_changed: int
    unknown_face_ids: list[str]
    conflicting_clusters: list[int]


def load_registry(out: Path) -> Registry:
    provenance = load_provenance(out)
    path = out / "characters.json"
    payload = path.read_bytes() if path.exists() else Registry(
        corpus_fingerprint=provenance.corpus_fingerprint).model_dump_json().encode()
    return read_registry(payload, provenance)


def read_registry(payload: bytes, provenance: Provenance) -> Registry:
    """The original v1 byte/digest algorithm, shared by file and additive import readers."""
    registry = Registry.model_validate_json(payload)
    if registry.corpus_fingerprint != provenance.corpus_fingerprint:
        raise ValueError("character registry corpus mismatch")
    previous = ""
    references: dict[str, str] = {}
    excluded: set[str] = set()
    for index, event in enumerate(registry.events, 1):
        payload = event.model_dump(exclude={"event_id"})
        if event.previous_event != previous or event.sequence != index or event.event_id != digest(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ):
            raise ValueError("naming event chain integrity mismatch")
        if event.semantic_profile != provenance.semantic_profile:
            raise ValueError("naming event semantic profile mismatch")
        if (provenance.contents.get(event.label.image_sha16) != event.image_sha256 or
                provenance.crops.get(event.label.face_id) != event.crop_sha256):
            raise ValueError("naming event content mismatch")
        previous = event.event_id
        _replay(event.label, references, excluded)
    if references != registry.references or sorted(excluded) != registry.excluded:
        raise ValueError("registry does not match naming event replay")
    return registry


def _replay(label: Label, references: dict[str, str], excluded: set[str]) -> None:
    """Mutate replay accumulators only; incoming labels and model weights are immutable."""
    match label.action:
        case "confirm" | "new":
            if label.character is None:
                raise ValueError("confirmation requires a character")
            references[label.face_id] = label.character.strip()
            excluded.discard(label.face_id)
        case "ignore" | "wrong_box":
            references.pop(label.face_id, None)
            excluded.add(label.face_id)
        case unreachable:
            assert_never(unreachable)


def pin_clusters(out: Path, document: IdentityDocument) -> IdentityDocument:
    registry = load_registry(out)
    clusters = []
    for cluster in document.clusters:
        names = {registry.references[f.face_id] for f in document.faces
                 if f.cluster_id == cluster.cluster_id and f.face_id in registry.references}
        confirmed = next(iter(names)) if len(names) == 1 else None
        clusters.append(cluster.model_copy(update={"confirmed_character": confirmed,
                                                   "suggested_character": None}))
    return document.model_copy(update={"clusters": clusters})


def apply_labels(out: Path, labels_path: Path) -> ApplyResult:
    document = load_document(out)
    provenance = load_provenance(out)
    envelope = LabelEnvelope.model_validate_json(labels_path.read_bytes())
    if envelope.corpus_fingerprint != provenance.corpus_fingerprint:
        raise ValueError("labels belong to a different corpus fingerprint")
    registry = load_registry(out)
    faces = {f.face_id: f for f in document.faces}
    references = registry.references.copy()
    excluded = set(registry.excluded)
    events = registry.events.copy()
    unknown = []
    changed = set()
    accepted = []
    # Validate the entire batch before publishing any authoritative state.
    for label in envelope.labels:
        if label.face_id not in faces:
            unknown.append(label.face_id)
            continue
        if faces[label.face_id].image_sha16 != label.image_sha16:
            raise ValueError("label image does not own the named face")
        accepted.append(label)
        before = (references.get(label.face_id), label.face_id in excluded)
        _replay(label, references, excluded)
        after = (references.get(label.face_id), label.face_id in excluded)
        last_mark = next((e.label.mark for e in reversed(events) if e.label.face_id == label.face_id), None)
        if before == after and (label.mark is None or label.mark == last_mark):
            continue
        changed.add(label.face_id)
        payload = {"sequence": len(events) + 1, "previous_event": events[-1].event_id if events else "",
                   "actor_local_id": envelope.source, "semantic_profile": provenance.semantic_profile,
                   "image_sha256": provenance.contents[label.image_sha16],
                   "crop_sha256": provenance.crops[label.face_id], "label": label.model_dump()}
        event_id = digest(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        events.append(NamingEvent.model_validate({**payload, "event_id": event_id}))
    updated_registry = registry.model_copy(update={"events": events, "references": references,
        "excluded": sorted(excluded), "reference_version": registry.reference_version + bool(changed)})
    save_model(out / "characters.json", updated_registry)
    updated = pin_clusters(out, document)
    changed_clusters = sum(a.confirmed_character != b.confirmed_character
                           for a, b in zip(document.clusters, updated.clusters, strict=True))
    conflicts = [c.cluster_id for c in updated.clusters if len({references[f.face_id] for f in updated.faces
                 if f.cluster_id == c.cluster_id and f.face_id in references}) > 1]
    save_model(out / "identities.json", updated)
    from .character_memory import sync_labels
    sync_labels(out, accepted)
    result = ApplyResult(faces_changed=len(changed), clusters_changed=changed_clusters,
                         unknown_face_ids=unknown, conflicting_clusters=conflicts)
    save_model(out / "identity-apply-result.json", result)
    if (out / "identity-embedding.json").exists():
        from .identity_candidates_v2 import emit
        emit(out)
    return result
