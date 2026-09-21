"""Synthetic injected exceptions are not power-loss certification."""
from pathlib import Path

import pytest

from artcurator.album_map import AlbumStore
from artcurator.album_map_protocol import BatchRequest
from artcurator.album_map_schema import MappingError, MappingRecord, Relation, Subject


@pytest.mark.parametrize("phase", ["before-P", "P-artifact", "P-manifest", "after-P",
    "before-C", "C-marker", "C-event", "C-row", "C-root", "after-C", "acknowledgement"])
def test_old_or_complete_revision_when_cutpoint_raises(tmp_path: Path, phase: str) -> None:
    # Given a real SQLite database and a two-row atomic request.
    path = tmp_path / "album.sqlite"
    def interrupt(current: str) -> None:
        if current == phase:
            raise InterruptedError(phase)
    with AlbumStore.initialize(path, "library") as store:
        request = BatchRequest.create(store.snapshot().root, tuple(
            MappingRecord.pending(c * 64, "library") for c in "ab"), "batch")
        store.cutpoint = interrupt
        # When an exception cuts P, C, or acknowledgement.
        with pytest.raises(InterruptedError):
            store.prepare(request, request.fingerprint())
            store.publish("batch")
    # Then restart exposes no mixed revision and exact replay after C.
    with AlbumStore.open(path) as store:
        committed = phase in {"after-C", "acknowledgement"}
        assert len(store.snapshot().records) == (2 if committed else 0)
        if committed:
            assert store.prepare(request, request.fingerprint()) == store.receipt("batch")


def test_request_stamps_lineage_when_created(tmp_path: Path) -> None:
    # Given a pending initial record.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        record = MappingRecord.pending("a" * 64, "library")
        # When constructing the exact request to preview.
        request = BatchRequest.create(store.snapshot().root, (record,), "op")
        # Then persisted metadata describes the proposed publication, not initialization.
        after = request.changes[0].after
        assert isinstance(after, MappingRecord)
        assert (after.revision, after.parent_revision, after.batch_id, after.operation_id) == (1, 0, "op", "op")


def test_nested_relation_refused_when_bound_to_sibling() -> None:
    # Given two subjects and a relation attached to the wrong subject container.
    record = MappingRecord.pending("a" * 64, "library")
    fields = record.model_dump(exclude={"schema_version", "library_id", "revision", "parent_revision",
        "image_id", "occurrences", "subjects", "relations", "archived"})
    relation = Relation(**fields, relation_id="r", entity_id="e", entity_type="character",
                        role="depicts", subject_id="two")
    subjects = tuple(Subject(**fields, subject_id=name, image_id=record.image_id,
        crop_id="b" * 64, detection_profile="c" * 64,
        relations=(relation,) if name == "one" else ()) for name in ("one", "two"))
    # When parsing the mapping, then sibling attribution is rejected.
    with pytest.raises(ValueError, match="relation-owner"):
        MappingRecord.model_validate({**record.model_dump(), "subjects": subjects})


def test_partial_undo_restores_eligible_rows_when_other_row_edited(tmp_path: Path) -> None:
    # Given a two-row batch and a later independent edit to only one image.
    path = tmp_path / "album.sqlite"
    with AlbumStore.initialize(path, "library") as store:
        records = tuple(MappingRecord.pending(c * 64, "library") for c in "ab")
        first = BatchRequest.create(store.snapshot().root, records, "first")
        store.prepare(first, first.fingerprint())
        store.publish("first")
        later = BatchRequest.create(store.snapshot().root, (records[0].model_copy(update={"notes": "human"}),), "later")
        store.prepare(later, later.fingerprint())
        store.publish("later")
        # When undoing the batch.
        receipt = store.undo("first")
        # Then eligible insertion is removed, later edit survives and result is persistent.
        assert receipt.partial_undo and receipt.mapping_mutations == 1
        assert receipt.conflicts == ("a" * 64,)
        assert tuple(r.notes for r in store.snapshot().records) == ("human",)
    with AlbumStore.open(path) as store:
        assert store.undo("first") == receipt


def test_second_coordinator_refused_when_lock_held(tmp_path: Path) -> None:
    # Given one admitted coordinator.
    path = tmp_path / "album.sqlite"
    with AlbumStore.initialize(path, "library"):
        # When a second coordinator opens it, then admission fails busy.
        with pytest.raises(MappingError, match="library-busy"):
            with AlbumStore.open(path):
                pytest.fail("second writer admitted")


def test_prepared_before_token_refused_when_manifest_rehashed(tmp_path: Path) -> None:
    # Given a prepared-only batch whose before-token no longer names the parent state.
    import sqlite3
    from artcurator.album_map_protocol import Prepared
    path = tmp_path / "album.sqlite"
    with AlbumStore.initialize(path, "library") as store:
        request = BatchRequest.create(store.snapshot().root, (MappingRecord.pending("a" * 64, "library"),), "op")
        prepared = store.prepare(request, request.fingerprint())
        assert isinstance(prepared, Prepared)
    corrupted = prepared.model_copy(update={"changes": (prepared.changes[0].model_copy(
        update={"before_token": "wrong-parent-token"}),)})
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE batches SET manifest=?,manifest_digest=?",
            (corrupted.model_dump_json(), corrupted.fingerprint()))
    # When reopening, then no explicit resume can publish the divergent before-image.
    with pytest.raises(MappingError, match="prepared-before-state"):
        with AlbumStore.open(path):
            pytest.fail("divergent prepared parent admitted")
