"""Real CLI subprocess walkthrough; fixture root is the only move destination."""
import json
import subprocess
import sys
from pathlib import Path

from artcurator.album_map import AlbumStore
from test_album_archive import enroll, inventory


def invoke(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "artcurator.cli", "album-map", *arguments],
                          capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)


def test_cli_when_preview_execute_status_undo_is_separately_authorized(tmp_path: Path) -> None:
    from artcurator.album_archive_schema import ArchivePlan, ArchiveRequest
    source = tmp_path / "source"
    source.mkdir()
    original = source / "fixture.png"
    original.write_bytes(b"synthetic CLI bytes")
    database = tmp_path / "album.sqlite"
    with AlbumStore.initialize(database, "library") as store:
        enroll(store, (original,))
    request = ArchiveRequest(source_root=source, export_root=tmp_path / "export", ledger_root=tmp_path / "ledger")
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    common = ["--album-db", str(database)]
    before = inventory(tmp_path)
    # When requesting a physical preview through the real command boundary.
    preview = invoke([*common, "--album-op", "archive-plan", "--album-file", str(request_path)])
    assert preview.returncode == 0, preview.stderr
    plan = ArchivePlan.model_validate_json(preview.stdout)
    assert inventory(tmp_path) == before
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
    before = inventory(tmp_path)
    refused = invoke([*common, "--album-op", "archive-execute", "--album-file", str(plan_path)])
    assert refused.returncode != 0
    assert inventory(tmp_path) == before
    executed = invoke([*common, "--album-op", "archive-execute", "--album-file", str(plan_path),
                       "--album-authorize", plan.digest, "--archive-token", plan.token])
    assert executed.returncode == 0, executed.stderr
    assert json.loads(executed.stdout)["done"] == 1
    # Mapping inverse is deliberately distinct; it must not restore physical files.
    inverse = invoke([*common, "--album-op", "undo", "--album-batch", "enroll"])
    assert inverse.returncode == 0, inverse.stderr
    assert not original.exists()
    status = invoke([*common, "--album-op", "archive-status", "--archive-ledger", str(tmp_path / "ledger")])
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["mapping_changed"] is True
    assert json.loads(status.stdout)["outstanding"] == 1
    undone = invoke([*common, "--album-op", "archive-undo", "--archive-ledger", str(tmp_path / "ledger")])
    assert undone.returncode == 0, undone.stderr
    assert json.loads(undone.stdout)["undone"] == 1
    assert original.read_bytes() == b"synthetic CLI bytes"
