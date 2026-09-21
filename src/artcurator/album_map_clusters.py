"""Pure cluster planning over frozen content bindings; publication belongs to G5."""
from typing import Literal, Self, assert_never

from pydantic import Field, model_validator

from .album_map_commands import Command, Entity
from .album_map_exchange import Manifest, ManifestMember
from .album_map_protocol import Artifact, Snapshot
from .album_map_schema import ClusterMembership, Hash, MappingError, Model


class ClusterSnapshot(Model):
    snapshot_id: Hash
    members: tuple[ManifestMember, ...] = Field(min_length=1)
    parents: tuple[Hash, ...] = ()
    context_digest: Hash | None = None

    @classmethod
    def create(cls, members: tuple[ManifestMember, ...], parents: tuple[str, ...] = (), context_digest: str | None = None) -> Self:
        ordered = tuple(sorted(members, key=lambda m: (m.image_id, m.subject_id)))
        # Alias strings locate legacy exports; only full content bindings define identity.
        payload = "\n".join(":".join((m.image_id, m.subject_id, m.crop_id, m.profile)) for m in ordered)
        identity = Artifact.capture(("cluster-members-v1\n" + payload + "\n" + "\n".join(sorted(parents))
            + "\n" + (context_digest or "")).encode()).digest
        return cls(snapshot_id=identity, members=ordered, parents=tuple(sorted(parents)), context_digest=context_digest)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({(m.image_id, m.subject_id) for m in self.members}) != len(self.members):
            raise MappingError("duplicate-cluster-member")
        return self


class ClusterDraft(Model):
    action: Literal["name", "split", "merge", "outlier", "exclusion"]
    cluster_id: int | str
    face_ids: tuple[str, ...] = ()
    character: str | None = None
    entity_id: str | None = None
    undone: bool = False
    parent_clusters: tuple[ClusterSnapshot, ...] = ()
    partitions: tuple[tuple[str, ...], ...] = ()
    conflict_resolution: Literal["reject", "defer"] = "reject"
    role: Literal["depicts", "baseline", "variant"] = "depicts"


class ClusterPlan(Model):
    name: str = "inactive-cluster-draft"
    commands: tuple[Command, ...]
    snapshots: tuple[ClusterSnapshot, ...] = ()
    label_conflicts: tuple[str, ...] = ()


class ClusterContext(Model):
    snapshot: Snapshot
    manifest: Manifest
    entities: tuple[Entity, ...]


def plan_cluster(draft: ClusterDraft, context: ClusterContext) -> ClusterPlan:
    """Visual merge never means entity merge; ambiguous names remain pending/deferred."""
    if draft.undone:
        return ClusterPlan(commands=())
    records = {r.image_id: r for r in context.snapshot.records}
    parents = draft.parent_clusters
    members = tuple(m for p in parents for m in p.members)
    for parent in parents:
        if ClusterSnapshot.create(parent.members, parent.parents, parent.context_digest) != parent:
            raise MappingError("cluster-snapshot-digest")
    for member in members:
        if context.manifest.resolve(member.legacy_id) != member:
            raise MappingError("cluster-manifest-binding")
        record = records.get(member.image_id)
        if record is None:
            raise MappingError("cluster-content-missing")
        target = next((s for s in record.subjects if s.subject_id == member.subject_id), None) if record.subjects else record
        if target is None:
            raise MappingError("cluster-subject-missing")
        if target.cluster_membership and target.cluster_membership.snapshot_id not in {p.snapshot_id for p in parents}:
            raise MappingError("stale-cluster-membership")
    ids = {m.legacy_id for m in members}
    if len(ids) != len(members) or len({(m.image_id, m.subject_id) for m in members}) != len(members):
        raise MappingError("overlapping-parent-clusters")
    match draft.action:
        case "name":
            if not draft.face_ids or (parents and not set(draft.face_ids) <= ids):
                raise MappingError("frozen-cluster-command-required")
            entities = tuple(e for e in context.entities if
                (e.entity_id == draft.entity_id if draft.entity_id else e.name == draft.character))
            if len(entities) != 1:
                raise MappingError("typed-cluster-entity-required")
            commands = tuple(Command(action="confirm_relation", members=(key,), entity=entities[0],
                scope="subject" if records[context.manifest.resolve(key).image_id].subjects else "image",
                role=draft.role, confirmation_basis="cluster-selected-members") for key in draft.face_ids)
            return ClusterPlan(name="name:" + entities[0].entity_id, commands=commands)
        case "split" | "outlier" | "exclusion":
            if len(parents) != 1:
                raise MappingError("one-frozen-parent-required")
            parts = draft.partitions if draft.action == "split" else (draft.face_ids,)
            chosen = tuple(key for part in parts for key in part)
            if not parts or any(not p for p in parts) or len(set(chosen)) != len(chosen) or not set(chosen) < ids:
                raise MappingError("split-partition-must-be-disjoint-proper-subsets")
            groups = (*parts, tuple(sorted(ids - set(chosen))))
        case "merge":
            if len(parents) < 2:
                raise MappingError("merge-requires-frozen-parents")
            groups = (tuple(sorted(ids)),)
        case unreachable:
            assert_never(unreachable)
    labels = set()
    for member in members:
        record = records[member.image_id]
        target = next((s for s in record.subjects if s.subject_id == member.subject_id), record)
        labels.update((r.entity_type, r.entity_id) for r in target.relations if r.disposition == "assigned")
    conflicts = tuple(sorted(kind + ":" + key for kind, key in labels)) if draft.action == "merge" and len(labels) > 1 else ()
    if conflicts and draft.conflict_resolution == "reject":
        raise MappingError("merge-label-conflict:" + ",".join(conflicts))
    by_id = {m.legacy_id: m for m in members}
    snapshots = tuple(ClusterSnapshot.create(tuple(by_id[k] for k in group),
        tuple(p.snapshot_id for p in parents)) for group in groups)
    commands = []
    for index, child in enumerate(snapshots):
        for member in child.members:
            scope: Literal["subject", "image"] = "subject" if records[member.image_id].subjects else "image"
            commands.append(Command(action="cluster_membership", members=(member.legacy_id,), scope=scope,
                cluster_membership=ClusterMembership(snapshot_id=child.snapshot_id, parents=child.parents,
                    excluded=draft.action in {"exclusion", "outlier"} and index == 0)))
            if conflicts:
                commands.append(Command(action="set_disposition", members=(member.legacy_id,), scope=scope,
                    disposition="deferred"))
    return ClusterPlan(name=draft.action, commands=tuple(commands), snapshots=snapshots, label_conflicts=conflicts)
