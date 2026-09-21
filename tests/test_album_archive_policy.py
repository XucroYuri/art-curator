"""Typed namespace, disposition, no-op and explicit selection contracts."""
from pathlib import Path

import pytest

from test_album_archive import enroll, inventory, proposal, tree


@pytest.mark.parametrize("entity_type,folder", [("work", "IP/作品"), ("artist", "画师"),
    ("original-series", "原创系列"), ("character", "角色"), ("ordinary-person", "普通人"),
    ("undetermined", "未定")])
def test_namespace_when_selected_is_typed(tree, entity_type: str, folder: str) -> None:
    from artcurator.album_map_protocol import BatchRequest
    from artcurator.album_map_schema import MappingRecord
    store, _, _ = tree
    record = store.snapshot().records[0]
    relation = record.relations[0].model_copy(update={"entity_type": entity_type})
    changed = MappingRecord.model_validate({**record.model_dump(), "relations": (relation,)})
    request = BatchRequest.create(store.snapshot().root, (changed,), "typed")
    store.prepare(request, request.fingerprint())
    store.publish("typed")
    # When planning a selected typed relation, then its namespace is never flattened to character.
    plan = proposal(tree)
    assert any(i.target == folder + "/fixture-character" for i in plan.items)


@pytest.mark.parametrize("state", ["assigned", "hypothesis", "deferred", "unknown-foreign",
                                  "original-design", "ordinary", "non-character", "pending"])
def test_disposition_when_uncertain_requires_reviewed_inclusion(tree, state: str) -> None:
    from artcurator.album_map_protocol import BatchRequest
    from artcurator.album_map_schema import MappingRecord
    from artcurator.album_archive import derive
    from artcurator.album_archive_schema import Selection
    store, _, _ = tree
    record = store.snapshot().records[0]
    changed = MappingRecord.model_validate({**record.model_dump(), "disposition": state})
    request = BatchRequest.create(store.snapshot().root, (changed,), "state")
    store.prepare(request, request.fingerprint())
    store.publish("state")
    # When deriving default and separately reviewed selection plans.
    default = proposal(tree)
    selection = Selection(image_id=record.image_id, occurrence_id=record.occurrences[0].occurrence_id,
                          relation_id=record.relations[0].relation_id, reviewed_inclusion=True)
    reviewed = derive(store, default.request.model_copy(update={"selections": (selection,)}))
    # Then uncertain states stay excluded unless expressly included without changing their mapping.
    assert len(default.items) == (2 if state in {"assigned", "original-design", "ordinary", "non-character"} else 1)
    assert len(reviewed.items) == 1
    assert store.snapshot().records[0].disposition == state


def test_already_correct_when_same_locator_is_noop(tmp_path: Path) -> None:
    from artcurator.album_map import AlbumStore
    from artcurator.album_archive import derive, execute
    from artcurator.album_archive_schema import Approval, ArchiveRequest
    root = tmp_path / "files"
    path = root / "角色" / "fixture-character" / "0.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"synthetic")
    with AlbumStore.initialize(tmp_path / "map.sqlite", "library") as store:
        enroll(store, (path,))
        request = ArchiveRequest(source_root=root, export_root=root, ledger_root=tmp_path / "ledger")
        before = inventory(root)
        plan = derive(store, request)
        # When a confirmed plan already matches the physical layout.
        result = execute(store, plan, Approval(digest=plan.digest, token=plan.token))
        # Then nothing in the source tree changes.
        assert plan.summary.conflicts["already_correct"] == 1
        assert result.no_op == 1
        assert result.done == 0
        assert inventory(root) == before


def test_multimembership_when_ambiguous_is_excluded_until_explicit_selection(tree) -> None:
    from artcurator.album_map_protocol import BatchRequest
    from artcurator.album_map_schema import MappingRecord
    from artcurator.album_archive import derive
    from artcurator.album_archive_schema import Selection
    store, _, _ = tree
    record = store.snapshot().records[0]
    added = record.relations[0].model_copy(update={"relation_id": "second", "entity_id": "other"})
    changed = MappingRecord.model_validate({**record.model_dump(), "relations": (*record.relations, added),
        "confirmation_members": (*record.confirmation_members, "second")})
    request = BatchRequest.create(store.snapshot().root, (changed,), "multi")
    store.prepare(request, request.fingerprint())
    store.publish("multi")
    # When choosing the second relation explicitly instead of a first-character heuristic.
    default = proposal(tree)
    selected = derive(store, default.request.model_copy(update={"selections": (Selection(image_id=record.image_id,
        occurrence_id=record.occurrences[0].occurrence_id, relation_id="second"),)}))
    # Then one declared destination wins only in the physical export; both virtual memberships remain.
    assert len(default.items) == 1
    assert selected.items[0].target == "角色/other"
    assert len(store.snapshot().records[0].relations) == 2
