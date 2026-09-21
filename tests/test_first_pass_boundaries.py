"""Additional exact comparators for trust, subjects and independent metric units."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from artcurator.album_map import AlbumStore
from artcurator.album_map_protocol import BatchRequest
from artcurator.album_map_schema import Decider, MappingRecord, Relation, Subject
from artcurator.first_pass_mapping import stage
from artcurator.first_pass_policy import Policy, audit, evaluate
from artcurator.first_pass_schema import Run
from artcurator.negotiation_consent import ConsentReceipt, Decision, Prediction
from test_first_pass_policy import evidence, h


def consent(mode="auto-first"):
    return ConsentReceipt(receipt_id=h("consent"), decision=Decision(actor="local:test",
        operation_id="consent", affirmative=True, report_digest=h("report"), snapshot_digest=h("snapshot"),
        profile_digest=h("profile"), mode=mode, inheritance="none", cost_ceiling_seconds=0,
        acknowledged=()), timestamp="2026-09-22T00:00:00Z", consequences=(), members=(),
        inherited=(), predicted=Prediction(), evidence_refs=())


def seed_references(store):
    records = []
    refs = []
    for name in ("a", "b"):
        image = h("ref-" + name)
        pending = MappingRecord.pending(image, "test")
        relation = Relation(**{**pending.model_dump(exclude={"schema_version", "library_id", "revision",
            "parent_revision", "image_id", "occurrences", "subjects", "relations", "archived"}),
            "source": "human", "verified": True, "disposition": "assigned",
            "decider": Decider(kind="human", identity="local:test", version="v1"),
            "confirmation_members": (image, "relation-" + name)},
            relation_id="relation-" + name, entity_id="character:" + name, entity_type="character", role="depicts")
        records.append(pending.model_copy(update={"relations": (relation,)}))
        refs.append(relation.fingerprint())
    request = BatchRequest.create(store.snapshot().root, tuple(records), "references")
    store.prepare(request, request.fingerprint())
    store.publish(request.batch_id)
    row = evidence()
    visuals = [v.model_dump() for v in row.visuals]
    for visual, ref in zip(visuals, refs, strict=True):
        visual["human_support_refs"] = [ref]
    return evidence(visuals=visuals)


def test_auto_when_human_support_is_committed_records_full_provenance(tmp_path):
    # Given
    with AlbumStore.initialize(tmp_path / "album.sqlite", "test") as store:
        row = seed_references(store)
        run = Run(operation_id="first", timestamp=datetime.now(timezone.utc), snapshot_digest=h("snapshot"),
                  profile=h("profile"), rows=(row,))
        # When
        preview = stage(store.snapshot(), run, consent())
        store.prepare(preview.request, preview.request.fingerprint())
        store.publish(run.operation_id)
        # Then
        record = next(r for r in store.snapshot().records if r.image_id == row.image_id)
        assert preview.summary.tiers == {"auto": 1, "review": 0, "none": 0, "audit": 1}
        assert record.disposition == "assigned" and record.source == "memory"
        assert not record.verified and not record.relations[0].verified
        assert record.operation_id == record.batch_id == run.operation_id
        assert record.decider.version == run.policy.fingerprint()
        assert record.evidence_refs and record.scores.visual.value == .96
        assert record.created_at == record.updated_at == run.timestamp
        assert "audit-5%" in record.flags and store.snapshot().supports == ()


def test_auto_when_support_digest_is_invented_becomes_review(tmp_path):
    # Given
    with AlbumStore.initialize(tmp_path / "album.sqlite", "test") as store:
        run = Run(operation_id="first", timestamp=datetime.now(timezone.utc), snapshot_digest=h("snapshot"),
                  profile=h("profile"), rows=(evidence(),))
        # When
        preview = stage(store.snapshot(), run, consent())
        # Then
        assert preview.outcomes[0].tier == "review"
        assert "human-support-required" in preview.outcomes[0].reasons


def test_multiface_when_only_one_subject_evaluated_sibling_stays_pending(tmp_path):
    # Given
    with AlbumStore.initialize(tmp_path / "album.sqlite", "test") as store:
        row = seed_references(store)
        record = MappingRecord.pending(row.image_id, "test")
        fields = record.model_dump(include=set(Subject.model_fields) - {"subject_id", "crop_id", "detection_profile"})
        subjects = tuple(Subject(**fields, subject_id=name, crop_id=h(name), detection_profile=h("profile"))
                         for name in ("face-a", "face-b"))
        record = record.model_copy(update={"subjects": subjects})
        request = BatchRequest.create(store.snapshot().root, (record,), "faces")
        store.prepare(request, request.fingerprint())
        store.publish(request.batch_id)
        row = row.model_copy(update={"subject_id": "face-a", "crop_id": h("face-a")})
        run = Run(operation_id="first", timestamp=datetime.now(timezone.utc), snapshot_digest=h("snapshot"),
                  profile=h("profile"), rows=(row,))
        # When
        preview = stage(store.snapshot(), run, consent())
        # Then
        after = preview.request.changes[0].after
        assert after.subjects[0].disposition == "assigned"
        assert after.subjects[1] == subjects[1] and after.disposition == "pending"
        assert not after.verified and after.relations == ()


def test_model_when_contradicted_by_human_records_demotion_without_mutation(tmp_path):
    # Given
    with AlbumStore.initialize(tmp_path / "album.sqlite", "test") as store:
        row = seed_references(store)
        row = evidence(image_id=h("ref-a"), visuals=[], model=dict(entity_id="2b", entity_type="character",
            name="2B", score=.99, runner_up=.50))
        run = Run(operation_id="first", timestamp=datetime.now(timezone.utc), snapshot_digest=h("snapshot"),
                  profile=h("profile"), rows=(row,))
        # When
        preview = stage(store.snapshot(), run, consent())
        # Then
        assert preview.request.changes == ()
        assert "model_demoted" in preview.outcomes[0].reasons


def test_hypotheses_when_scores_differ_keep_separate_candidate_metrics(tmp_path):
    # Given
    with AlbumStore.initialize(tmp_path / "album.sqlite", "test") as store:
        row = evidence(model=dict(entity_id="2b", entity_type="character", name="2B", score=.99, runner_up=.50))
        run = Run(operation_id="first", timestamp=datetime.now(timezone.utc), snapshot_digest=h("snapshot"),
                  profile=h("profile"), rows=(row,))
        # When
        preview = stage(store.snapshot(), run, consent())
        # Then
        hypotheses = preview.request.changes[0].after.hypotheses
        assert hypotheses[1].scores.visual.value == .80
        assert hypotheses[2].scores.visual is None and hypotheses[2].scores.wd.value == .99


@pytest.mark.parametrize("kwargs", [dict(min_similarity=.89), dict(min_margin=.04),
    dict(enumeration=.4), dict(model_score=float("nan"))])
def test_policy_when_floor_lowered_or_unversioned_change_refuses(kwargs):
    # Given / When / Then
    with pytest.raises(ValidationError):
        Policy(**kwargs)


def test_audit_when_empty_strata_returns_no_items():
    # Given / When
    result = audit((), (), h("snapshot"))
    # Then
    assert result.auto_ids == result.none_ids == ()


def test_calibration_when_stricter_than_policy_controls_auto():
    # Given
    row = evidence()
    row = row.model_copy(update={"calibration": row.calibration.model_copy(update={"min_similarity": .97})})
    # When
    result = evaluate(row, Policy(), "auto-first")
    # Then
    assert result.tier == "review" and "similarity-below-policy" in result.reasons


def test_review_when_prior_contradiction_outlives_candidates_is_retained(tmp_path):
    # Given: disappearance of candidates is not acquittal of recorded contradiction.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "test") as store:
        record = MappingRecord.pending(h("query"), "test").model_copy(update={"flags": ("model_demoted",)})
        initial = BatchRequest.create(store.snapshot().root, (record,), "initial")
        store.prepare(initial, initial.fingerprint())
        store.publish(initial.batch_id)
        run = Run(operation_id="first", timestamp=datetime.now(timezone.utc), snapshot_digest=h("snapshot"),
                  profile=h("profile"), rows=(evidence(visuals=[], model=None),))
        # When
        preview = stage(store.snapshot(), run, consent())
        # Then
        assert preview.outcomes[0].tier == "review"
        assert "model_demoted" in preview.outcomes[0].reasons
