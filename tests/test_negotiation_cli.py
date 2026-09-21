"""G2 commands must be reachable through the incumbent argparse CLI, like every other stage."""
import io
import json
import logging
import shutil
import sys
import uuid
from pathlib import Path

import pytest
from PIL import Image

from artcurator import cli, ingest
from artcurator.config import ROOT, Settings
from artcurator.ingest_schema import Job, Options
from artcurator.negotiation_consent import Decision, FolderSelection
from artcurator.negotiation_copy import COPY


class TextIO(io.StringIO):
    def reconfigure(self, **kwargs: object) -> None:
        pass


def run_cli(monkeypatch: pytest.MonkeyPatch, *argv: str) -> dict:
    stdout, stderr = TextIO(), TextIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(sys, "argv", ["artcurator", *argv])
    cli.main()
    return json.loads(stdout.getvalue())


def cleanup(out: Path) -> None:
    """Release the run.log FileHandler before removing the gitignored scratch job."""
    for handler in logging.getLogger().handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logging.getLogger().removeHandler(handler)
    shutil.rmtree(out, ignore_errors=True)


@pytest.fixture
def negotiated(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    for name, size, color in (("folder-a/red.png", (48, 32), "red"), ("folder-b/blue.png", (32, 48), "blue")):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color).save(path)
    (source / "folder-a/red-copy.png").write_bytes((source / "folder-a/red.png").read_bytes())
    out = ROOT / "out" / "ingest" / ("pytest-negotiation-" + uuid.uuid4().hex[:8])
    settings = Settings(input=source, out=out, references=source, posted=source,
                        characters_root=source, workers=1)
    ingest.run(settings, Options(analysis=False, reserve_bytes=0))
    try:
        yield out
    finally:
        cleanup(out)


def test_cli_when_negotiate_runs_prints_the_report(monkeypatch: pytest.MonkeyPatch, negotiated: Path) -> None:
    # When
    report = run_cli(monkeypatch, "ingest-negotiate", "--out", str(negotiated))
    # Then
    assert report["schema_version"] == "album-negotiation-v1"
    assert report["presentation"]["text"]["ingest_prompt"] == COPY["ingest_prompt"]
    assert report["report_digest"] and report["snapshot_digest"]


def test_cli_when_confirm_and_retract_run_updates_the_job(monkeypatch: pytest.MonkeyPatch,
                                                          negotiated: Path, tmp_path: Path) -> None:
    # Given
    report = run_cli(monkeypatch, "ingest-negotiate", "--out", str(negotiated))
    request = Decision(actor="local:pytest", operation_id="cli-op", affirmative=True,
                       report_digest=report["report_digest"], snapshot_digest=report["snapshot_digest"],
                       profile_digest=report["profile_digest"], mode="auto-first", inheritance="all",
                       folders=tuple(
                           FolderSelection(folder_id=folder["folder_id"], relation_type="undetermined")
                           for folder in report["folders"]),
                       cost_ceiling_seconds=0, acknowledged=tuple(report["limitations"]))
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(request.model_dump_json(), encoding="utf-8")
    # When
    receipt = run_cli(monkeypatch, "ingest-confirm", "--out", str(negotiated),
                      "--decision", str(decision_path))
    # Then
    assert receipt["context_enabled"] is False and receipt["mapping_mutations"] == 0
    assert Job.model_validate_json((negotiated / "job.json").read_bytes()).progress.stage == "FIRST-PASS"
    status = run_cli(monkeypatch, "ingest-retract", "--out", str(negotiated), "--actor", "local:pytest")
    assert status == {"status": "retracted", "active_consent": None, "mapping_mutations": 0}


def test_cli_when_dismissed_stays_waiting_then_can_still_confirm(monkeypatch: pytest.MonkeyPatch,
                                                                 negotiated: Path, tmp_path: Path) -> None:
    # Given
    report = run_cli(monkeypatch, "ingest-negotiate", "--out", str(negotiated))
    # When
    dismissed = run_cli(monkeypatch, "ingest-dismiss", "--out", str(negotiated))
    # Then
    assert dismissed == {"status": "waiting", "consent": None}
    state = Job.model_validate_json((negotiated / "job.json").read_bytes()).negotiation
    assert state.active is None and state.dismissed is True
    request = Decision(actor="local:pytest", operation_id="later-op", affirmative=True,
                       report_digest=report["report_digest"], snapshot_digest=report["snapshot_digest"],
                       profile_digest=report["profile_digest"], mode="human-first", inheritance="none",
                       folders=(), cost_ceiling_seconds=0, acknowledged=tuple(report["limitations"]))
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(request.model_dump_json(), encoding="utf-8")
    receipt = run_cli(monkeypatch, "ingest-confirm", "--out", str(negotiated),
                      "--decision", str(decision_path))
    assert receipt["decision"]["mode"] == "human-first"


def test_cli_when_confirm_has_no_decision_refuses(monkeypatch: pytest.MonkeyPatch, negotiated: Path) -> None:
    # When / Then: defaults are never consent.
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, "ingest-confirm", "--out", str(negotiated))


def test_cli_when_inventory_only_run_records_initial_intent(monkeypatch: pytest.MonkeyPatch,
                                                            tmp_path: Path) -> None:
    # Given
    source = tmp_path / "intent-source"
    source.mkdir()
    Image.new("RGB", (20, 20), "red").save(source / "one.png")
    out = ROOT / "out" / "ingest" / ("pytest-negotiation-" + uuid.uuid4().hex[:8])
    try:
        # When
        progress = run_cli(monkeypatch, "ingest-run", "--input", str(source), "--out", str(out),
                           "--inventory-only", "--reserve-gib", "0")
        # Then: the proactive prompt is recorded as intent before any analysis result.
        intent = json.loads((out / "initial-intent.json").read_bytes())
        assert intent["text"]["ingest_prompt"] == COPY["ingest_prompt"]
        assert intent["mapping_action_available"] is False
        assert (out / "launch.json").exists() and progress["stage"] == "PROPOSE"
    finally:
        cleanup(out)
