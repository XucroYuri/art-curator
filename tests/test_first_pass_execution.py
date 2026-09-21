"""Real G2 authority and G5 store; synthetic sources only, no model downloads."""
import importlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from artcurator.album_map import AlbumStore
from artcurator.album_map_protocol import BatchRequest
from artcurator.album_map_schema import Decider, MappingError, MappingRecord
from artcurator.config import Settings
from artcurator.first_pass_schema import Evidence, Run
from artcurator.ingest_schema import IngestError
from test_ingest import corpus as corpus
from test_ingest import snapshot
from test_negotiation_consent import decision, prepared
from test_first_pass_boundaries import seed_references


def setup_run(corpus: Settings, mode="auto-first", grant_consent=True):
    api, report = prepared(corpus)
    if grant_consent:
        api.confirm(corpus.out, decision(report, mode, "none"))
    rows = tuple(Evidence(image_id=image, snapshot_digest=report.snapshot_digest,
        profile=report.analysis_profile_digest,
        model=dict(entity_id="character:a", entity_type="character", name="A", score=.96))
        for image in sorted({m.image_id for m in report.members}))
    run = Run(operation_id="first-pass:test", timestamp=datetime.now(timezone.utc),
        snapshot_digest=report.snapshot_digest, profile=report.analysis_profile_digest, rows=rows)
    return api, report, run


def test_execution_when_committed_undo_and_repeat_restore_before_images(corpus: Settings):
    # Given
    _, _, run = setup_run(corpus)
    module = importlib.import_module("artcurator.first_pass")
    source_before = snapshot(corpus.input)
    with AlbumStore.initialize(corpus.out / "album.sqlite", "test") as store:
        preview = module.preview(store.snapshot(), run, corpus.out)
        # When
        receipt = module.execute(store, preview, (corpus.out, preview.fingerprint()))
        replay = module.execute(store, preview, (corpus.out, preview.fingerprint()))
        inverse = store.undo(receipt.batch_id)
        repeat = store.undo(receipt.batch_id)
        # Then
        assert receipt == replay
        assert inverse == repeat and not inverse.partial_undo
        assert store.snapshot().records == ()
        assert receipt.mapping_mutations == len(run.rows)
        assert snapshot(corpus.input) == source_before


def test_undo_when_later_human_edit_preserves_it_and_reports_partial(corpus: Settings):
    # Given
    _, _, run = setup_run(corpus)
    module = importlib.import_module("artcurator.first_pass")
    with AlbumStore.initialize(corpus.out / "album.sqlite", "test") as store:
        preview = module.preview(store.snapshot(), run, corpus.out)
        receipt = module.execute(store, preview, (corpus.out, preview.fingerprint()))
        image = run.rows[0].image_id
        human = MappingRecord.pending(image, "test").model_copy(update={"source": "human",
            "decider": Decider(kind="human", identity="local:test", version="v1"),
            "disposition": "deferred", "notes": "keep my edit"})
        human = MappingRecord.model_validate_json(human.model_dump_json())
        edit = BatchRequest.create(store.snapshot().root, (human,), "human-edit")
        store.prepare(edit, edit.fingerprint())
        store.publish(edit.batch_id)
        # When
        inverse = store.undo(receipt.batch_id)
        # Then
        assert inverse.partial_undo and inverse.conflicts == (image,)
        assert store.snapshot().records[0].notes == "keep my edit"
        assert store.undo(receipt.batch_id) == inverse


@pytest.mark.parametrize("failure", ["revoked", "absent-measurement", "stale-measurement", "no-consent"])
def test_execution_when_authority_invalid_fails_closed(corpus: Settings, failure):
    # Given
    api, report, run = setup_run(corpus, grant_consent=failure != "no-consent")
    module = importlib.import_module("artcurator.first_pass")
    with AlbumStore.initialize(corpus.out / "album.sqlite", "test") as store:
        if failure == "no-consent":
            # When / Then: the very first preview cannot acquire implicit consent.
            with pytest.raises(MappingError, match="consent"):
                module.preview(store.snapshot(), run, corpus.out)
            assert store.snapshot().root.revision == 0
            return
        preview = module.preview(store.snapshot(), run, corpus.out)
        if failure in {"revoked", "no-consent"}:
            api.retract(corpus.out, "local:test")
        else:
            report_path = corpus.out / "negotiation" / "reports" / (report.report_digest + ".json")
            if failure == "absent-measurement":
                report_path.unlink()
            else:
                data = json.loads(report_path.read_bytes())
                data["snapshot_digest"] = "0" * 64
                report_path.write_text(json.dumps(data), encoding="utf-8")
        # When / Then
        with pytest.raises((IngestError, MappingError)):
            module.execute(store, preview, (corpus.out, preview.fingerprint()))
        assert store.snapshot().root.revision == 0


def test_inherit_only_when_previewed_has_zero_mutations(corpus: Settings):
    # Given
    _, _, run = setup_run(corpus, "inherit-only")
    module = importlib.import_module("artcurator.first_pass")
    with AlbumStore.initialize(corpus.out / "album.sqlite", "test") as store:
        # When
        preview = module.preview(store.snapshot(), run, corpus.out)
        # Then
        assert preview.request.changes == ()
        assert preview.audit.auto_ids == preview.audit.none_ids == ()


def test_cli_when_preview_execute_undo_and_revoked_error(corpus: Settings):
    # Given
    api, _, run = setup_run(corpus)
    db = corpus.out / "album.sqlite"
    with AlbumStore.initialize(db, "test"):
        pass
    path = corpus.out / "first-pass.json"
    path.write_text(run.model_dump_json(), encoding="utf-8")
    command = [sys.executable, "-m", "artcurator.cli", "album-map", "--album-db", str(db),
               "--first-pass-root", str(corpus.out), "--album-file", str(path)]
    # When: real CLI processes, JSON contract all the way through.
    result = subprocess.run([*command, "--album-op", "first-pass-preview"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    module = importlib.import_module("artcurator.first_pass_schema")
    preview = module.Preview.model_validate_json(result.stdout)
    path.write_text(preview.model_dump_json(), encoding="utf-8")
    commit = subprocess.run([*command, "--album-op", "first-pass-execute", "--album-authorize",
        preview.fingerprint()], capture_output=True, text=True)
    undo = subprocess.run([*command, "--album-op", "undo", "--album-batch", run.operation_id],
        capture_output=True, text=True)
    api.retract(corpus.out, "local:test")
    denied = subprocess.run([*command, "--album-op", "first-pass-execute", "--album-authorize",
        preview.fingerprint()], capture_output=True, text=True)
    # Then
    assert commit.returncode == undo.returncode == 0, commit.stderr + undo.stderr
    assert json.loads(commit.stdout)["mapping_mutations"] == len(run.rows)
    assert json.loads(undo.stdout)["inverse_of"] == run.operation_id
    assert denied.returncode != 0


def test_execution_when_auto_gates_pass_assigns_with_real_consent(corpus: Settings):
    # Given
    _, _, run = setup_run(corpus)
    module = importlib.import_module("artcurator.first_pass")
    with AlbumStore.initialize(corpus.out / "album.sqlite", "test") as store:
        row = seed_references(store)
        row = row.model_copy(update={"image_id": run.rows[0].image_id, "profile": run.profile,
            "snapshot_digest": run.snapshot_digest,
            "calibration": row.calibration.model_copy(update={"profile": run.profile})})
        run = run.model_copy(update={"rows": (row,)})
        preview = module.preview(store.snapshot(), run, corpus.out)
        # When
        receipt = module.execute(store, preview, (corpus.out, preview.fingerprint()))
        # Then
        record = next(r for r in store.snapshot().records if r.image_id == row.image_id)
        assert receipt.mapping_mutations == 1 and record.disposition == "assigned"
        assert record.relations[0].entity_id == "character:a" and not record.verified


def test_execution_when_audit_error_freezes_prepared_batch_and_offers_undo(corpus: Settings):
    # Given
    _, _, run = setup_run(corpus)
    module = importlib.import_module("artcurator.first_pass")
    audit_api = importlib.import_module("artcurator.first_pass_audit")
    with AlbumStore.initialize(corpus.out / "album.sqlite", "test") as store:
        preview = module.preview(store.snapshot(), run, corpus.out)
        store.prepare(preview.request, preview.request.fingerprint())
        incident = audit_api.Incident(batch_id=run.operation_id, image_id=run.rows[0].image_id,
            actor="local:test", timestamp=datetime.now(timezone.utc))
        # When
        response = audit_api.freeze(store, incident)
        # Then
        assert response.action == "review-or-undo-entire-batch"
        with pytest.raises(MappingError, match="audit-frozen"):
            module.execute(store, preview, (corpus.out, preview.fingerprint()))
        assert store.snapshot().root.revision == 0


def test_execution_when_preview_before_state_forged_is_rejected(corpus: Settings):
    # Given: client fabricates a before-image but reuses the real parent root.
    _, _, run = setup_run(corpus)
    module = importlib.import_module("artcurator.first_pass")
    with AlbumStore.initialize(corpus.out / "album.sqlite", "test") as store:
        fake = store.snapshot().model_copy(update={"records": (
            MappingRecord.pending(run.rows[0].image_id, "test").model_copy(update={
                "created_at": run.timestamp, "updated_at": run.timestamp}),)})
        preview = module.preview(fake, run, corpus.out)
        # When / Then
        with pytest.raises(MappingError, match="before-state"):
            module.execute(store, preview, (corpus.out, preview.fingerprint()))
        assert store.snapshot().root.revision == 0
