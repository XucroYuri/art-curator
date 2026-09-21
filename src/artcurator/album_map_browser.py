"""Portable browser journal staging. No localStorage synchronization or implicit apply."""
from datetime import datetime, timezone
from typing import Literal, assert_never

from pydantic import Field, ValidationError

from .album_map import AlbumStore
from .album_map_commands import Command, Entity
from .album_map_clusters import ClusterContext, ClusterDraft, ClusterPlan, plan_cluster
from .album_map_exchange import Manifest, ManifestMember
from .album_map_protocol import Artifact, BatchRequest, ExecutionReceipt, Root, Snapshot
from .album_map_schema import (
    Decider, Hash, Identifier, MappingError, MappingRecord, Model,
    Relation, Subject, summarize,
)
from .identity_schema import Label


class Journal(Model):
    clusterDecisions: tuple[ClusterDraft, ...] = ()
    faceLabels: dict[str, Label] = Field(default_factory=dict)


class BrowserEnvelope(Model):
    schema_version: Literal["album-mapping-decisions-v1"] = "album-mapping-decisions-v1"
    source: Literal["review-studio"]
    corpus_fingerprint: Hash
    parent: Root
    export_id: Identifier
    actor: Identifier
    profile: Hash
    manifest_digest: Hash
    original_journal: Artifact
    operations: tuple[Command, ...] = ()
    entities: tuple[Entity, ...] = ()


class StagedImport(Model):
    schema_version: Literal["album-mapping-staging-v1"] = "album-mapping-staging-v1"
    envelope_digest: Hash
    original: BrowserEnvelope
    manifest: Manifest
    before: Snapshot
    request: BatchRequest | None
    conflicts: tuple[str, ...]
    source_moves: Literal[0] = 0
    history_completeness: Literal["snapshot-not-complete-history"] = "snapshot-not-complete-history"
    cluster_plans: tuple[ClusterPlan, ...] = ()


def _translate(envelope: BrowserEnvelope, context: ClusterContext) -> tuple[tuple[Command, ...], tuple[ClusterPlan, ...]]:
    journal = Journal.model_validate_json(bytes.fromhex(envelope.original_journal.payload_hex))
    commands = list(envelope.operations)
    for label in journal.faceLabels.values():
        if label.action not in {"confirm", "new"}:
            raise MappingError("legacy-exclusion-needs-reference-retraction:" + label.face_id)
        entities = tuple(e for e in envelope.entities if e.name == label.character)
        if len(entities) != 1:
            raise MappingError("typed-entity-resolution-required:" + label.face_id)
        commands.append(Command(action="confirm_relation", members=(label.face_id,), entity=entities[0],
            role=label.mark or "depicts"))
    plans = tuple(plan_cluster(draft, context) for draft in journal.clusterDecisions)
    commands.extend(command for plan in plans for command in plan.commands)
    return tuple(commands), plans


class BoundCommand(Model):
    command: Command
    member: ManifestMember
    actor: Identifier
    evidence: Hash
    operation_id: Identifier


def apply_command(record: MappingRecord, bound: BoundCommand) -> MappingRecord:
    """Change only the selected subject; image verification is never inferred."""
    command, member = bound.command, bound.member
    target = next((s for s in record.subjects if s.subject_id == member.subject_id), None)
    if command.scope == "subject":
        if target is None or target.crop_id != member.crop_id or target.detection_profile != member.profile:
            raise MappingError("subject-content-profile-binding")
    elif record.subjects:
        raise MappingError("explicit-subject-selection-required")
    selected = target if command.scope == "subject" else record
    if selected is None:
        raise MappingError("missing-selected-subject")
    data = selected.model_dump()
    data.update(source="human", decider=Decider(kind="human", identity=bound.actor, version="v1"),
                verified=False, updated_at=datetime.now(timezone.utc),
                batch_id=bound.operation_id, operation_id=bound.operation_id,
                evidence_refs=tuple(dict.fromkeys((*selected.evidence_refs, bound.evidence))))
    if command.notes is not None:
        data["notes"] = command.notes
    match command.action:
        case "cluster_membership":
            if command.cluster_membership is None:
                raise MappingError("cluster-membership-required")
            data["cluster_membership"] = command.cluster_membership
        case "set_disposition":
            if command.disposition == "assigned":
                raise MappingError("assigned-requires-relation-command")
            data["disposition"] = command.disposition
        case "confirm_relation":
            if command.entity is None:
                raise MappingError("typed-entity-required")
            entity = command.entity
            relation_id = Artifact.capture(f"{entity.entity_type}:{entity.entity_id}:{member.subject_id}:{command.role}".encode()).digest
            relation = Relation(disposition="assigned", source="human", decider=data["decider"],
                verified=True, confirmation_members=(record.image_id, member.subject_id, member.crop_id, relation_id),
                evidence_refs=(bound.evidence,), created_at=selected.created_at, updated_at=data["updated_at"],
                batch_id=bound.operation_id, operation_id=bound.operation_id, relation_id=relation_id,
                entity_id=entity.entity_id, entity_type=entity.entity_type, role=command.role,
                flags=(command.confirmation_basis,),
                subject_id=member.subject_id if command.scope == "subject" else None)
            data["relations"] = tuple(r for r in selected.relations if r.relation_id != relation_id) + (relation,)
            data["disposition"] = "assigned"
        case unreachable:
            assert_never(unreachable)
    if command.scope == "image":
        return MappingRecord.model_validate(data)
    subject = Subject.model_validate(data)
    subjects = tuple(subject if s.subject_id == subject.subject_id else s for s in record.subjects)
    return MappingRecord.model_validate({**record.model_dump(), "subjects": subjects, "verified": False,
        "disposition": summarize(tuple(s.disposition for s in subjects)), "updated_at": data["updated_at"]})


def stage_import(snapshot: Snapshot, envelope: BrowserEnvelope, manifest: Manifest) -> StagedImport:
    """Return pending conflicts for the entire batch; no write during staging."""
    request = None
    conflicts = ()
    plans = ()
    try:
        if envelope.parent != snapshot.root or envelope.manifest_digest != manifest.fingerprint():
            raise MappingError("stale-parent-or-manifest")
        evidence = Artifact.capture(envelope.canonical(), "browser-envelope")
        records = {r.image_id: r for r in snapshot.records}
        changed = set()
        seen = set()
        operation = "browser:" + envelope.fingerprint()
        commands, plans = _translate(envelope, ClusterContext(snapshot=snapshot, manifest=manifest, entities=envelope.entities))
        for command in commands:
            for legacy_id in command.members:
                member = manifest.resolve(legacy_id)
                if member.profile != envelope.profile or member.image_id not in records:
                    raise MappingError("missing-content-or-profile")
                duplicate = (member.image_id, member.subject_id, command.fingerprint())
                if duplicate in seen:
                    continue
                seen.add(duplicate)
                records[member.image_id] = apply_command(records[member.image_id], BoundCommand(
                    command=command, member=member, actor=envelope.actor, evidence=evidence.digest,
                    operation_id=operation))
                changed.add(member.image_id)
        base = BatchRequest.create(snapshot.root, tuple(records[key] for key in sorted(changed)), operation)
        request = base.model_copy(update={"name": "cluster:" + ";".join(plan.name for plan in plans) if plans else base.name,
            "artifacts": (*base.artifacts, evidence, envelope.original_journal,
            Artifact.capture(manifest.canonical(), "member-manifest"),
            *(Artifact.capture(plan.canonical(), "cluster-plan") for plan in plans)), "consent_ref": evidence.digest})
    except MappingError as error:
        conflicts = (error.code,)
    except ValidationError as error:
        conflicts = (str(error),)
    return StagedImport(envelope_digest=envelope.fingerprint(), original=envelope, manifest=manifest,
                        before=snapshot, request=request, conflicts=conflicts, cluster_plans=plans)


def confirm_import(store: AlbumStore, staged: StagedImport, authorization: str) -> ExecutionReceipt:
    if authorization != staged.fingerprint() or staged.conflicts or staged.request is None:
        raise MappingError("import-preview-confirmation-required")
    store.prepare(staged.request, staged.request.fingerprint())
    return store.publish(staged.request.batch_id)
