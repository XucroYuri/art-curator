"""Analytic ALBUM-FOLDER-v1 subset, not labelled accuracy qualification."""
import importlib

import pytest


def test_confirm_when_proposal_ready_is_a_supported_transition() -> None:
    # Given
    from artcurator.ingest_schema import transition
    # When
    result = transition("PROPOSE", "CONFIRM")
    # Then
    assert result == "CONFIRM"


@pytest.mark.parametrize("n,expected", [(0, None), (1, None), (29, 1.0), (30, 1.0), (100, 1.0)])
def test_coherence_when_identical_vectors_uses_nonself(n: int, expected: float | None) -> None:
    # Given
    metrics = importlib.import_module("artcurator.negotiation_metrics")
    # When
    result = metrics.coherence(tuple((1.0, 0.0) for _ in range(n)))
    # Then
    assert result.median == expected
    assert result.valid == n


def test_coherence_when_invalid_vectors_preserves_missingness() -> None:
    # Given
    metrics = importlib.import_module("artcurator.negotiation_metrics")
    # When
    result = metrics.coherence(((1., 0.), (1., 0.), (0., 0.), None))
    # Then
    assert (result.denominator, result.valid, result.missing, result.median) == (4, 2, 2, 1.)


def test_wilson_when_all_thirty_positive_matches_independent_golden() -> None:
    # Given
    metrics = importlib.import_module("artcurator.negotiation_metrics")
    # When
    result = metrics.proportion(30, 30, 100)
    # Then: z=1.96, all-positive lower = n/(n+z*z).
    assert result.interval == pytest.approx((0.8864829086, 1.), abs=1e-9)


def test_proportion_when_census_has_no_population_interval() -> None:
    # Given
    metrics = importlib.import_module("artcurator.negotiation_metrics")
    # When
    result = metrics.proportion(27, 30, 30)
    # Then
    assert result.value == .9
    assert result.interval is None
    assert result.method == "census-exact"


@pytest.mark.parametrize("v,f,k,q,expected", [
    (.9, .8, 1, 0., ("session-set",)),
    (.79, .49, 3, .1, ("mixed-pile",)),
    (.85, .79, 2, .5, ("scenario/documentary",)),
    (.8, .5, 3, .49, ()),
    (None, None, None, None, ()),
])
def test_regime_when_boundary_features_are_measured(v, f, k, q, expected) -> None:
    # Given
    module = importlib.import_module("artcurator.negotiation_regimes")
    features = module.Features(valid_images=30, eligible_faces=30, V=v, F=f, K=k, Q=q)
    # When
    result = module.detect(features)
    # Then
    assert result.passing == expected
    assert result.confidence is None


def test_regime_when_artist_evidence_overlaps_returns_ambiguous() -> None:
    # Given
    module = importlib.import_module("artcurator.negotiation_regimes")
    features = module.Features(valid_images=30, eligible_faces=30, V=.9, F=.8,
                               A=.8, artist_labels=30, entities=3)
    # When
    result = module.detect(features)
    # Then
    assert result.status == "ambiguous"
    assert result.passing == ("session-set", "artist-portfolio")
