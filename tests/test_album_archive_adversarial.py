"""Adversarial namespace, ledger, source edits and inverse-copy cutpoints."""
from pathlib import Path

import pytest

from test_album_archive import inventory, proposal, tree


def test_planned_case_alias_when_different_filenames_blocks_both(tree) -> None:
    from artcurator.album_map_protocol import BatchRequest
    from artcurator.album_map_schema import MappingRecord
    store, _, _ = tree
    changed = tuple(MappingRecord.model_validate({**record.model_dump(), "relations": (
        record.relations[0].model_copy(update={"entity_id": name}),)})
        for record, name in zip(store.snapshot().records, ("Hero", "hero"), strict=True))
    request = BatchRequest.create(store.snapshot().root, changed, "case-folders")
    store.prepare(request, request.fingerprint())
    store.publish("case-folders")
    # When distinct target filenames share differently cased planned directories.
    plan = proposal(tree)
    # Then Windows folder aliases are explicit for every affected item.
    assert plan.summary.conflicts["case_hazard"] == 2


def test_undo_when_interrupted_after_reverse_copy_can_resume(tree, monkeypatch) -> None:
    from artcurator.album_archive import execute, undo
    from artcurator.album_archive_schema import Approval
    store, paths, root = tree
    plan = proposal(tree)
    execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    original = Path.unlink
    def fail(path, *args, **kwargs):
        if path == plan.items[0].dst:
            raise PermissionError("inverse source locked")
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail)
        first = undo(root / "ledger")
    assert first.partial_undo
    # When inverse restarts with both copies and the new original inode.
    result = undo(root / "ledger")
    # Then the unchanged reverse copy is accepted, never overwritten.
    assert not result.partial_undo
    assert result.undone == 1
    assert result.already_undone == 1
    assert all(path.exists() for path in paths)


@pytest.mark.parametrize("side", ["original", "target_same_bytes", "target_mtime"])
def test_undo_when_human_edits_are_later_preserves_files(tree, side: str) -> None:
    import os
    from artcurator.album_archive import execute, undo
    from artcurator.album_archive_schema import Approval
    store, _, root = tree
    plan = proposal(tree)
    execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    item = plan.items[0]
    match side:
        case "original":
            item.src.write_bytes(b"later original")
            protected = item.src
        case "target_same_bytes":
            content = item.dst.read_bytes()
            replacement = item.dst.with_suffix(".replacement")
            replacement.write_bytes(content)
            os.replace(replacement, item.dst)
            protected = item.dst
        case "target_mtime":
            stamp = item.dst.stat()
            os.utime(item.dst, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 10000000))
            protected = item.dst
    before = protected.read_bytes(), protected.stat().st_mtime_ns
    # When the inverse encounters a later human file or even a same-byte replacement.
    result = undo(root / "ledger")
    # Then later bytes/metadata survive and the outcome is explicitly partial.
    assert result.partial_undo
    assert (protected.read_bytes(), protected.stat().st_mtime_ns) == before


@pytest.mark.parametrize("corruption", ["torn", "digest"])
def test_undo_when_journal_corrupt_fails_closed_without_repair(tree, corruption: str) -> None:
    from artcurator.album_archive import execute, undo
    from artcurator.album_archive_schema import Approval
    from artcurator.album_map_schema import MappingError
    store, _, root = tree
    plan = proposal(tree)
    execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    path = root / "ledger" / "disposition_log.jsonl"
    payload = path.read_bytes()
    path.write_bytes(payload + b"torn" if corruption == "torn" else payload.replace(b"copy-intent", b"bad-intent"))
    before = inventory(root)
    # When an untrusted ledger cannot establish reverse authority.
    with pytest.raises(MappingError):
        undo(root / "ledger")
    # Then preserve all bytes as evidence; no recency repair or fabricated inverse.
    assert inventory(root) == before


def test_confirmed_empty_plan_when_everything_excluded_has_no_writes(tree) -> None:
    from artcurator.album_archive import derive, execute
    from artcurator.album_archive_schema import Approval, Selection
    from artcurator.album_map_protocol import BatchRequest
    store, _, root = tree
    record = store.snapshot().records[0]
    changed = record.model_copy(update={"verified": False})
    request = BatchRequest.create(store.snapshot().root, (changed,), "unverified")
    store.prepare(request, request.fingerprint())
    store.publish("unverified")
    original = proposal(tree)
    plan = derive(store, original.request.model_copy(update={"selections": (Selection(image_id=record.image_id,
        occurrence_id=record.occurrences[0].occurrence_id, relation_id=record.relations[0].relation_id),)}))
    before = inventory(root)
    # When explicit selection is excluded because it lacks reviewed inclusion.
    result = execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    # Then no empty run artifacts are created.
    assert result.done == 0
    assert inventory(root) == before
