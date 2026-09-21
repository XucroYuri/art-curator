"""Backend-only G5 scenarios, no real library or browser assets."""
import importlib.util
from pathlib import Path

import pytest

from artcurator.album_map import AlbumStore
from artcurator.album_map_protocol import BatchRequest
from artcurator.album_map_schema import MappingRecord


def test_exchange_preserves_history_when_restored(tmp_path: Path) -> None:
    # Given committed history with an opaque optional extension.
    assert importlib.util.find_spec("artcurator.album_map_exchange"), "exchange adapter missing"
    from artcurator.album_map_exchange import export_bundle, restore_bundle
    with AlbumStore.initialize(tmp_path / "original.sqlite", "library") as store:
        record = MappingRecord.pending("a" * 64, "library").model_copy(update={"extension": {"future": 7}})
        request = BatchRequest.create(store.snapshot().root, (record,), "first")
        store.prepare(request, request.fingerprint())
        original_receipt = store.publish("first")
        bundle = export_bundle(store)
        original = store.snapshot()
    # When explicitly restoring logical history into a new destination.
    with AlbumStore.initialize(tmp_path / "restore.sqlite", "library") as restored:
        restore_bundle(restored, bundle)
        # Then logical identity, extensions and operation replay survive.
        assert restored.snapshot() == original
        assert restored.prepare(request, request.fingerprint()) == original_receipt
        assert restored.undo("first").mapping_mutations == 1


def test_deferred_trigger_once_when_revision_repeated(tmp_path: Path) -> None:
    # Given a deferred record containing human notes.
    assert importlib.util.find_spec("artcurator.album_map_tray"), "tray adapter missing"
    from artcurator.album_map_tray import TrayAction, tray_request, deferred
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        record = MappingRecord.pending("a" * 64, "library").model_copy(update={
            "disposition": "deferred", "notes": "retain alternatives"})
        initial = BatchRequest.create(store.snapshot().root, (record,), "first")
        store.prepare(initial, initial.fingerprint())
        store.publish("first")
        # When archive and duplicate trigger revisions are proposed and applied.
        for op, action in (("archive", "archive"), ("notify", "notify"), ("repeat", "notify")):
            request = tray_request(store.snapshot(), TrayAction(image_id=record.image_id,
                action=action, operation_id=op, trigger_revision="c" * 64))
            store.prepare(request, request.fingerprint())
            store.publish(op)
        # Then archive preserves the tray and exactly one trigger marker remains.
        saved = deferred(store.snapshot())[0]
        assert saved.archived and saved.notes == "retain alternatives"
        assert saved.trigger_revisions == ("c" * 64,)
        assert not saved.verified


def test_full_hash_resolution_refuses_ambiguous_short_id() -> None:
    # Given two full hashes sharing a legacy prefix.
    assert importlib.util.find_spec("artcurator.album_map_exchange"), "manifest resolver missing"
    from artcurator.album_map_exchange import Manifest, ManifestMember
    manifest = Manifest(members=tuple(ManifestMember(legacy_id="same", image_id="a" * 16 + c * 48,
        subject_id=c, crop_id=c * 64, profile="d" * 64) for c in "bc"))
    # When resolving the short ID, then ambiguity refuses the entire operation.
    with pytest.raises(ValueError, match="ambiguous"):
        manifest.resolve("same")
