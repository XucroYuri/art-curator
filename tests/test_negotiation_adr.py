"""ADR-0005 conditions proven through G2 behavior; no contextual grouping is implemented."""
import importlib
from pathlib import Path

import pytest
from PIL import Image
from test_ingest import corpus as corpus
from test_negotiation_consent import decision, prepared

from artcurator.config import Settings
from artcurator.ingest import run
from artcurator.ingest_schema import IngestError, Job, Options


def job_of(root: Path) -> Job:
    return Job.model_validate_json((root / "job.json").read_bytes())


def test_authorize_when_snapshot_advanced_without_new_consent_fails_closed(corpus: Settings) -> None:
    # Given: consent bound to the current snapshot, then a corpus member is added and ingested.
    api, report = prepared(corpus)
    api.confirm(corpus.out, decision(report, "auto-first", "all"))
    Image.new("RGB", (10, 10), "green").save(corpus.input / "future.png")
    advanced = run(corpus, Options(analysis=False, reserve_bytes=0))
    # When / Then: the old receipt cannot authorize anything in the new revision.
    assert advanced.revision != report.snapshot_digest
    with pytest.raises(IngestError, match="stale"):
        api.authorize(corpus.out, ("folder-a/red.png",))


def test_authorize_when_path_is_not_a_frozen_member_fails_closed(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    api.confirm(corpus.out, decision(report, "human-first", "all"))
    Image.new("RGB", (10, 10), "green").save(corpus.input / "future.png")
    # When / Then: a path outside the frozen consent snapshot is not covered by membership.
    with pytest.raises(IngestError, match="member"):
        api.authorize(corpus.out, ("future.png",))


def test_retract_when_report_artifact_is_gone_still_removes_authority(corpus: Settings) -> None:
    # Given: active consent whose report has been removed from disk.
    api, report = prepared(corpus)
    api.confirm(corpus.out, decision(report, "inherit-only", "all"))
    state = job_of(corpus.out).negotiation
    (corpus.out / state.report_path).unlink()
    revisions = {p.name for p in (corpus.out / "revisions").iterdir()}
    # When: revocation does not require readable evidence.
    api.retract(corpus.out, "local:test")
    # Then: authority is gone, history is inactive-only, and no derived tree was created.
    after = job_of(corpus.out).negotiation
    assert after.active is None
    assert [r.status for r in after.history] == ["revoked"]
    assert {p.name for p in (corpus.out / "revisions").iterdir()} == revisions
    with pytest.raises(IngestError, match="consent"):
        api.authorize(corpus.out, ("folder-a/red.png",))


def test_retract_when_already_stale_never_resurrects_on_resume(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    api.confirm(corpus.out, decision(report, "human-first", "all"))
    api.retract(corpus.out, "local:test")
    # When: reopening/resuming the waiting job after revocation.
    api.prepare(corpus.out)
    # Then: revoked consent stays revoked and cannot be replayed.
    state = job_of(corpus.out).negotiation
    assert state.active is None and all(r.status == "revoked" for r in state.history)
    with pytest.raises(IngestError, match="consent"):
        api.authorize(corpus.out, ("folder-a/red.png",))


def test_consent_when_granted_never_authorizes_context_or_mapping(corpus: Settings) -> None:
    # Given: the broadest affirmative choice available in G2.
    api, report = prepared(corpus)
    request = decision(report, "auto-first", "all")
    # When
    receipt = api.confirm(corpus.out, request)
    # Then: recorded consequences, but no contextual use, no mapping, no execution.
    assert receipt.context_enabled is False
    assert receipt.mapping_mutations == 0
    assert "context-disabled" in receipt.consequences
    assert "G4-execution-guarded" in receipt.consequences
    assert receipt.predicted.auto is None and receipt.predicted.reason.startswith("Unknown")
    assert api.authorize(corpus.out, (receipt.members[0].path,)) == receipt
    assert job_of(corpus.out).progress.status == "paused"


def test_report_when_evidence_is_missing_reports_unavailable_never_defaulted(corpus: Settings) -> None:
    # Given: inventory-only corpus with no models, labels or whole-image vectors.
    _, report = prepared(corpus)
    # When / Then: unavailable is explicit and never a zero or a fabricated 100%.
    assert report.global_evidence.faces is None
    assert report.global_evidence.whole_image_unknown is None
    assert report.global_evidence.crop_unknown.method == "unavailable"
    assert report.global_evidence.crop_unknown.value is None
    assert report.recommendations.cluster_coverage is None
    for folder in report.folders:
        assert folder.purity.value is None and folder.purity.method == "unavailable"
        assert folder.coherence.median is None and folder.coherence.valid == 0
        assert folder.regimes.status == "insufficient-evidence"
        assert folder.identity_recommendation is False
        assert folder.context_enabled is False
    assert report.presentation.text["purity_missing"].startswith("没有独立人工标签")


def test_prepare_when_labels_are_not_snapshot_bound_refuses(corpus: Settings) -> None:
    # Given
    metrics = importlib.import_module("artcurator.negotiation_metrics")
    api, report = prepared(corpus)
    labels = metrics.Labels(snapshot_digest="0" * 64)
    # When / Then
    with pytest.raises(IngestError, match="snapshot"):
        api.prepare(corpus.out, labels)


def test_prepare_when_label_is_unattributed_refuses(corpus: Settings) -> None:
    # Given
    metrics = importlib.import_module("artcurator.negotiation_metrics")
    api, report = prepared(corpus)
    label = metrics.HumanLabel(image_id=report.members[0].image_id, identity="A",
                               actor=" ", evidence_ref="human:test", independent=True)
    labels = metrics.Labels(snapshot_digest=report.snapshot_digest, labels=(label,))
    # When / Then
    with pytest.raises(IngestError, match="unattributed"):
        api.prepare(corpus.out, labels)


def test_reprepare_when_receipt_active_never_silently_supersedes_it(corpus: Settings) -> None:
    # Given: active consent, then the user prepares a differently labelled proposal.
    metrics = importlib.import_module("artcurator.negotiation_metrics")
    api, report = prepared(corpus)
    receipt = api.confirm(corpus.out, decision(report, "human-first", "all"))
    label = metrics.HumanLabel(image_id=report.members[0].image_id, identity="A",
                               actor="local:test", evidence_ref="human:test", independent=True)
    labels = metrics.Labels(snapshot_digest=report.snapshot_digest, labels=(label,))
    second = api.prepare(corpus.out, labels)
    # Then: the old proposal is superseded, but the receipt keeps its status until revoked.
    assert second.report_digest != report.report_digest
    state = job_of(corpus.out).negotiation
    kept = next(r for r in state.history if r.receipt_id == receipt.receipt_id)
    assert kept.status == "active" and state.active == receipt.receipt_id
    with pytest.raises(IngestError, match="stale"):
        api.authorize(corpus.out, (receipt.members[0].path,))


def test_current_when_report_file_is_missing_fails_closed(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    state = job_of(corpus.out).negotiation
    (corpus.out / state.report_path).unlink()
    # When / Then
    with pytest.raises(IngestError, match="missing"):
        api.current(corpus.out)


def test_confirm_when_receipt_replaces_revoked_one_needs_a_new_operation(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    request = decision(report, "human-first", "none")
    api.confirm(corpus.out, request)
    api.retract(corpus.out, "local:test")
    # When / Then: the old operation is spent; a scoped new decision is required.
    with pytest.raises(IngestError, match="operation"):
        api.confirm(corpus.out, request)
    fresh = request.model_copy(update={"operation_id": "second-attempt"})
    receipt = api.confirm(corpus.out, fresh)
    assert receipt.decision.operation_id == "second-attempt"
