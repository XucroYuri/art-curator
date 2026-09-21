"""Analytic cluster evidence: exact representatives and eligibility boundaries, no models."""
import importlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from artcurator.candidates_schema_v2 import CandidateDocumentV2
from artcurator.identity_schema import (
    Cluster,
    ClusteringInfo,
    DetectorInfo,
    Face,
    IdentityDocument,
    ImageFaces,
    ModelInfo,
)
from artcurator.ingest_schema import IngestError, Inventory, Job, Occurrence
from artcurator.negotiation_sources import Evidence, G1Report

REVISION = "a" * 64


def build(vectors: tuple[tuple[float, ...] | None, ...], *, profile: str | None = "siglip-test") -> Evidence:
    """One cluster holding the first face of every distinct image."""
    faces, images, occurrences, by_face, full_hashes = [], [], [], {}, {}
    for index, vector in enumerate(vectors):
        full, short = f"{index + 1:064x}", f"{index + 1:016x}"
        face_id = f"f_{index:08x}"
        faces.append(Face(face_id=face_id, image_sha16=short, bbox=(0, 0, 8, 8), det_score=1.0,
                          crop_rel=f"faces/{face_id}.jpg", cluster_id=1, is_outlier=False))
        images.append(ImageFaces(sha16=short, path_rel=f"folder/image-{index}.png", faces=[face_id]))
        occurrences.append(Occurrence(path=f"folder/image-{index}.png", sha256=full, status="indexed"))
        full_hashes[short] = full
        if vector is not None:
            by_face[face_id] = vector
    clusters = [Cluster(cluster_id=1, size=len(faces), centroid_face_id=faces[0].face_id,
                        confidence=1.0, representative_faces=[faces[0].face_id])]
    document = IdentityDocument(
        detector=DetectorInfo(name="d", model="m", revision="1"),
        embedder=ModelInfo(name="e", model="m", revision="1"), clustering=ClusteringInfo(),
        image_count=len(images), face_count=len(faces), cluster_count=1,
        images=images, faces=faces, clusters=clusters)
    job = Job(job_id="j", root=Path("/synthetic"), revision=REVISION, profile_digest="b" * 64)
    inventory = Inventory(revision=REVISION, parent_revision=None, occurrences=tuple(occurrences))
    g1 = G1Report(revision=REVISION, profile_digest="b" * 64, occurrences=len(occurrences),
                  unique_images=len(occurrences), decode_failed=(), detected_faces=len(occurrences),
                  unavailable_signals=(), costs=())
    return Evidence(job=job, inventory=inventory, g1=g1, seal_digest="c" * 64,
                    artifact_names=frozenset(), identities=document,
                    candidates=CandidateDocumentV2(version=2.1, faces=[]), images=(),
                    vectors=by_face, full_hashes=full_hashes, vector_profile=profile)


def cluster_of(evidence: Evidence):
    return importlib.import_module("artcurator.negotiation_clusters").clusters(evidence)[0]


def test_clusters_when_nine_distinct_images_is_ineligible() -> None:
    # Given: nine near-identical crops.
    report = cluster_of(build(tuple((1.0, 0.1 * i) for i in range(9))))
    # When / Then
    assert report.eligible is False
    assert "fewer-than-10-distinct-images" in report.eligibility_reasons
    assert len(report.representatives) == 9


def test_clusters_when_ten_identical_images_is_exactly_eligible() -> None:
    # Given: the boundary at ten distinct images with perfect coherence.
    report = cluster_of(build(tuple((1.0, 0.0) for _ in range(10))))
    # When / Then
    assert report.eligible is True and report.eligibility_reasons == ()
    assert report.coherence.median == 1.0 and report.coherence.p10 == 1.0


def test_clusters_when_two_far_groups_fail_median_and_p10() -> None:
    # Given: five crops at 0 degrees and five at 90 degrees.
    report = cluster_of(build(tuple((1.0, 0.0) for _ in range(5)) + tuple((0.0, 1.0) for _ in range(5))))
    # When / Then
    assert report.eligible is False
    assert report.coherence.median is not None and report.coherence.median < 0.90
    assert any("median-below" in reason for reason in report.eligibility_reasons)


def test_clusters_when_one_vector_is_invalid_reports_missingness() -> None:
    # Given: ten distinct images, one zero-norm crop.
    report = cluster_of(build(tuple([(1.0, 0.0)] * 9 + [None])))
    # When / Then: the invalid member stays in the denominator and never counts as coherent.
    assert report.eligible is False
    assert report.coherence.denominator == 10 and report.coherence.valid == 9
    assert "insufficient-or-invalid-same-profile-vectors" in report.eligibility_reasons
    assert len(report.representatives) == 10


def test_clusters_when_profile_is_absent_is_ineligible() -> None:
    # Given: valid vectors but no declared same-profile representation.
    report = cluster_of(build(tuple((1.0, 0.0) for _ in range(10)), profile=None))
    # When / Then
    assert report.eligible is False
    assert "insufficient-or-invalid-same-profile-vectors" in report.eligibility_reasons


def test_clusters_when_face_is_absent_from_the_snapshot_refuses() -> None:
    # Given: a sealed vector that does not resolve to a snapshot hash.
    broken = replace(build(tuple((1.0, 0.0) for _ in range(3))), full_hashes={})
    # When / Then
    with pytest.raises(IngestError, match="snapshot"):
        importlib.import_module("artcurator.negotiation_clusters").clusters(broken)


def test_representative_indices_when_replayed_are_exact_and_capped() -> None:
    # Given: fifteen distinct images; twelve is the representative cap.
    module = importlib.import_module("artcurator.negotiation_clusters")
    ids = tuple(f"{index + 1:064x}" for index in range(15))
    vectors = tuple((1.0, 0.02 * index) for index in range(15))
    matrix = np.asarray(vectors)
    matrix = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    # When
    first = module.representative_indices(ids, vectors)
    # Then: deterministic, capped, medoid first, lowest coherence second.
    assert len(first) == 12 and len(set(first)) == 12
    assert first == module.representative_indices(ids, vectors)
    medoid_scores = matrix @ matrix.sum(axis=0)
    assert first[0] == min(range(15), key=lambda index: (-float(medoid_scores[index]), ids[index]))
    scores = importlib.import_module("artcurator.negotiation_metrics").coherence(vectors).scores
    assert first[1] == min(range(15), key=lambda index: (scores[index], ids[index]))
    # Then: each remaining pick is the farthest point, ties broken by full hash.
    for position in range(2, len(first)):
        selected = first[:position]
        remaining = set(range(15)) - set(selected)
        expected = min(remaining, key=lambda index: (
            max(float(np.dot(matrix[index], matrix[prior])) for prior in selected), ids[index]))
        assert first[position] == expected


def test_representative_indices_when_vectors_are_invalid_uses_sorted_hashes() -> None:
    # Given
    module = importlib.import_module("artcurator.negotiation_clusters")
    ids = tuple(f"{index:064x}" for index in (5, 1, 9))
    # When
    selected = module.representative_indices(ids, (None, None, None))
    # Then: deterministic hash order, no fabricated medoid.
    assert [ids[index] for index in selected] == sorted(ids)
