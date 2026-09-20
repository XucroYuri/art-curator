"""Density groups remain proposals; isolated faces are never force-named."""
from pathlib import Path
from typing import assert_never

import numpy as np
from numpy.typing import NDArray

from .identity_schema import Cluster, ClusteringInfo, IdentityOptions
from .identity_store import load_document, load_vectors, normalized, save_model


def cluster_vectors(values: NDArray, options: IdentityOptions) -> tuple[NDArray, NDArray]:
    vectors = normalized(values)
    if len(vectors) < options.min_cluster_size:
        return np.full(len(vectors), -1, dtype=int), np.zeros(len(vectors))
    match options.cluster:
        case "hdbscan":
            from sklearn.cluster import HDBSCAN
            estimator = HDBSCAN(min_cluster_size=options.min_cluster_size,
                                min_samples=options.min_cluster_size, metric="euclidean", n_jobs=1)
            labels = estimator.fit_predict(vectors)
            return labels, estimator.probabilities_
        case "dbscan":
            from sklearn.cluster import DBSCAN
            labels = DBSCAN(eps=options.eps, min_samples=options.min_cluster_size,
                            metric="cosine", n_jobs=1).fit_predict(vectors)
            return labels, (labels >= 0).astype(float)
        case "chinese_whispers":
            # Deterministic in-place label propagation with blocked cosine neighborhoods.
            labels = np.arange(len(vectors))
            neighbors = []
            for index, vector in enumerate(vectors):
                similarities = vectors @ vector
                indices = np.flatnonzero(
                    (similarities >= 1 - options.eps) & (np.arange(len(vectors)) != index)
                )
                neighbors.append((indices, similarities[indices]))
            for _ in range(20):
                previous = labels.copy()
                for index, (indices, weights) in enumerate(neighbors):
                    if indices.size == 0:
                        continue
                    support = np.bincount(labels[indices], weights=weights, minlength=len(vectors))
                    labels[index] = int(np.argmax(support))
                if np.array_equal(labels, previous):
                    break
            counts = np.bincount(labels, minlength=len(vectors))
            labels[counts[labels] < options.min_cluster_size] = -1
            return labels, (labels >= 0).astype(float)
        case unreachable:
            assert_never(unreachable)


def cluster(out: Path, options: IdentityOptions) -> None:
    from .identity_labels import load_registry, pin_clusters
    document = load_document(out)
    vectors = load_vectors(out, document)
    excluded = set(load_registry(out).excluded)
    active = np.array([i for i, face in enumerate(document.faces) if face.face_id not in excluded], dtype=int)
    labels = np.full(len(vectors), -1, dtype=int)
    probabilities = np.zeros(len(vectors))
    labels[active], probabilities[active] = cluster_vectors(vectors[active], options)
    # Public numeric IDs deterministic for this profile/content set; not stable across corpus growth.
    groups = sorted((np.flatnonzero(labels == label) for label in set(labels) - {-1}),
                    key=lambda indices: min(document.faces[int(i)].face_id for i in indices))
    centroids = normalized(np.stack([vectors[indices].mean(axis=0) for indices in groups])) if groups else np.empty((0, 0))
    faces = [face.model_copy(update={"cluster_id": None, "cluster_prob": 0., "is_outlier": True,
                                     "cluster_margin": None}) for face in document.faces]
    clusters = []
    for cluster_id, indices in enumerate(groups):
        similarities = vectors[indices] @ centroids[cluster_id]
        ranked = sorted(range(len(indices)), key=lambda j: (-float(similarities[j]), document.faces[int(indices[j])].face_id))
        representative = [document.faces[int(indices[j])].face_id for j in ranked[:3]]
        margin = None
        if len(groups) > 1:
            others = np.delete(centroids @ centroids[cluster_id], cluster_id)
            margin = float(np.clip(np.max(others), -1, 1))
        for index in indices:
            faces[int(index)] = faces[int(index)].model_copy(update={
                "cluster_id": cluster_id, "cluster_prob": float(probabilities[index]),
                "is_outlier": False, "cluster_margin": margin})
        clusters.append(Cluster(cluster_id=cluster_id, size=len(indices), centroid_face_id=representative[0],
                                confidence=float(probabilities[indices].mean()), representative_faces=representative))
    updated = document.model_copy(update={"faces": faces, "clusters": clusters, "cluster_count": len(clusters),
                "clustering": ClusteringInfo(algorithm=options.cluster, min_cluster_size=options.min_cluster_size)})
    save_model(out / "identities.json", pin_clusters(out, updated))
