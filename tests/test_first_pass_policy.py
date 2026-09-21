"""Analytic ALBUM-MAP-v1 / ALBUM-CONFUSABLE-v1 policy fixtures."""
import importlib
from hashlib import sha256

import pytest


def api():
    return importlib.import_module("artcurator.first_pass_policy")


def h(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def evidence(**updates):
    data = dict(image_id=h("query"), profile=h("profile"), snapshot_digest=h("snapshot"),
        visuals=[dict(entity_id="character:a", entity_type="character", name="A", source="memory",
            centroid=.96, individual=.96, reference_images=[h("ref-a")],
            reference_crops=[h("crop-a")], human_support_refs=[h("human-a")]),
            dict(entity_id="character:b", entity_type="character", name="B", source="anchors",
            centroid=.80, individual=.80, reference_images=[h("ref-b")],
            reference_crops=[h("crop-b")], human_support_refs=[h("human-b")])],
        calibration=dict(profile=h("profile"), reference_digest=h("refs"),
            min_similarity=.90, min_margin=.05, method="reference-only-leave-one-out"),
        reference_digest=h("refs"))
    data.update(updates)
    return api().Evidence.model_validate(data)


@pytest.mark.parametrize(("score", "margin", "tier"), [(.90, .05, "auto"),
    (.899999, .05, "review"), (.90, .049999, "review")])
def test_auto_when_exact_or_below_threshold(score, margin, tier):
    # Given: same-winner centroid/individual margins, two independent references.
    row = evidence()
    visuals = [v.model_dump() for v in row.visuals]
    visuals[0].update(centroid=score, individual=score)
    visuals[1].update(centroid=score-margin, individual=score-margin)
    row = evidence(visuals=visuals)
    # When
    result = api().evaluate(row, api().Policy(), "auto-first")
    # Then
    assert result.tier == tier


def test_143_high_score_2b_proposals_when_contradicted_all_review():
    # Given: every proposal clears .85/.20; independent evidence names another character.
    rows = [evidence(image_id=h(str(i)), model=dict(entity_id="2b_(nier:automata)",
        entity_type="character", name="2B", score=.97, runner_up=.60)) for i in range(143)]
    # When
    results = [api().evaluate(row, api().Policy(), "auto-first") for row in rows]
    # Then
    assert len(results) == 143
    assert {r.tier for r in results} == {"review"}
    assert all("model_demoted" in r.reasons for r in results)


@pytest.mark.parametrize("change", [dict(calibration=None), dict(visuals=[]),
    dict(valid=False), dict(conflicts=["prior-conflict"])])
def test_auto_when_prerequisite_missing_never_assigns(change):
    # Given
    row = evidence(**change)
    # When
    result = api().evaluate(row, api().Policy(), "auto-first")
    # Then
    assert result.tier != "auto"


@pytest.mark.parametrize("mode,tier", [("human-first", "review"), ("inherit-only", "none")])
def test_mode_when_recorded_disallows_auto(mode, tier):
    # Given
    row = evidence()
    # When
    result = api().evaluate(row, api().Policy(), mode)
    # Then
    assert result.tier == tier


@pytest.mark.parametrize("score,tier", [(.35, "none"), (.350001, "review"), (.99, "review")])
def test_model_when_no_references_never_auto(score, tier):
    # Given
    row = evidence(visuals=[], model=dict(entity_id="character:a", entity_type="character",
        name="A", score=score, runner_up=None))
    # When
    result = api().evaluate(row, api().Policy(), "auto-first")
    # Then
    assert result.tier == tier


def test_self_match_when_only_winner_support_is_query_is_review():
    # Given
    row = evidence()
    visuals = [v.model_dump() for v in row.visuals]
    visuals[0]["reference_images"] = [row.image_id]
    # When
    result = api().evaluate(evidence(visuals=visuals), api().Policy(), "auto-first")
    # Then
    assert result.tier == "review"


def test_audit_when_strata_have_21_and_1_rows_samples_separately():
    # Given
    auto = tuple(h(str(i)) for i in range(21))
    none = (h("none"),)
    # When
    result = api().audit(auto, none, h("snapshot"))
    reverse = api().audit(tuple(reversed(auto)), none, h("snapshot"))
    # Then: independent ceil(.05*n), order-independent SHA-256 ranking.
    assert result == reverse
    assert len(result.auto_ids) == 2 and len(result.none_ids) == 1
    expected = sorted(auto, key=lambda image: (h(f"album-first-pass-v1\n{h('snapshot')}\nauto\n{image}"), image))[:2]
    assert result.auto_ids == tuple(expected)


@pytest.mark.parametrize("variation", ["individual-disagrees", "tied-leaders", "self-crop", "profile-invalid", "one-identity"])
def test_auto_when_visual_gate_fails_is_review(variation):
    # Given
    row = evidence()
    visuals = [v.model_dump() for v in row.visuals]
    changes = {}
    if variation == "individual-disagrees":
        visuals[1]["individual"] = .99
    elif variation == "tied-leaders":
        visuals[1]["individual"] = .96
    elif variation == "self-crop":
        changes = dict(subject_id="face", crop_id=h("crop-a"))
    elif variation == "profile-invalid":
        visuals[0]["profile_valid"] = False
    else:
        visuals = visuals[:1]
    # When
    result = api().evaluate(evidence(visuals=visuals, **changes), api().Policy(), "auto-first")
    # Then
    assert result.tier == "review"


def test_model_when_compact_runner_missing_uses_point35_lower_bound():
    # Given
    row = evidence(visuals=[], model=dict(entity_id="a", entity_type="character", name="A", score=.85))
    # When
    result = api().evaluate(row, api().Policy(), "auto-first")
    # Then
    assert result.scores.model_margin.value == .50
    assert result.scores.model_margin.bound == "lower"


def test_contradiction_when_independent_cosine_below_auto_still_demotes():
    # Given
    row = evidence()
    visuals = [v.model_dump() for v in row.visuals[:1]]
    visuals[0].update(centroid=.36, individual=.36)
    row = evidence(visuals=visuals, model=dict(entity_id="2b", entity_type="character", name="2B", score=.99))
    # When
    result = api().evaluate(row, api().Policy(), "auto-first")
    # Then
    assert "model_demoted" in result.reasons and result.tier == "review"


def test_contradiction_when_tied_leaders_include_model_is_ambiguous_not_demoted():
    # Given
    row = evidence()
    visuals = [v.model_dump() for v in row.visuals]
    visuals[1].update(centroid=.96, individual=.96)
    row = evidence(visuals=visuals, model=dict(entity_id="character:a", entity_type="character", name="A", score=.99))
    # When
    result = api().evaluate(row, api().Policy(), "auto-first")
    # Then
    assert result.tier == "review" and "model_demoted" not in result.reasons


def test_unknown_when_no_candidate_is_normal_none_not_forced_identity():
    # Given: analytic replay of missingness count, not a new corpus precision run.
    rows = [evidence(image_id=h(str(i)), visuals=[], calibration=None) for i in range(1285)]
    # When
    results = [api().evaluate(row, api().Policy(), "auto-first") for row in rows]
    # Then
    assert all(r.tier == "none" and r.winner is None and r.eligible_none for r in results)


@pytest.mark.parametrize("field", ["profile", "reference_digest"])
def test_calibration_when_binding_stale_is_review(field):
    # Given
    row = evidence()
    row = row.model_copy(update={"calibration": row.calibration.model_copy(update={field: h("stale")})})
    # When
    result = api().evaluate(row, api().Policy(), "auto-first")
    # Then
    assert result.tier == "review" and "calibration-required" in result.reasons
