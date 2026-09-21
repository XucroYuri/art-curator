"""Frozen unknown-pool discovery over saved vectors; no embedding or source I/O."""
from typing import Literal

import numpy as np
from pydantic import Field

from .album_map_browser import Entity, StagedImport
from .album_map_clusters import ClusterSnapshot
from .album_map_exchange import Manifest, ManifestMember
from .album_map_protocol import Artifact, Root, Snapshot
from .album_map_schema import Hash, MappingError, Model
from .identity_cluster import cluster_vectors
from .identity_schema import IdentityOptions
from .negotiation_clusters import representative_indices
from .negotiation_metrics import coherence


class VectorMember(ManifestMember):
    vector: tuple[float, ...] | None


class DiscoveryInput(Model):
    profile: Hash
    options: IdentityOptions
    vectors: tuple[VectorMember, ...]
    previous_clusters: tuple[Hash, ...] = ()
    minimum_seed_images: int = Field(default=10, ge=2)
    previous: "Discovery | None" = None
    include_resolved: tuple[str, ...] = ()


class PriorMembership(Model):
    image_id: Hash
    subject_id: str
    snapshot_id: Hash


class Pool(Model):
    schema_version: Literal["album-unknown-pool-v1"] = "album-unknown-pool-v1"
    root: Root
    inputs: DiscoveryInput
    members: tuple[VectorMember, ...]
    unresolved_without_vectors: tuple[str, ...]
    member_digest: Hash
    pair_comparison_upper_bound: int
    reembedding_authorized: Literal[False] = False
    parameters_changed: bool = False
    reembedding_required: tuple[str, ...] = ()
    cost_basis: Literal["arithmetic-upper-bound-not-measured-time"] = "arithmetic-upper-bound-not-measured-time"
    prior_memberships: tuple[PriorMembership, ...] = ()


class ProposedCluster(Model):
    cluster_id: Hash
    members: tuple[str, ...]
    representatives: tuple[str, ...]
    seed_eligible: bool
    parents: tuple[Hash, ...]
    coherent_wall: bool = False
    snapshot: ClusterSnapshot


class Discovery(Model):
    schema_version: Literal["album-discovery-v1"] = "album-discovery-v1"
    pool: Pool
    clusters: tuple[ProposedCluster, ...]
    noise: tuple[str, ...]
    additions: tuple[str, ...] = ()
    splits: tuple[Hash, ...] = ()
    merges: tuple[Hash, ...] = ()


def preview_pool(snapshot: Snapshot, inputs: DiscoveryInput) -> Pool:
    unresolved = {"unknown-foreign", "pending", "hypothesis", "deferred"}
    targets = {(r.image_id, s.subject_id) for r in snapshot.records for s in r.subjects
               if s.disposition in unresolved and not s.verified}
    targets.update((r.image_id, r.image_id) for r in snapshot.records if not r.subjects
                    and r.disposition in unresolved and not r.verified)
    targets.update((v.image_id, v.subject_id) for v in inputs.vectors if v.legacy_id in inputs.include_resolved)
    if not set(inputs.include_resolved) <= {v.legacy_id for v in inputs.vectors}:
        raise MappingError("explicit-pool-selection-missing")
    members = tuple(sorted((v for v in inputs.vectors if (v.image_id, v.subject_id) in targets),
                           key=lambda v: (v.image_id, v.subject_id)))
    if len({(v.image_id, v.subject_id) for v in members}) != len(members):
        raise MappingError("duplicate-vector-member")
    valid = tuple(v for v in members if v.vector is not None)
    subjects = {(r.image_id, s.subject_id): s for r in snapshot.records for s in r.subjects}
    images = {r.image_id: r for r in snapshot.records}
    for member in members:
        subject = subjects.get((member.image_id, member.subject_id))
        image = images.get(member.image_id)
        if image is None or (image.subjects and subject is None):
            raise MappingError("vector-content-binding")
        if subject is not None and (member.crop_id != subject.crop_id or member.profile != subject.detection_profile):
            raise MappingError("vector-content-binding")
    dimensions = {len(v.vector) for v in valid if v.vector is not None}
    if len(dimensions) > 1:
        raise MappingError("incompatible-vector-profile")
    if any(not v.vector or np.linalg.norm(v.vector) <= 1e-12 for v in valid):
        raise MappingError("invalid-vector")
    missing = tuple(sorted(subject for image, subject in targets
        if not any(v.image_id == image and v.subject_id == subject for v in valid)))
    manifest = Manifest(members=members)
    membership = manifest.canonical() + "\n".join(image + ":" + subject for image, subject in sorted(targets)).encode()
    previous = inputs.previous
    prior = tuple(PriorMembership(image_id=r.image_id, subject_id=s.subject_id,
        snapshot_id=s.cluster_membership.snapshot_id) for r in snapshot.records
        for s in r.subjects if s.cluster_membership is not None)
    prior += tuple(PriorMembership(image_id=r.image_id, subject_id=r.image_id,
        snapshot_id=r.cluster_membership.snapshot_id) for r in snapshot.records
        if not r.subjects and r.cluster_membership is not None)
    return Pool(root=snapshot.root, inputs=inputs, members=members, unresolved_without_vectors=missing,
        member_digest=Artifact.capture(membership).digest, pair_comparison_upper_bound=len(valid) * len(valid),
        parameters_changed=previous is not None and (previous.pool.inputs.options != inputs.options
            or previous.pool.inputs.profile != inputs.profile),
        reembedding_required=tuple(v.legacy_id for v in valid if v.profile != inputs.profile), prior_memberships=prior)


def recluster(pool: Pool) -> Discovery:
    if pool.reembedding_required:
        raise MappingError("separate-reembedding-required")
    valid = tuple(v for v in pool.members if v.vector is not None)
    if not valid:
        return Discovery(pool=pool, clusters=(), noise=pool.unresolved_without_vectors)
    labels, _ = cluster_vectors(np.asarray(tuple(v.vector for v in valid), dtype=np.float32), pool.inputs.options)
    clusters = []
    for label in sorted(set(labels) - {-1}):
        selected = tuple(v for v, assigned in zip(valid, labels, strict=True) if assigned == label)
        ids = tuple(v.legacy_id for v in selected)
        parameters = pool.inputs.options.model_dump_json().encode() + pool.inputs.profile.encode()
        unique = {v.image_id: v for v in reversed(selected)}
        wall_ids = tuple(sorted(unique))
        wall_vectors = tuple(unique[key].vector for key in wall_ids)
        representatives = representative_indices(wall_ids, wall_vectors)
        stats = coherence(wall_vectors)
        previous = pool.inputs.previous
        selected_bindings = {(v.image_id, v.subject_id, v.crop_id) for v in selected}
        parents = tuple(c.cluster_id for c in previous.clusters if selected_bindings & {
            (v.image_id, v.subject_id, v.crop_id) for v in previous.pool.members if v.legacy_id in c.members}) if previous else pool.inputs.previous_clusters
        parents = tuple(sorted(set(parents) | {p.snapshot_id for p in pool.prior_memberships
            if (p.image_id, p.subject_id) in {(v.image_id, v.subject_id) for v in selected}}))
        snapshot = ClusterSnapshot.create(tuple(ManifestMember.model_validate(v.model_dump(exclude={"vector"}))
            for v in selected), parents, Artifact.capture(parameters).digest)
        clusters.append(ProposedCluster(cluster_id=snapshot.snapshot_id, members=ids, snapshot=snapshot,
            representatives=tuple(unique[wall_ids[i]].legacy_id for i in representatives),
            seed_eligible=len({v.image_id for v in selected}) >= pool.inputs.minimum_seed_images,
            parents=parents, coherent_wall=stats.valid == len(wall_ids) and stats.median is not None
                and stats.median >= .90 and stats.p10 is not None and stats.p10 >= .80))
    noise = tuple(v.legacy_id for v, label in zip(valid, labels, strict=True) if label == -1)
    previous = pool.inputs.previous
    previous_bindings = {(v.image_id, v.subject_id, v.crop_id) for v in previous.pool.members} if previous else set()
    return Discovery(pool=pool, clusters=tuple(clusters), noise=noise + pool.unresolved_without_vectors,
        additions=tuple(v.legacy_id for v in pool.members if (v.image_id, v.subject_id, v.crop_id) not in previous_bindings),
        splits=tuple(c.cluster_id for c in previous.clusters if sum(c.cluster_id in n.parents for n in clusters) > 1) if previous else (),
        merges=tuple(c.cluster_id for c in clusters if len(c.parents) > 1))


def promotion(snapshot: Snapshot, discovery: Discovery, entity: Entity) -> StagedImport:
    """Single-cluster convenience; multi-cluster selection must be previewed separately."""
    if len(discovery.clusters) != 1 or not discovery.clusters[0].seed_eligible:
        raise MappingError("select-one-qualified-seed-cluster")
    from .album_map_promotion import DiscoveryDecision, stage_discovery
    return stage_discovery(snapshot, DiscoveryDecision(discovery=discovery, actor="local-promotion-confirmation",
        cluster_id=discovery.clusters[0].cluster_id, entity=entity))


DiscoveryInput.model_rebuild()
