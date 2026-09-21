"""Re-cluster membership publication and selected-cluster naming through G5 staging."""
from typing import Literal

from .album_map_browser import BrowserEnvelope, StagedImport, stage_import
from .album_map_commands import Command, Entity
from .album_map_discovery import Discovery, preview_pool, recluster
from .album_map_exchange import Manifest
from .album_map_protocol import Artifact, Snapshot
from .album_map_schema import ClusterMembership, Hash, Identifier, MappingError, Model


class DiscoveryDecision(Model):
    discovery: Discovery
    actor: Identifier
    cluster_id: Hash | None = None
    entity: Entity | None = None
    selected_members: tuple[Identifier, ...] = ()


def stage_discovery(snapshot: Snapshot, decision: DiscoveryDecision) -> StagedImport:
    """Absent entity means reversible re-clustering only, never implicit verification."""
    discovery = decision.discovery
    if snapshot.root != discovery.pool.root:
        raise MappingError("stale-discovery-parent")
    if recluster(preview_pool(snapshot, discovery.pool.inputs)) != discovery:
        raise MappingError("discovery-replay-mismatch")
    manifest = Manifest(members=discovery.pool.members)
    records = {r.image_id: r for r in snapshot.records}
    clusters = discovery.clusters
    if decision.entity is not None:
        clusters = tuple(c for c in clusters if c.cluster_id == decision.cluster_id)
        if len(clusters) != 1 or not clusters[0].seed_eligible:
            raise MappingError("select-one-qualified-seed-cluster")
    selected = set(decision.selected_members)
    available = {key for cluster in clusters for key in cluster.members}
    if selected and not selected <= available:
        raise MappingError("selection-outside-cluster")
    if decision.entity is not None and selected and len({manifest.resolve(k).image_id for k in selected}) < discovery.pool.inputs.minimum_seed_images:
        raise MappingError("selected-promotion-below-seed-gate")
    commands = []
    for cluster in clusters:
        for key in cluster.members:
            if selected and key not in selected:
                continue
            member = manifest.resolve(key)
            scope: Literal["subject", "image"] = "subject" if records[member.image_id].subjects else "image"
            commands.append(Command(action="cluster_membership", members=(key,), scope=scope,
                cluster_membership=ClusterMembership(snapshot_id=cluster.cluster_id, parents=cluster.parents)))
            if decision.entity is not None:
                commands.append(Command(action="confirm_relation", members=(key,), entity=decision.entity,
                    scope=scope, confirmation_basis="cluster-selected-members"))
    # Noise is still mapped as unresolved; missing vectors have no invented membership.
    if decision.entity is None:
        for member in discovery.pool.members:
            if member.vector is None or member.legacy_id not in discovery.noise:
                continue
            noise_id = Artifact.capture((discovery.pool.member_digest + ":noise:" + member.image_id + member.subject_id).encode()).digest
            scope = "subject" if records[member.image_id].subjects else "image"
            parents = {p.snapshot_id for p in discovery.pool.prior_memberships
                if (p.image_id, p.subject_id) == (member.image_id, member.subject_id)}
            previous = discovery.pool.inputs.previous
            if previous is not None:
                parents.update(c.cluster_id for c in previous.clusters if any(
                    (m.image_id, m.subject_id, m.crop_id) == (member.image_id, member.subject_id, member.crop_id)
                    for m in c.snapshot.members))
            commands.append(Command(action="cluster_membership", members=(member.legacy_id,), scope=scope,
                cluster_membership=ClusterMembership(snapshot_id=noise_id, excluded=True,
                    parents=tuple(sorted(parents)))))
    artifact = Artifact.capture(discovery.canonical(), "discovery-lineage")
    envelope = BrowserEnvelope(source="review-studio", corpus_fingerprint=discovery.pool.member_digest,
        parent=snapshot.root, export_id=artifact.digest, actor=decision.actor,
        profile=discovery.pool.inputs.profile, manifest_digest=manifest.fingerprint(),
        original_journal=Artifact.capture(b'{}'), operations=tuple(commands))
    staged = stage_import(snapshot, envelope, manifest)
    if staged.request is None:
        return staged
    name = "promotion:" + decision.entity.entity_id if decision.entity else "unknown-pool-recluster"
    request = staged.request.model_copy(update={"name": name,
        "artifacts": (*staged.request.artifacts, artifact)})
    return staged.model_copy(update={"request": request})
