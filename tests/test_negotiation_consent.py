"""Real sealed G1 -> G2 -> withdrawal integration, inventory-only corpus."""
import importlib
from pathlib import Path

import pytest
from PIL import Image

from artcurator.config import Settings
from artcurator.ingest import run
from artcurator.ingest_schema import IngestError, Job, Options
from test_ingest import corpus as corpus
from test_ingest import snapshot


def prepared(corpus: Settings):
    run(corpus, Options(analysis=False, reserve_bytes=0))
    api = importlib.import_module("artcurator.negotiation")
    return api, api.prepare(corpus.out)


def decision(report, mode: str, scope: str):
    schema = importlib.import_module("artcurator.negotiation_consent")
    folders = () if scope == "none" else tuple(
        schema.FolderSelection(folder_id=f.folder_id, relation_type="undetermined")
        for f in report.folders)
    return schema.Decision(actor="local:test", operation_id="test-confirm",
        affirmative=True, report_digest=report.report_digest, snapshot_digest=report.snapshot_digest,
        profile_digest=report.profile_digest, mode=mode, inheritance=scope, folders=folders,
        cost_ceiling_seconds=0, acknowledged=report.limitations)


@pytest.mark.parametrize("mode", ["human-first", "auto-first", "inherit-only"])
@pytest.mark.parametrize("scope", ["all", "selected", "none"])
def test_consent_when_explicit_combination_is_durable(corpus: Settings, mode: str, scope: str) -> None:
    # Given
    api, report = prepared(corpus)
    before = snapshot(corpus.input)
    request = decision(report, mode, scope)
    # When
    receipt = api.confirm(corpus.out, request)
    # Then
    job = Job.model_validate_json((corpus.out / "job.json").read_bytes())
    assert job.progress.stage == "FIRST-PASS"
    assert job.progress.status == "paused"
    assert receipt.decision == request
    assert receipt.context_enabled is False
    assert receipt.mapping_mutations == 0
    assert snapshot(corpus.input) == before
    assert api.confirm(corpus.out, request) == receipt


def test_consent_when_stale_report_fails_closed(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    request = decision(report, "auto-first", "all").model_copy(update={"report_digest": "0" * 64})
    # When / Then
    with pytest.raises(IngestError, match="digest"):
        api.confirm(corpus.out, request)


def test_consent_when_no_decision_remains_waiting(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    # When
    api.dismiss(corpus.out)
    # Then
    job = Job.model_validate_json((corpus.out / "job.json").read_bytes())
    assert job.progress.stage == "CONFIRM"
    assert job.negotiation.active is None
    assert report.folders[0].purity.value is None


def test_consent_when_new_member_is_consumed_refuses(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    api.confirm(corpus.out, decision(report, "human-first", "all"))
    Image.new("RGB", (10, 10), "green").save(corpus.input / "future.png")
    # When / Then
    with pytest.raises(IngestError, match="member"):
        api.authorize(corpus.out, ("future.png",))


def test_consent_when_frozen_source_mutated_fails_closed(corpus: Settings) -> None:
    # Given: active consent over an unchanged synthetic corpus.
    api, report = prepared(corpus)
    api.confirm(corpus.out, decision(report, "auto-first", "all"))
    # When: an external process changes a frozen member after confirmation.
    Image.new("RGB", (48, 32), "yellow").save(corpus.input / "folder-a/red.png")
    # Then: consumption revalidates every frozen hash and refuses without re-consent.
    with pytest.raises(IngestError, match="changed"):
        api.authorize(corpus.out, ("folder-a/red.png",))
    fresh = decision(report, "human-first", "none").model_copy(update={"operation_id": "after-mutation"})
    with pytest.raises(IngestError, match="changed"):
        api.confirm(corpus.out, fresh)


def test_retraction_when_restarted_leaves_only_inactive_history(corpus: Settings) -> None:
    # Given
    api, report = prepared(corpus)
    before = snapshot(corpus.out / "revisions")
    request = decision(report, "inherit-only", "all")
    api.confirm(corpus.out, request)
    # When
    api.retract(corpus.out, "local:test")
    # Then
    job = Job.model_validate_json((corpus.out / "job.json").read_bytes())
    assert job.negotiation.active is None
    assert all(r.status == "revoked" for r in job.negotiation.history)
    assert snapshot(corpus.out / "revisions") == before
    with pytest.raises(IngestError, match="consent"):
        api.authorize(corpus.out, ("folder-a/red.png",))
    with pytest.raises(IngestError, match="operation"):
        api.confirm(corpus.out, request)


def test_report_when_unsealed_sidecar_added_never_consumes_it(corpus: Settings) -> None:
    # Given
    job = run(corpus, Options(analysis=False, reserve_bytes=0))
    (corpus.out / "revisions" / job.revision / "identities.json").write_text("{}")
    api = importlib.import_module("artcurator.negotiation")
    # When
    report = api.prepare(corpus.out)
    # Then
    assert report.clusters == ()
    assert report.global_evidence.faces is None


def test_report_when_sealed_artifact_tampered_refuses(corpus: Settings) -> None:
    # Given
    job = run(corpus, Options(analysis=False, reserve_bytes=0))
    (corpus.out / "revisions" / job.revision / "analysis-report.json").write_text("{}")
    api = importlib.import_module("artcurator.negotiation")
    # When / Then
    with pytest.raises(IngestError, match="seal"):
        api.prepare(corpus.out)
