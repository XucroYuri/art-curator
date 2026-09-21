"""Physical cutpoints, safe Windows rename, and inverse restart behavior."""
import os
from pathlib import Path

import pytest

from test_album_archive import inventory, proposal, tree


def test_copy_when_confirmed_orders_verification_ledger_then_unlink(tree, monkeypatch) -> None:
    from artcurator import _moves, album_archive, journal
    from artcurator.album_archive_schema import Approval
    store, paths, _ = tree
    plan = proposal(tree)
    events: list[str] = []
    copy, digest, unlink, publish = _moves.copy_bytes, _moves.sha256, Path.unlink, journal.publish
    def observe_copy(src, dst):
        events.append("copy:" + src.name)
        return copy(src, dst)
    def observe_digest(path):
        events.append("hash:" + str(path))
        return digest(path)
    def observe_unlink(path, *args, **kwargs):
        if path in paths:
            events.append("unlink:" + path.name)
        return unlink(path, *args, **kwargs)
    def observe_publish(path, record):
        result = publish(path, record)
        if record.entry:
            events.append("ledger:" + record.entry.src.name)
        return result
    monkeypatch.setattr(_moves, "copy_bytes", observe_copy)
    monkeypatch.setattr(_moves, "sha256", observe_digest)
    monkeypatch.setattr(Path, "unlink", observe_unlink)
    monkeypatch.setattr("artcurator.album_archive_ledger.publish", observe_publish)
    # When exporting through the real byte-copy and fsynced journal.
    album_archive.execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    # Then each destination/source verification precedes its ledger and source unlink.
    for item in plan.items:
        copied = events.index("copy:" + item.src.name)
        logged = events.index("ledger:" + item.src.name)
        removed = events.index("unlink:" + item.src.name)
        assert copied < events.index("hash:" + str(item.dst), copied) < logged < removed
        assert copied < events.index("hash:" + str(item.src), copied) < logged


@pytest.mark.parametrize("cut", ["copy", "verify", "ledger", "unlink", "after_unlink"])
def test_interruption_when_copy_cutpoint_fails_retains_original_digest(tree, monkeypatch, cut: str) -> None:
    from artcurator import _moves, album_archive
    from artcurator.album_archive_schema import Approval
    from artcurator import album_archive_ledger as ledger
    store, paths, root = tree
    plan = proposal(tree)
    first = plan.items[0]
    publish, unlink = ledger.publish, Path.unlink
    def fail_copy(src, dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"partial")
        raise OSError("injected copy failure")
    def corrupt_copy(src, dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"bad digest")
    def fail_ledger(path, record):
        if record.entry:
            raise OSError("injected ledger failure")
        return publish(path, record)
    def fail_unlink(path, *args, **kwargs):
        if path == first.src:
            if cut == "after_unlink":
                unlink(path, *args, **kwargs)
            raise OSError("injected unlink failure")
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        match cut:
            case "copy":
                patch.setattr(_moves, "copy_bytes", fail_copy)
            case "verify":
                patch.setattr(_moves, "copy_bytes", corrupt_copy)
            case "ledger":
                patch.setattr(ledger, "publish", fail_ledger)
            case "unlink" | "after_unlink":
                patch.setattr(Path, "unlink", fail_unlink)
        # When interrupted at the selected real move seam.
        with pytest.raises((OSError, _moves.MoveError)):
            album_archive.execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    # Then each original digest still exists; incomplete copies are never deleted.
    for item in plan.items:
        assert any(path.is_file() and _moves.sha256(path) == item.sha256 for path in (item.src, item.dst))
    result = album_archive.undo(root / "ledger")
    assert result.partial_undo == (cut in {"copy", "verify", "ledger"})
    assert all(path.exists() for path in paths)


def test_resume_when_done_precedes_source_unlink_is_restart_safe(tree, monkeypatch) -> None:
    from artcurator import album_archive
    from artcurator.album_archive_schema import Approval
    store, _, _ = tree
    plan = proposal(tree)
    original = Path.unlink
    def fail(path, *args, **kwargs):
        if path == plan.items[0].src:
            raise PermissionError("locked")
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail)
        with pytest.raises(PermissionError):
            album_archive.execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    # When resuming from disk with a newly parsed plan and reconstructed ledger.
    result = album_archive.execute(store, type(plan).model_validate_json(plan.model_dump_json()),
                                   Approval(digest=plan.digest, token=plan.token))
    # Then both files finish once without another copy of the staged item.
    assert result.done == 2


def test_undo_when_acknowledgement_lost_recovers_without_overwrite(tree, monkeypatch) -> None:
    from artcurator import album_archive, album_archive_ledger
    from artcurator.album_archive_schema import Approval
    store, paths, root = tree
    plan = proposal(tree)
    album_archive.execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    original = album_archive_ledger.publish
    def fail(path, record):
        if record.entry and record.entry.status == "undone":
            raise OSError("inverse acknowledgement lost")
        return original(path, record)
    with monkeypatch.context() as patch:
        patch.setattr(album_archive_ledger, "publish", fail)
        album_archive.undo(root / "ledger")
    # When restarting the inverse with restored sources and absent destinations.
    result = album_archive.undo(root / "ledger")
    # Then restore's already_undone path safely acknowledges both files.
    assert result.already_undone == 2
    assert all(path.exists() for path in paths)


@pytest.mark.skipif(os.name != "nt", reason="Windows no-replace rename contract")
@pytest.mark.parametrize("interrupt", [False, True])
def test_rename_when_explicitly_selected_is_recoverable(tree, monkeypatch, interrupt: bool) -> None:
    from artcurator import album_archive, album_archive_ledger
    from artcurator.album_archive_schema import Approval, ArchiveRequest
    store, paths, root = tree
    request = ArchiveRequest(source_root=root / "source", export_root=root / "export", ledger_root=root / "ledger",
                             transfer="rename")
    plan = album_archive.derive(store, request)
    original = album_archive_ledger.publish
    def fail(path, record):
        if record.entry:
            raise OSError("after rename before done")
        return original(path, record)
    # When same-volume Windows rename is requested and its acknowledgement can be lost.
    with monkeypatch.context() as patch:
        if interrupt:
            patch.setattr(album_archive_ledger, "publish", fail)
            with pytest.raises(OSError):
                album_archive.execute(store, plan, Approval(digest=plan.digest, token=plan.token))
        else:
            album_archive.execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    result = album_archive.undo(root / "ledger")
    # Then the source inode-bound intent permits safe inverse recovery.
    assert not result.partial_undo
    assert all(path.exists() for path in paths)
