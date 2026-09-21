"""Analytic folder measurement (ALBUM-FOLDER-v1 subset): denominators, weights, invariance."""

from artcurator.negotiation_folders import FolderPopulation, measure
from artcurator.negotiation_metrics import HumanLabel, ImageEvidence, Labels, proportion

SNAPSHOT = "d" * 64
FOLDER = "e" * 64


def images(count: int, *, representation: str = "whole-image", vector=(1.0, 0.0),
           faces: tuple[int | None, ...] | None = None, candidates=("A",),
           conflict=False) -> tuple[ImageEvidence, ...]:
    return tuple(ImageEvidence(image_id=f"{index:064x}", vector=vector, representation=representation,
                               profile="siglip-test", face_clusters=faces, candidates=candidates,
                               conflict=conflict) for index in range(count))


def population(rows: tuple[ImageEvidence, ...], *, path: str = "folder") -> FolderPopulation:
    return FolderPopulation(folder_id=FOLDER, path=path, images=rows,
                            occurrences=len(rows) + 2, unavailable_occurrences=0)


def labels(count: int, rows: tuple[ImageEvidence, ...], *, identity: str | None = "A",
           artist: str | None = None, entity: str | None = None,
           target: str | None = None, target_type: str = "character") -> Labels:
    return Labels(snapshot_digest=SNAPSHOT,
                  labels=tuple(HumanLabel(image_id=rows[index].image_id, identity=identity, artist=artist,
                                          entity=entity, actor="local:test", evidence_ref=f"human:{index}",
                                          independent=True) for index in range(count)),
                  targets={FOLDER: target} if target else {},
                  target_types={FOLDER: target_type} if target else {})


def test_measure_when_population_is_a_census_has_no_interval() -> None:
    # Given: 30 distinct images, all independently labelled.
    rows = images(30)
    # When
    report = measure(population(rows), labels(30, rows))
    # Then: exact descriptive fraction, never a model-correctness interval.
    assert report.purity.value == 1.0 and report.purity.interval is None
    assert report.purity.method == "census-exact" and report.unresolved_labels == 0


def test_measure_when_sample_is_smaller_than_population_uses_wilson() -> None:
    # Given: 120 distinct images sampled down to 100 with 90 labelled.
    rows = images(120)
    # When
    report = measure(population(rows), labels(90, rows))
    # Then
    assert report.sample == 100 and report.population == 120
    assert report.purity.method == "Wilson-95%-z=1.96-SRS"
    assert report.purity.interval is not None and report.purity.interval[0] < .90


def test_measure_when_labels_are_absent_reports_unavailable_never_zero() -> None:
    # Given
    rows = images(10)
    # When
    report = measure(population(rows), Labels(snapshot_digest=SNAPSHOT))
    # Then
    assert report.purity.value is None and report.purity.method == "unavailable"
    assert report.unresolved_labels == 10 and report.purity_identity is None


def test_measure_when_unresolved_labels_exist_keeps_them_in_the_denominator() -> None:
    # Given: 20 sampled images, only 15 labelled "A".
    rows = images(20)
    partial = Labels(snapshot_digest=SNAPSHOT,
                     labels=tuple(HumanLabel(image_id=row.image_id, identity="A", actor="local:test",
                                             evidence_ref=f"human:{row.image_id}", independent=True)
                                  for row in rows[:15]))
    # When
    report = measure(population(rows), partial)
    # Then: the largest identity count is 15/20, never 15/15.
    assert report.purity.numerator == 15 and report.purity.denominator == 20
    assert report.unresolved_labels == 5


def test_measure_when_identity_prior_qualifies_requires_30_labels_and_lower_bound() -> None:
    # Given: 120 images, all independently labelled for the declared target identity.
    rows = images(120)
    # When
    report = measure(population(rows), labels(len(rows), rows, target="A"))
    # Then
    assert report.coherence_admitted is True
    assert report.identity_prior_admitted is True
    assert report.identity_recommendation is True


def test_measure_when_identity_labels_are_below_thirty_is_not_admitted() -> None:
    # Given: 29 labels is one short of the constitutional minimum.
    rows = images(120)
    # When
    report = measure(population(rows), labels(29, rows, target="A"))
    # Then
    assert report.identity_prior_admitted is False and report.identity_recommendation is False


def test_measure_when_target_is_an_artist_keeps_proxy_and_agreement_unavailable() -> None:
    # Given: an explicit artist declaration rather than a character target.
    rows = images(10, candidates=("some-artist",))
    labels_for_target = labels(0, rows, artist="some-artist", entity="work-1", target="unknown-artist",
                               target_type="artist")
    # When
    report = measure(population(rows), labels_for_target)
    # Then: weak agreement and unresolved proxy D are N/A, not zero or 100%.
    assert report.weak_agreement.value is None and report.unresolved_proxy_D.value is None
    assert report.artist_agreement.value is None


def test_measure_when_folder_is_renamed_changes_no_measured_value() -> None:
    # Given: identical content under two folder names.
    rows = images(12, faces=(1,))
    baseline = measure(population(rows, path="old-name"), labels(0, rows))
    renamed = measure(population(rows, path="new-name/deeper"), labels(0, rows))
    # When / Then: path text locates the folder and never enters the measurements.
    excluded = {"folder_id", "path", "population_digest", "sample_digest"}
    assert baseline.model_dump(exclude=excluded) == renamed.model_dump(exclude=excluded)


def test_measure_when_one_face_cluster_dominates_passes_session_set() -> None:
    # Given: 30 images, each with exactly one detected face in cluster 1.
    rows = images(30, faces=(1,))
    # When
    report = measure(population(rows), labels(0, rows))
    # Then
    assert report.regimes.features.V == 1.0 and report.regimes.features.F == 1.0
    assert report.regimes.features.K == 1 and report.regimes.features.Q == 0.0
    assert "session-set" in report.regimes.passing


def test_measure_when_detection_is_missing_leaves_dependent_regimes_unavailable() -> None:
    # Given: whole-image vectors but no face evidence at all.
    rows = images(30, faces=None)
    # When
    report = measure(population(rows), labels(0, rows))
    # Then: missing face evidence cannot fabricate F/K/Q or a passing detector.
    assert report.regimes.features.F is None and report.regimes.features.K is None
    assert report.regimes.features.Q is None
    assert report.regimes.status == "insufficient-evidence"


def test_measure_when_artist_labels_span_entities_passes_artist_portfolio() -> None:
    # Given: 30 independently artist-labelled images across three works.
    rows = images(30)
    spanning = Labels(snapshot_digest=SNAPSHOT,
                      labels=tuple(HumanLabel(image_id=rows[index].image_id, artist="one-artist",
                                              entity=f"work-{index % 3}", actor="local:test",
                                              evidence_ref=f"human:{index}", independent=True)
                                   for index in range(30)))
    # When
    report = measure(population(rows), spanning)
    # Then
    assert report.artist_agreement.value == 1.0
    assert "artist-portfolio" in report.regimes.passing


def test_proportion_when_evidence_is_missing_is_unavailable_not_zero() -> None:
    # Given / When
    result = proportion(None, 0, 0)
    # Then
    assert result.value is None and result.interval is None and result.method == "unavailable"
