"""Physical export tests use synthetic bytes exclusively inside pytest temp trees."""
import hashlib
from pathlib import Path

import pytest

from artcurator.album_map import AlbumStore
from artcurator.album_map_protocol import BatchRequest
from artcurator.album_map_schema import Decider, MappingRecord, Occurrence, Relation


def inventory(root: Path) -> dict[str, tuple[int, int, str]]:
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns,
            hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.rglob("*") if p.is_file()}


def enroll(store: AlbumStore, paths: tuple[Path, ...]) -> None:
    records = []
    for index, path in enumerate(paths):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        pending = MappingRecord.pending(digest, "library")
        fields = dict(disposition="assigned", source="human", verified=True,
                      decider=Decider(kind="human", identity="fixture", version="1"),
                      confirmation_members=(digest, f"r{index}"))
        relation = Relation(**{**pending.model_dump(exclude={"schema_version", "library_id", "revision",
            "parent_revision", "image_id", "occurrences", "subjects", "relations", "archived"}), **fields},
            relation_id=f"r{index}", entity_id="fixture-character", entity_type="character", role="depicts")
        records.append(MappingRecord.model_validate({**pending.model_dump(), **fields,
            "relations": (relation,), "occurrences": (Occurrence(occurrence_id=f"o{index}",
            locator=str(path), observed_hash=digest, available=True),)}))
    request = BatchRequest.create(store.snapshot().root, tuple(records), "enroll")
    store.prepare(request, request.fingerprint())
    store.publish("enroll")


@pytest.fixture
def tree(tmp_path: Path):
    root = tmp_path / "fixture"
    source = root / "source"
    source.mkdir(parents=True)
    paths = tuple(source / f"{index}.png" for index in range(2))
    for index, path in enumerate(paths):
        path.write_bytes(f"synthetic-{index}".encode())
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        enroll(store, paths)
        yield store, paths, root


def proposal(tree):
    from artcurator.album_archive import derive
    from artcurator.album_archive_schema import ArchiveRequest
    store, _, root = tree
    return derive(store, ArchiveRequest(source_root=root / "source", export_root=root / "export",
                                       ledger_root=root / "ledger"))


def test_plan_when_derived_is_deterministic_and_read_only(tree) -> None:
    # Given committed synthetic occurrences.
    _, _, root = tree
    before = inventory(root)
    # When deriving twice.
    first, second = proposal(tree), proposal(tree)
    # Then the whole fixture is unchanged and the plan binds revision 1.
    assert first == second
    assert inventory(root) == before
    assert first.mapping.revision == 1
    assert first.summary.targets == {"角色/fixture-character": 2}
    assert first.summary.ready == 2
    assert first.digest == first.fingerprint()


@pytest.mark.parametrize("digest,token", [("", ""), ("wrong", "wrong"), ("correct", "")])
def test_refusal_when_confirmation_missing_is_byte_identical(tree, digest: str, token: str) -> None:
    from artcurator.album_archive import execute
    from artcurator.album_archive_schema import Approval
    from artcurator.album_map_schema import MappingError
    # Given a dry-run and complete byte/size/mtime inventory.
    store, _, root = tree
    plan = proposal(tree)
    before = inventory(root)
    # When execution lacks either explicit digest or token.
    with pytest.raises(MappingError):
        execute(store, plan, Approval(digest=plan.digest if digest == "correct" else digest, token=token))
    # Then even ledger directories/files have not been created.
    assert inventory(root) == before
    assert not (root / "ledger").exists()


def test_execute_when_confirmed_moves_without_changing_mapping(tree) -> None:
    from artcurator.album_archive import execute
    from artcurator.album_archive_schema import Approval
    # Given a committed map and independently reviewed physical plan.
    store, paths, _ = tree
    before = store.snapshot()
    plan = proposal(tree)
    # When confirmed.
    result = execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    # Then bytes are relocated but virtual authority remains byte-for-byte equal.
    assert result.done == 2
    assert all(not path.exists() for path in paths)
    assert all(item.dst.read_bytes() == f"synthetic-{i}".encode() for i, item in
               enumerate(sorted(plan.items, key=lambda item: item.src.name)))
    assert store.snapshot() == before


def test_repeat_when_run_completed_is_idempotent(tree) -> None:
    from artcurator.album_archive import execute
    from artcurator.album_archive_schema import Approval
    store, _, root = tree
    plan = proposal(tree)
    approval = Approval(digest=plan.digest, token=plan.token)
    execute(store, plan, approval)
    before = inventory(root)
    # When retrying the exact run.
    result = execute(store, plan, approval)
    # Then no file or ledger is rewritten.
    assert result.already_done == 2
    assert inventory(root) == before


@pytest.mark.parametrize("edited", [False, True])
def test_undo_when_target_changed_preserves_later_edits(tree, edited: bool) -> None:
    from artcurator.album_archive import execute, undo
    from artcurator.album_archive_schema import Approval
    store, paths, root = tree
    plan = proposal(tree)
    execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    if edited:
        plan.items[0].dst.write_bytes(b"later human edit")
    # When undoing the whole ledger.
    result = undo(root / "ledger")
    # Then eligible originals return and later edits remain untouched.
    assert result.undone == (1 if edited else 2)
    assert result.partial_undo == edited
    if edited:
        assert plan.items[0].dst.read_bytes() == b"later human edit"
    else:
        assert all(path.exists() for path in paths)


def test_repeat_undo_when_later_original_is_replaced_does_not_touch_it(tree) -> None:
    from artcurator.album_archive import execute, undo
    from artcurator.album_archive_schema import Approval
    store, paths, root = tree
    plan = proposal(tree)
    execute(store, plan, Approval(digest=plan.digest, token=plan.token))
    undo(root / "ledger")
    paths[0].write_bytes(b"human replacement")
    before = inventory(root)
    # When repeating an already acknowledged inverse.
    result = undo(root / "ledger")
    # Then the terminal ledger token guards against ABA/redeletion.
    assert result.already_undone == 2
    assert inventory(root) == before
