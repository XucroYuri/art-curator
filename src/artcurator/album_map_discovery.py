"""Frozen unknown-pool discovery over saved vectors; no embedding or source I/O."""
from typing import Literal

import numpy as np
from pydantic import Field

from .album_map_browser import BrowserEnvelope, Command, Entity, StagedImport, stage_import
from .album_map_exchange import Manifest, ManifestMember
from .album_map_protocol import Artifact, Root, Snapshot
from .album_map_schema import Hash, MappingError, Model
from .identity_cluster import cluster_vectors
from .identity_schema import IdentityOptions
from .negotiation_clusters import representative_indices


class VectorMember(ManifestMember):
    vector: tuple[float, ...] | None


class DiscoveryInput(Model):
    profile: Hash
    options: IdentityOptions
    vectors: tuple[VectorMember, ...]
    previous_clusters: tuple[Hash, ...] = ()
    minimum_seed_images: int = Field(default=10, ge=2)


class Pool(Model):
    schema_version: Literal["album-unknown-pool-v1"] = "album-unknown-pool-v1"
    root: Root
    inputs: DiscoveryInput
    members: tuple[VectorMember, ...]
    unresolved_without_vectors: tuple[str, ...]
    member_digest: Hash
    pair_comparison_upper_bound: int
    reembedding_authorized: Literal[False] = False


class ProposedCluster(Model):
    cluster_id: Hash
    members: tuple[str, ...]
    representatives: tuple[str, ...]
    seed_eligible: bool
    parents: tuple[Hash, ...]


class Discovery(Model):
    schema_version: Literal["album-discovery-v1"] = "album-discovery-v1"
    pool: Pool
    clusters: tuple[ProposedCluster, ...]
    noise: tuple[str, ...]


def preview_pool(snapshot: Snapshot, inputs: DiscoveryInput) -> Pool:
    unresolved = {"unknown-foreign", "pending", "hypothesis", "deferred"}
    targets = {(r.image_id, s.subject_id) for r in snapshot.records for s in r.subjects
               if s.disposition in unresolved and not s.verified}
    targets.update((r.image_id, r.image_id) for r in snapshot.records if not r.subjects
                   and r.disposition in unresolved and not r.verified)
    members = tuple(sorted((v for v in inputs.vectors if (v.image_id, v.subject_id) in targets),
                           key=lambda v: (v.image_id, v.subject_id)))
    if len({(v.image_id, v.subject_id) for v in members}) != len(members):
        raise MappingError("duplicate-vector-member")
    valid = tuple(v for v in members if v.vector is not None)
    dimensions = {len(v.vector) for v in valid if v.vector is not None}
    if len(dimensions) > 1 or any(v.profile != inputs.profile for v in valid):
        raise MappingError("incompatible-vector-profile")
    if any(not v.vector or np.linalg.norm(v.vector) <= 1e-12 for v in valid):
        raise MappingError("invalid-vector")
    missing = tuple(sorted(subject for image, subject in targets
        if not any(v.image_id == image and v.subject_id == subject for v in valid)))
    manifest = Manifest(members=members)
    membership = manifest.canonical() + "\n".join(image + ":" + subject for image, subject in sorted(targets)).encode()
    return Pool(root=snapshot.root, inputs=inputs, members=members, unresolved_without_vectors=missing,
                member_digest=Artifact.capture(membership).digest, pair_comparison_upper_bound=len(valid) * len(valid))


def recluster(pool: Pool) -> Discovery:
    valid = tuple(v for v in pool.members if v.vector is not None)
    if not valid:
        return Discovery(pool=pool, clusters=(), noise=pool.unresolved_without_vectors)
    labels, _ = cluster_vectors(np.asarray(tuple(v.vector for v in valid), dtype=np.float32), pool.inputs.options)
    clusters = []
    for label in sorted(set(labels) - {-1}):
        selected = tuple(v for v, assigned in zip(valid, labels, strict=True) if assigned == label)
        ids = tuple(v.legacy_id for v in selected)
        manifest = Manifest(members=selected)
        parameters = pool.inputs.options.model_dump_json().encode() + pool.inputs.profile.encode()
        identity = Artifact.capture(manifest.canonical() + parameters).digest
        representatives = representative_indices(ids, tuple(v.vector for v in selected))
        clusters.append(ProposedCluster(cluster_id=identity, members=ids,
            representatives=tuple(ids[i] for i in representatives),
            seed_eligible=len({v.image_id for v in selected}) >= pool.inputs.minimum_seed_images,
            parents=pool.inputs.previous_clusters))
    noise = tuple(v.legacy_id for v, label in zip(valid, labels, strict=True) if label == -1)
    return Discovery(pool=pool, clusters=tuple(clusters), noise=noise + pool.unresolved_without_vectors)


def promotion(snapshot: Snapshot, discovery: Discovery, entity: Entity) -> StagedImport:
    """Single-cluster convenience; multi-cluster selection must be previewed separately."""
    if len(discovery.clusters) != 1 or not discovery.clusters[0].seed_eligible:
        raise MappingError("select-one-qualified-seed-cluster")
    if snapshot.root != discovery.pool.root:
        raise MappingError("stale-discovery-parent")
    manifest = Manifest(members=discovery.pool.members)
    cluster = discovery.clusters[0]
    records = {r.image_id: r for r in snapshot.records}
    commands = tuple(Command(action="confirm_relation", members=(key,), entity=entity,
        scope="subject" if records[manifest.resolve(key).image_id].subjects else "image") for key in cluster.members)
    envelope = BrowserEnvelope(source="review-studio", corpus_fingerprint=discovery.pool.member_digest,
        parent=snapshot.root, export_id=cluster.cluster_id, actor="local-promotion-confirmation",
        profile=discovery.pool.inputs.profile, manifest_digest=manifest.fingerprint(),
        original_journal=Artifact.capture(b'{"clusterDecisions":[],"faceLabels":{}}'), operations=commands)
    staged = stage_import(snapshot, envelope, manifest)
    if staged.request is None:
        return staged
    request = staged.request.model_copy(update={"name": "promotion:" + entity.entity_id,
        "artifacts": (*staged.request.artifacts, Artifact.capture(discovery.canonical(), "discovery-lineage"))})
    return staged.model_copy(update={"request": request})
