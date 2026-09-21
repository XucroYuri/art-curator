"""Transactional G5 regression scenarios using only synthetic content."""
from pathlib import Path

import pytest


def test_prepared_mapping_is_hidden_when_reopened(tmp_path: Path) -> None:
    # Given an explicitly initialized empty library.
    from artcurator.album_map import AlbumStore
    from artcurator.album_map_schema import MappingRecord
    from artcurator.album_map_protocol import BatchRequest

    path = tmp_path / "album.sqlite"
    record = MappingRecord.pending("a" * 64, "library")
    with AlbumStore.initialize(path, "library") as store:
        request = BatchRequest.create(store.snapshot().root, (record,), "first")
        store.prepare(request, request.fingerprint())
    # When recovery opens a durable prepared-only batch.
    with AlbumStore.open(path) as store:
        snapshot = store.snapshot()
        # Then no prepared materialization is visible and explicit resume publishes it.
        assert snapshot.records == ()
        assert store.recovery.prepared == ("first",)
        receipt = store.publish("first")
        assert receipt.revision == 1
        assert len(store.snapshot().records) == 1
        assert store.prepare(request, request.fingerprint()) == receipt


def test_undo_preserves_aba_when_later_edit_returns_to_same_value(tmp_path: Path) -> None:
    # Given a committed mapping followed by edit-away-and-back.
    from artcurator.album_map import AlbumStore
    from artcurator.album_map_schema import MappingRecord
    from artcurator.album_map_protocol import BatchRequest, Mutation, image_digest

    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        original = MappingRecord.pending("a" * 64, "library")
        after_digest = ""
        for operation, record in (("a", original), ("b", original.model_copy(update={"notes": "later"})),
                                  ("c", original)):
            request = BatchRequest.create(store.snapshot().root, (record,), operation)
            # Freeze identical full after-images including metadata: only event tokens distinguish ABA.
            request = request.model_copy(update={"changes": (Mutation(key=record.image_id, after=record),)})
            if operation == "a":
                after_digest = image_digest(request.changes[0].after)
            if operation == "c":
                assert image_digest(request.changes[0].after) == after_digest
            store.prepare(request, request.fingerprint())
            store.publish(operation)
        # When the original batch is undone twice.
        first = store.undo("a")
        second = store.undo("a")
        # Then one persistent partial inverse preserves the later event.
        assert first == second
        assert first.partial_undo
        assert first.conflicts == (original.image_id,)
        assert len(store.snapshot().records) == 1


def test_reconcile_refuses_tampered_unchanged_row(tmp_path: Path) -> None:
    # Given a committed row corrupted outside the coordinator.
    import sqlite3
    from artcurator.album_map import AlbumStore
    from artcurator.album_map_schema import MappingRecord, MappingError
    from artcurator.album_map_protocol import BatchRequest

    path = tmp_path / "album.sqlite"
    with AlbumStore.initialize(path, "library") as store:
        request = BatchRequest.create(store.snapshot().root,
                                      (MappingRecord.pending("a" * 64, "library"),), "a")
        store.prepare(request, request.fingerprint())
        store.publish("a")
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE materialized SET token='tampered'")
    # When restarting, then mutation admission fails without repairing evidence.
    with pytest.raises(MappingError, match="materialized"):
        with AlbumStore.open(path):
            pytest.fail("corrupt store admitted")
