"""Pure first-pass projection, preserving human rows, sibling subjects and history."""
from collections import Counter
from typing import assert_never

from .album_map_protocol import Artifact, BatchRequest, Mutation, Snapshot
from .album_map_schema import (
    DecisionFields, Decider, Hypothesis, MappingError, MappingRecord, Metric, Relation, Scores, Subject, summarize,
)
from .first_pass_policy import audit, evaluate
from .first_pass_schema import Evidence, ModelAdvice, Outcome, Preview, Run, Summary, Visual
from .negotiation_consent import ConsentReceipt


def protected(target: DecisionFields) -> bool:
    """Never overwrite human decisions, accepted relations, or explicit exclusions."""
    return (target.source == "human" or target.verified or
            bool(target.cluster_membership and target.cluster_membership.excluded))


def bound_outcome(row: Evidence, snapshot: Snapshot, run: Run, /) -> Evidence:
    """Resolve human support digests against live committed reference relations."""
    records = {record.image_id: record for record in snapshot.records}
    visuals = []
    for visual in row.visuals:
        supports = set()
        for image in visual.reference_images:
            reference = records.get(image)
            if reference is None:
                continue
            relations = (*reference.relations, *(r for s in reference.subjects for r in s.relations))
            for relation in relations:
                if relation.entity_id == visual.entity_id and relation.entity_type == visual.entity_type:
                    if relation.verified and relation.source == "human" and relation.disposition == "assigned":
                        supports.add(relation.fingerprint())
        visuals.append(visual.model_copy(update={
            "human_support_refs": tuple(ref for ref in visual.human_support_refs if ref in supports)}))
    return row.model_copy(update={"visuals": tuple(visuals), "valid": row.valid and row.profile == run.profile})


def project(target: MappingRecord | Subject, outcome: Outcome, context: tuple[Run, Evidence, tuple[str, ...]]) -> MappingRecord | Subject:
    """One target only; no reference membership is created by policy assignment."""
    run, row, refs = context
    hypotheses = list(target.hypotheses)
    for entity in (*row.visuals, *((row.model,) if row.model else ())):
        match entity:
            case Visual():
                scores = Scores(visual=Metric(value=entity.centroid, unit="cosine", profile=row.profile))
            case ModelAdvice():
                scores = Scores(wd=outcome.scores.wd, model_margin=outcome.scores.model_margin)
            case unreachable:
                assert_never(unreachable)
        hypotheses.append(Hypothesis(entity_id=entity.entity_id, entity_type=entity.entity_type,
            name=entity.name, scores=scores, evidence_refs=(row.fingerprint(),)))
    fields = dict(source=outcome.source, decider=Decider(kind="policy", identity="album-first-pass",
        version=run.policy.fingerprint()), scores=outcome.scores, verified=False, confirmation_members=(),
        evidence_refs=tuple(dict.fromkeys((*target.evidence_refs, *refs))),
        flags=tuple(dict.fromkeys((*target.flags, *outcome.reasons,
            *("first-pass-conflict:" + reason for reason in row.conflicts)))),
        updated_at=run.timestamp, batch_id=run.operation_id, operation_id=run.operation_id,
        hypotheses=tuple(hypotheses))
    match outcome.tier:
        case "auto":
            winner = outcome.winner
            if winner is None:
                raise MappingError("auto-winner-required")
            relation = Relation(**fields, disposition="assigned", created_at=run.timestamp,
                relation_id=f"{run.operation_id}:{row.image_id}:{row.subject_id or 'image'}",
                entity_id=winner.entity_id, entity_type=winner.entity_type, role="depicts", subject_id=row.subject_id)
            fields.update(disposition="assigned", relations=(*target.relations, relation))
        case "review":
            fields.update(disposition="deferred" if target.disposition == "deferred" else "hypothesis")
        case "none":
            pass
        case unreachable:
            assert_never(unreachable)
    return type(target).model_validate({**target.model_dump(), **fields})


def stage(snapshot: Snapshot, run: Run, consent: ConsentReceipt) -> Preview:
    """Deterministic preview with complete proposed after-images and auditable reasons."""
    records = {r.image_id: r for r in snapshot.records}
    outcomes = []
    changes = {}
    consent_artifact = Artifact.capture(consent.model_dump_json().encode(), "first-pass-consent")
    run_artifact = Artifact.capture(run.canonical(), "first-pass-input")
    artifacts = [consent_artifact, run_artifact, Artifact.capture(b"unavailable-evidence")]
    refs = (consent_artifact.digest, run_artifact.digest)
    for row in sorted(run.rows, key=lambda r: (r.image_id, r.subject_id or "")):
        original = records.get(row.image_id)
        record = changes.get(row.image_id, original or MappingRecord.pending(row.image_id, snapshot.root.library_id))
        # Stable supplied operational timestamp, not wall-clock preview generation.
        if original is None:
            record = record.model_copy(update={"created_at": run.timestamp, "updated_at": run.timestamp})
        target: MappingRecord | Subject = record
        if row.subject_id is not None:
            target = next((s for s in record.subjects if s.subject_id == row.subject_id), record)
            if not isinstance(target, Subject) or target.crop_id != row.crop_id or target.detection_profile != row.profile:
                raise MappingError("first-pass-subject-binding")
        elif record.subjects:
            raise MappingError("first-pass-requires-explicit-subject")
        checked = bound_outcome(row, snapshot, run)
        retained = tuple(flag for flag in target.flags if flag == "model_demoted"
                         or flag.startswith("first-pass-conflict:"))
        checked = checked.model_copy(update={"conflicts": tuple(dict.fromkeys((*checked.conflicts, *retained)))})
        outcome = evaluate(checked, run.policy, consent.decision.mode)
        if protected(target) or any(protected(r) for r in target.relations):
            human_ids = {r.entity_id for r in target.relations if protected(r) and r.disposition == "assigned"}
            demotion = ("model_demoted",) if row.model and human_ids and row.model.entity_id not in human_ids else ()
            outcome = outcome.model_copy(update={"tier": "review", "eligible_none": False,
                "reasons": tuple(dict.fromkeys((*outcome.reasons, *demotion, "human-or-exclusion-preserved")))})
            outcomes.append(outcome)
            continue
        outcomes.append(outcome)
        if consent.decision.mode == "inherit-only":
            continue
        artifacts.append(Artifact.capture(row.canonical(), "first-pass-evidence"))
        updated = project(target, outcome, (run, row, (*refs, row.fingerprint())))
        match updated:
            case Subject():
                subjects = tuple(updated if s.subject_id == updated.subject_id else s for s in record.subjects)
                record = MappingRecord.model_validate({**record.model_dump(), "subjects": subjects,
                    "disposition": summarize(tuple(s.disposition for s in subjects)), "verified": False,
                    "source": outcome.source, "decider": updated.decider, "scores": updated.scores,
                    "evidence_refs": tuple(dict.fromkeys((*record.evidence_refs, *updated.evidence_refs))),
                    "updated_at": run.timestamp, "batch_id": run.operation_id, "operation_id": run.operation_id})
            case MappingRecord():
                record = updated
            case unreachable:
                assert_never(unreachable)
        changes[row.image_id] = record
    # An image with any review subject is already scheduled, not in either audit stratum.
    groups: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        groups.setdefault(outcome.image_id, []).append(outcome)
    auto = tuple(image for image, rows in groups.items() if all(r.tier == "auto" for r in rows))
    none = tuple(image for image, rows in groups.items() if all(r.tier == "none" and r.eligible_none for r in rows))
    sampled = audit(auto, none, run.snapshot_digest)
    for image in (*sampled.auto_ids, *sampled.none_ids):
        changes[image] = changes[image].model_copy(update={"flags": (*changes[image].flags, "audit-5%")})
    counts = Counter(o.tier for o in outcomes)
    summary = Summary(tiers={**{t: counts[t] for t in ("auto", "review", "none")},
        "audit": len(sampled.auto_ids) + len(sampled.none_ids)},
        reasons=dict(Counter(reason for o in outcomes for reason in o.reasons)),
        evidence_bases=dict(Counter(o.source for o in outcomes)), changed_images=len(changes))
    artifacts.extend((Artifact.capture(sampled.canonical(), "first-pass-audit"),
                      Artifact.capture(summary.canonical(), "first-pass-summary")))
    request = BatchRequest(parent=snapshot.root, batch_id=run.operation_id, operation_id=run.operation_id,
        name="First pass: " + run.policy.fingerprint(), consent_ref=consent_artifact.digest,
        artifacts=tuple(artifacts), changes=tuple(Mutation(key=image, after=MappingRecord.model_validate({
            **record.model_dump(), "revision": snapshot.root.revision + 1, "parent_revision": snapshot.root.revision}))
            for image, record in sorted(changes.items())))
    return Preview(run=run, consent=consent, before=snapshot, outcomes=tuple(outcomes), audit=sampled,
                   summary=summary, request=request)
