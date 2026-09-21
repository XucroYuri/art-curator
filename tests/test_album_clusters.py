"""ALBUM-MAP-v1 cluster walkthrough: analytic content, never corpus locators."""
import json
from pathlib import Path

import pytest

from artcurator.album_map import AlbumStore
from artcurator.album_map_browser import BrowserEnvelope, Command, Entity, confirm_import, stage_import
from artcurator.album_map_exchange import Manifest, ManifestMember
from artcurator.album_map_protocol import Artifact, BatchRequest
from artcurator.album_map_schema import MappingRecord, Subject


def seed(store: AlbumStore) -> Manifest:
    records = []
    members = []
    for index in range(4):
        image = f"{index:064x}"
        record = MappingRecord.pending(image, "library")
        subjects = tuple(Subject(**record.model_dump(exclude={"image_id"}), image_id=image,
            subject_id=f"face-{index}-{face}", crop_id=f"{index * 2 + face:064x}",
            detection_profile="c" * 64) for face in range(2))
        records.append(record.model_copy(update={"subjects": subjects}))
        members.extend(ManifestMember(legacy_id=s.subject_id, image_id=image,
            subject_id=s.subject_id, crop_id=s.crop_id, profile=s.detection_profile) for s in subjects)
    request = BatchRequest.create(store.snapshot().root, tuple(records), "initial")
    store.prepare(request, request.fingerprint())
    store.publish(request.batch_id)
    return Manifest(members=tuple(members))


def envelope(store: AlbumStore, manifest: Manifest, journal: bytes) -> BrowserEnvelope:
    return BrowserEnvelope(source="review-studio", corpus_fingerprint="d" * 64,
        parent=store.snapshot().root, export_id="draft", actor="reviewer", profile="c" * 64,
        manifest_digest=manifest.fingerprint(), original_journal=Artifact.capture(journal),
        entities=(Entity(entity_id="entity", entity_type="character", name="Name"),))


@pytest.mark.parametrize("action", ["name", "split", "merge", "outlier", "exclusion"])
def test_cluster_operation_replays_and_undoes_when_confirmed(tmp_path: Path, action: str) -> None:
    # Given frozen selected faces plus untouched sibling faces.
    from artcurator import album_map_clusters as clusters
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        manifest = seed(store)
        selected = tuple(m for m in manifest.members if m.subject_id.endswith("-0"))
        parents = (clusters.ClusterSnapshot.create(selected[:2]), clusters.ClusterSnapshot.create(selected[2:]))
        if action != "merge":
            parents = (clusters.ClusterSnapshot.create(selected),)
        draft = {"action": action, "cluster_id": "legacy", "face_ids": [m.legacy_id for m in selected[:1]],
            "character": "Name", "parent_clusters": [p.model_dump(mode="json") for p in parents],
            "partitions": [[selected[0].legacy_id]] if action == "split" else []}
        before = store.snapshot().records
        staged = stage_import(store.snapshot(), envelope(store, manifest,
            json.dumps({"clusterDecisions": [draft]}).encode()), manifest)
        assert staged.conflicts == ()
        assert store.snapshot().records == before
        # When confirming and replaying the exact staged operation.
        receipt = confirm_import(store, staged, staged.fingerprint())
        assert confirm_import(store, staged, staged.fingerprint()) == receipt
        # Then only selected targets change; old state has one exact, repeatable inverse.
        after = store.snapshot().records
        assert all(r.subjects[1] == old.subjects[1] for r, old in zip(after, before, strict=True))
        if action == "name":
            relation = after[0].subjects[0].relations[0]
            assert relation.verified and relation.source == "human"
            assert relation.decider.identity == "reviewer"
            assert relation.batch_id == receipt.batch_id == relation.operation_id
            assert all(not r.subjects[0].relations for r in after[1:])
        else:
            memberships = tuple(r.subjects[0].cluster_membership for r in after)
            assert all(m is not None and m.parents for m in memberships)
            assert all(m.snapshot_id not in {p.snapshot_id for p in parents} for m in memberships if m)
            assert len({m.snapshot_id for m in memberships if m}) == (1 if action == "merge" else 2)
        inverse = store.undo(receipt.batch_id)
        assert not inverse.partial_undo
        assert store.snapshot().records == before
        assert store.undo(receipt.batch_id) == inverse


def test_split_refuses_overlap_when_partitions_are_not_disjoint(tmp_path: Path) -> None:
    # Given a frozen parent and overlapping subsets.
    from artcurator.album_map_clusters import ClusterSnapshot
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        manifest = seed(store)
        parent = ClusterSnapshot.create(manifest.members)
        draft = {"action": "split", "cluster_id": 1, "parent_clusters": [parent.model_dump(mode="json")],
            "partitions": [["face-0-0"], ["face-0-0"]]}
        # When staging, then the whole batch remains pending.
        staged = stage_import(store.snapshot(), envelope(store, manifest,
            json.dumps({"clusterDecisions": [draft]}).encode()), manifest)
        assert staged.request is None
        assert "split-partition" in staged.conflicts[0]


def test_partial_undo_preserves_sibling_edit_when_same_image_row_changes(tmp_path: Path) -> None:
    # Given a two-image cluster naming and a later edit of an independent sibling.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        manifest = seed(store)
        original = envelope(store, manifest, b'{"clusterDecisions":[{"action":"name","cluster_id":1,"face_ids":["face-0-0","face-1-0"],"character":"Name"}]}')
        staged = stage_import(store.snapshot(), original, manifest)
        receipt = confirm_import(store, staged, staged.fingerprint())
        later = envelope(store, manifest, b'{}').model_copy(update={"operations": (
            Command(action="set_disposition", members=("face-0-1",), disposition="deferred", notes="later"),)})
        edit = stage_import(store.snapshot(), later, manifest)
        confirm_import(store, edit, edit.fingerprint())
        # When undoing, then the image-row limitation is conservative and reported exactly.
        inverse = store.undo(receipt.batch_id)
        assert inverse.partial_undo and inverse.conflicts == ("0" * 64,)
        assert inverse.mapping_mutations == 1
        assert store.snapshot().records[0].subjects[1].notes == "later"
        assert store.undo(receipt.batch_id) == inverse
