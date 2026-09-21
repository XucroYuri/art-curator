"""G2 CONFIRM barrier: explicit decisions only, never inferred consent or execution."""
from pathlib import Path

import pytest
from test_ingest import corpus as corpus
from test_negotiation_consent import decision, prepared

from artcurator.config import Settings
from artcurator.ingest_schema import IngestError, Job, Stage, transition


def job_of(root: Path) -> Job:
    return Job.model_validate_json((root / "job.json").read_bytes())


@pytest.mark.parametrize("target", ["FIRST-PASS", "REVIEW", "ARCHIVE"])
def test_transition_when_future_stage_requested_stays_guarded(target: str) -> None:
    # Given / When / Then
    with pytest.raises(NotImplementedError):
        transition("CONFIRM", target)


def test_transition_when_confirm_follows_propose_is_supported() -> None:
    # Given / When / Then
    assert transition("PROPOSE", "CONFIRM") == Stage.CONFIRM


def test_transition_when_confirm_skips_propose_is_refused() -> None:
    # Given / When / Then
    with pytest.raises(IngestError, match="invalid"):
        transition("ANALYZE", "CONFIRM")


def test_confirm_when_limitations_unacknowledged_refuses(corpus: Settings) -> None:
    # Given: a decision that bypassed affirmative acknowledgement with model_copy.
    api, report = prepared(corpus)
    request = decision(report, "human-first", "none").model_copy(update={"acknowledged": ()})
    # When / Then
    with pytest.raises(IngestError, match="acknowledg"):
        api.confirm(corpus.out, request)


def test_confirm_when_threshold_override_attempted_refuses(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    request = decision(report, "human-first", "none").model_copy(
        update={"threshold_overrides": ("median>=0.5",)})
    # When / Then
    with pytest.raises(IngestError, match="threshold"):
        api.confirm(corpus.out, request)


def test_confirm_when_duplicate_directory_selected_refuses(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    request = decision(report, "human-first", "selected")
    mutated = request.model_copy(update={"folders": (*request.folders, request.folders[0])})
    # When / Then
    with pytest.raises(IngestError, match="duplicate or unknown"):
        api.confirm(corpus.out, mutated)


def test_confirm_when_all_inheritance_omits_a_directory_refuses(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    request = decision(report, "human-first", "all")
    mutated = request.model_copy(update={"folders": request.folders[:-1]})
    # When / Then
    with pytest.raises(IngestError, match="every directory"):
        api.confirm(corpus.out, mutated)


def test_confirm_when_none_inheritance_carries_folders_refuses(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    request = decision(report, "human-first", "selected")
    mutated = request.model_copy(update={"inheritance": "none"})
    # When / Then
    with pytest.raises(IngestError, match="none inheritance"):
        api.confirm(corpus.out, mutated)


def test_confirm_when_inherit_only_plus_none_is_browse_only(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    # When
    receipt = api.confirm(corpus.out, decision(report, "inherit-only", "none"))
    # Then
    assert "browse-only-not-classification" in receipt.consequences
    assert receipt.context_enabled is False
    assert receipt.mapping_mutations == 0
    assert job_of(corpus.out).progress.stage == Stage.FIRST_PASS


def test_dismiss_when_no_response_never_grants_consent(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    # When
    api.dismiss(corpus.out)
    # Then: still waiting, no receipt, and a later affirmative decision remains possible.
    state = job_of(corpus.out).negotiation
    assert state.active is None and state.dismissed is True and state.history == ()
    receipt = api.confirm(corpus.out, decision(report, "human-first", "none"))
    assert receipt.decision.affirmative is True


def test_dismiss_when_consent_active_requires_explicit_retraction(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    api.confirm(corpus.out, decision(report, "human-first", "none"))
    # When / Then
    with pytest.raises(IngestError, match="retraction"):
        api.dismiss(corpus.out)


def test_confirm_when_second_choice_arrives_while_active_refuses(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    api.confirm(corpus.out, decision(report, "human-first", "none"))
    second = decision(report, "auto-first", "none").model_copy(update={"operation_id": "second"})
    # When / Then
    with pytest.raises(IngestError, match="retract"):
        api.confirm(corpus.out, second)


def test_confirm_when_operation_id_reused_with_other_decision_refuses(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    first = decision(report, "human-first", "none")
    api.confirm(corpus.out, first)
    # When / Then
    with pytest.raises(IngestError, match="operation"):
        api.confirm(corpus.out, first.model_copy(update={"mode": "auto-first"}))


def test_confirm_when_decision_is_replayed_returns_the_same_receipt(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    request = decision(report, "auto-first", "all")
    # When
    first = api.confirm(corpus.out, request)
    replay = api.confirm(corpus.out, request)
    # Then: exactly one receipt; a replay is the same confirmation, not a new authority.
    history = job_of(corpus.out).negotiation.history
    assert replay == first and len(history) == 1


def test_authorize_when_member_consented_returns_intent_only(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    receipt = api.confirm(corpus.out, decision(report, "auto-first", "all"))
    # When
    returned = api.authorize(corpus.out, (receipt.members[0].path,))
    # Then: consent intent only; no mapping, cache or context authority.
    assert returned == receipt
    assert returned.context_enabled is False and returned.mapping_mutations == 0


def test_prepare_when_reopened_keeps_one_report_and_zero_receipts(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    # When
    again = api.prepare(corpus.out)
    # Then
    state = job_of(corpus.out).negotiation
    assert again.report_digest == report.report_digest
    assert state.history == () and state.active is None
