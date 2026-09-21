import importlib.util
from pathlib import Path

from artcurator.album_map import AlbumStore
from artcurator.album_map_protocol import Artifact, BatchRequest
from artcurator.album_map_schema import MappingRecord


def test_browser_draft_stages_then_commits_when_confirmed(tmp_path: Path) -> None:
    # Given a content-bound pending record and an explicit disposition draft.
    assert importlib.util.find_spec("artcurator.album_map_browser"), "browser import missing"
    from artcurator.album_map_browser import BrowserEnvelope, Command, stage_import, confirm_import
    from artcurator.album_map_exchange import Manifest, ManifestMember
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        initial = BatchRequest.create(store.snapshot().root, (MappingRecord.pending("a" * 64, "library"),), "initial")
        store.prepare(initial, initial.fingerprint())
        store.publish("initial")
        manifest = Manifest(members=(ManifestMember(legacy_id="face", image_id="a" * 64,
            subject_id="face", crop_id="b" * 64, profile="c" * 64),))
        envelope = BrowserEnvelope(source="review-studio", corpus_fingerprint="d" * 64,
            parent=store.snapshot().root, export_id="draft", actor="human", manifest_digest=manifest.fingerprint(),
            profile="c" * 64, original_journal=Artifact.capture(b'{"clusterDecisions":[],"faceLabels":{}}'),
            operations=(Command(action="set_disposition", members=("face",), disposition="deferred", scope="image"),))
        # When staging, then there is still no mapping mutation.
        staged = stage_import(store.snapshot(), envelope, manifest)
        assert store.snapshot().records[0].disposition == "pending"
        assert staged.conflicts == ()
        # When confirming the exact preview, then one durable batch/replay receipt is returned.
        receipt = confirm_import(store, staged, staged.fingerprint())
        assert store.snapshot().records[0].disposition == "deferred"
        assert confirm_import(store, staged, staged.fingerprint()) == receipt
        assert store.undo(receipt.batch_id).mapping_mutations == 1
