"""Representative selection over frozen G1 clusters; this module never clusters."""
import math

import numpy as np

from .candidates_schema_v2 import FaceOptions
from .identity_store import digest
from .ingest_schema import Frozen, IngestError
from .negotiation_metrics import Coherence, coherence
from .negotiation_sources import Evidence


class Representative(Frozen):
    image_id: str
    face_id: str
    image_ref: str | None
    crop_ref: str | None


class ClusterReport(Frozen):
    cluster_id: int
    member_digest: str
    image_ids: tuple[str, ...]
    face_ids: tuple[str, ...]
    unique_images: int
    faces: int
    outlier_fraction: float
    coherence: Coherence
    eligible: bool
    eligibility_reasons: tuple[str, ...]
    representation: str = "lowest-face-id per distinct image within cluster; crop-only"
    representatives: tuple[Representative, ...]
    candidates: tuple[FaceOptions, ...]
    names: tuple[str, ...]
    source_concentration: float | None
    source_concentration_basis: str = "largest folder share of distinct images; overlapping origins retained, not purity"
    reference_support_ref: str | None
    profile: str | None


def representative_indices(ids: tuple[str, ...], vectors: tuple[tuple[float, ...] | None, ...]) -> tuple[int, ...]:
    """Medoid, lowest LOO coherence, then farthest-point; full hash breaks every tie."""
    stats = coherence(vectors)
    if stats.valid != len(ids) or any(s is None for s in stats.scores):
        return tuple(sorted(range(len(ids)), key=lambda i: ids[i])[:12])
    matrix = np.asarray(vectors, dtype=np.float64)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    # Cosine medoid without an N*N allocation.
    medoid_scores = matrix @ matrix.sum(axis=0)
    medoid = min(range(len(ids)), key=lambda i: (-float(medoid_scores[i]), ids[i]))
    lowest = min(range(len(ids)), key=lambda i: (stats.scores[i], ids[i]))
    selected = [medoid]
    if lowest != medoid:
        selected.append(lowest)
    while len(selected) < min(12, len(ids)):
        remaining = set(range(len(ids))) - set(selected)
        selected.append(min(remaining, key=lambda i: (
            max(float(np.dot(matrix[i], matrix[j])) for j in selected), ids[i])))
    return tuple(selected)


def clusters(evidence: Evidence) -> tuple[ClusterReport, ...]:
    document = evidence.identities
    if document is None:
        return ()
    prefix = f"revisions/{evidence.job.revision}/"
    results = []
    for cluster in document.clusters:
        faces = sorted((f for f in document.faces if f.cluster_id == cluster.cluster_id), key=lambda f: f.face_id)
        unique: dict[str, str] = {}
        for face in faces:
            sha = evidence.full_hashes.get(face.image_sha16)
            if sha is None:
                raise IngestError("cluster member absent from snapshot")
            unique.setdefault(sha, face.face_id)
        ids = tuple(sorted(unique))
        vectors = tuple(evidence.vectors.get(unique[key]) for key in ids)
        stats = coherence(vectors)
        reasons = []
        if len(ids) < 10:
            reasons.append("fewer-than-10-distinct-images")
        if stats.valid != len(ids) or any(s is None for s in stats.scores) or evidence.vector_profile is None:
            reasons.append("insufficient-or-invalid-same-profile-vectors")
        if stats.median is None or stats.median < .90:
            reasons.append("median-below-0.90-or-unavailable")
        if stats.p10 is None or stats.p10 < .80:
            reasons.append("p10-below-0.80-or-unavailable")
        representatives = []
        for index in representative_indices(ids, vectors):
            sha, face_id = ids[index], unique[ids[index]]
            image_ref, crop_ref = prefix + f"previews/{sha}.jpg", prefix + f"faces/{face_id}.jpg"
            representatives.append(Representative(image_id=sha, face_id=face_id,
                image_ref=image_ref if image_ref in evidence.artifact_names else None,
                crop_ref=crop_ref if crop_ref in evidence.artifact_names else None))
        origins: dict[str, set[str]] = {}
        from pathlib import PurePosixPath
        for occurrence in evidence.inventory.occurrences:
            if occurrence.sha256 in unique and occurrence.status != "unavailable":
                origins.setdefault(str(PurePosixPath(occurrence.path).parent), set()).add(occurrence.sha256)
        member_faces = tuple(f.face_id for f in faces)
        reference = prefix + "character-groups.json"
        results.append(ClusterReport(cluster_id=cluster.cluster_id,
            member_digest=digest("\n".join((*ids, *member_faces)).encode()), image_ids=ids,
            face_ids=member_faces, unique_images=len(ids), faces=len(faces),
            outlier_fraction=sum(f.is_outlier for f in faces)/len(faces), coherence=stats,
            eligible=not reasons, eligibility_reasons=tuple(reasons), representatives=tuple(representatives),
            candidates=tuple(f for f in evidence.candidates.faces if f.face_id in member_faces) if evidence.candidates else (),
            names=tuple(n for n in (cluster.suggested_character, cluster.confirmed_character) if n),
            source_concentration=max((len(s) for s in origins.values()), default=0)/len(ids),
            reference_support_ref=reference if reference in evidence.artifact_names else None,
            profile=evidence.vector_profile))
    return tuple(results)
