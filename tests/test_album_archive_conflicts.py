"""Conflict classification and admission tests; no real library access."""
from pathlib import Path

import pytest

from test_album_archive import inventory, proposal, tree


@pytest.mark.parametrize("kind", ["missing", "different_target", "name_collision", "case_hazard",
                                 "path_length", "unreadable", "cross_volume", "capacity"])
def test_conflict_when_present_is_reported_and_blocks_all_moves(tree, monkeypatch, kind: str) -> None:
    from artcurator import album_archive_plan as planner
    from artcurator.album_archive import derive, execute
    from artcurator.album_archive_schema import Approval
    from artcurator.album_map_schema import MappingError
    store, paths, root = tree
    clean = proposal(tree)
    request = clean.request
    target = next(item.dst for item in clean.items if item.src == paths[0])
    # Given one hazard in a two-file plan.
    match kind:
        case "missing":
            paths[0].unlink()
        case "different_target" | "name_collision":
            target.parent.mkdir(parents=True)
            target.write_bytes(b"different" if kind == "different_target" else paths[0].read_bytes())
        case "case_hazard":
            target.parent.mkdir(parents=True)
            target.with_name(target.name.upper()).write_bytes(b"different")
        case "path_length":
            request = request.model_copy(update={"export_root": root / ("x" * 180)})
        case "unreadable":
            original = planner.sha256
            def locked(path: Path) -> str:
                if path == paths[0]:
                    raise PermissionError("synthetic sharing violation")
                return original(path)
            monkeypatch.setattr(planner, "sha256", locked)
        case "cross_volume":
            monkeypatch.setattr(planner, "same_volume", lambda source, target: False)
        case "capacity":
            monkeypatch.setattr(planner, "free_bytes", lambda target: 0)
    before = inventory(root)
    # When previewing and attempting the independently confirmed conflicting plan.
    plan = derive(store, request)
    with pytest.raises(MappingError):
        execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    # Then every hazard is explicit; refusal leaves bytes, sizes, mtimes and file set intact.
    assert plan.summary.conflicts[kind] == (2 if kind in {"cross_volume", "capacity", "path_length"} else 1)
    assert inventory(root) == before


@pytest.mark.parametrize("change", ["source", "mapping", "mtime", "plan"])
def test_abort_when_plan_stale_is_byte_identical(tree, change: str) -> None:
    from artcurator.album_archive import execute
    from artcurator.album_archive_schema import Approval
    from artcurator.album_map_schema import MappingError
    import os
    store, paths, root = tree
    plan = proposal(tree)
    # Given a change after dry run.
    match change:
        case "source":
            paths[0].write_bytes(b"later bytes")
        case "mapping":
            store.undo("enroll")
        case "mtime":
            stat = paths[0].stat()
            os.utime(paths[0], ns=(stat.st_atime_ns, stat.st_mtime_ns + 10000000))
        case "plan":
            plan = plan.model_copy(update={"items": ()})
    before = inventory(root)
    # When executing an obsolete confirmation.
    with pytest.raises(MappingError):
        execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    # Then the abort is pre-mutation, not a partial export.
    assert inventory(root) == before


def test_prepared_when_unpublished_is_not_export_authority(tmp_path: Path) -> None:
    from artcurator.album_map import AlbumStore
    from artcurator.album_map_protocol import BatchRequest
    from artcurator.album_map_schema import MappingRecord, MappingError
    from artcurator.album_archive import derive
    from artcurator.album_archive_schema import ArchiveRequest
    with AlbumStore.initialize(tmp_path / "map.sqlite", "library") as store:
        request = BatchRequest.create(store.snapshot().root, (MappingRecord.pending("a" * 64, "library"),), "p")
        store.prepare(request, request.fingerprint())
        # When only a preparation exists, then no physical plan may derive from it.
        with pytest.raises(MappingError, match="committed"):
            derive(store, ArchiveRequest(source_root=tmp_path / "source", export_root=tmp_path / "export",
                                        ledger_root=tmp_path / "ledger"))


def test_locked_when_windows_byte_range_denies_read_is_reported(tree) -> None:
    import os
    if os.name != "nt":
        pytest.skip("Windows file sharing probe")
    import msvcrt
    _, paths, _ = tree
    # Given a real locked byte range, not a simulated API response.
    with paths[0].open("r+b") as handle:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            # When preview attempts hashing, then the file remains a reported unreadable conflict.
            plan = proposal(tree)
            assert plan.summary.conflicts["unreadable"] == 1
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
