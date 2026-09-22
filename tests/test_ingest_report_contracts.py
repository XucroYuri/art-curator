"""Report capability data follows the actual backend command contracts."""
import json

import pytest

from artcurator.config import Settings
from artcurator.ingest import run
from artcurator.ingest_schema import Options
from test_ingest import corpus as corpus


def test_report_when_proposed_lists_delivered_backend_surfaces(corpus: Settings) -> None:
    # Given inventory-only G1 with no subsequent negotiation or mapping execution.
    options = Options(analysis=False, reserve_bytes=0)
    # When the report is generated.
    job = run(corpus, options)
    # Then delivered contracts are distinguished from unexecuted downstream work.
    report = json.loads((corpus.out / "revisions" / job.revision / "analysis-report.json").read_bytes())
    assert {"ingest-negotiate", "ingest-confirm"} <= set(report["backend_commands"])
    assert {"first-pass-preview", "first-pass-execute", "tray", "archive-plan", "archive-undo"} <= set(report["album_operations"])
    assert report["consent"] is None and report["mapping_mutations"] == 0
    assert all(row["measurement_status"] == "not_run" for row in report["folder_measurements"])


def test_report_when_command_registry_changes_uses_that_registry(corpus: Settings,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a command registry changed at the CLI boundary, not a second report list.
    from artcurator import ingest_cli
    monkeypatch.setattr(ingest_cli, "COMMANDS", ("ingest-negotiate",))
    # When proposing.
    job = run(corpus, Options(analysis=False, reserve_bytes=0))
    # Then both artifacts expose exactly the registered command, not a stale inventory.
    revision = corpus.out / "revisions" / job.revision
    report = json.loads((revision / "analysis-report.json").read_bytes())
    assert report["backend_commands"] == ["ingest-negotiate"]
    markdown = (revision / "analysis-report.md").read_text(encoding="utf-8")
    assert "`ingest-negotiate`" in markdown
    assert "`ingest-confirm`" not in markdown
