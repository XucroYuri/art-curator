"""Adversarial cluster boundary fixtures; no identity precision claim."""
import json
from pathlib import Path

import pytest

from artcurator.album_map import AlbumStore
from artcurator.album_map_browser import Command, Entity, confirm_import, stage_import
from artcurator.album_map_clusters import ClusterSnapshot
from test_album_clusters import envelope, seed


@pytest.mark.parametrize("resolution", ["reject", "defer"])
def test_merge_preserves_labels_when_names_conflict(tmp_path: Path, resolution: str) -> None:
    # Given different confirmed names on two visual clusters.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        manifest = seed(store)
        commands = tuple(Command(action="confirm_relation", members=(f"face-{i}-0",),
            entity=Entity(entity_id=str(i), entity_type="character", name=str(i))) for i in range(2))
        staged = stage_import(store.snapshot(), envelope(store, manifest, b'{}').model_copy(
            update={"operations": commands}), manifest)
        confirm_import(store, staged, staged.fingerprint())
        before = store.snapshot()
        parents = tuple(ClusterSnapshot.create((manifest.resolve(f"face-{i}-0"),)) for i in range(2))
        draft = {"action": "merge", "cluster_id": 0, "parent_clusters": [p.model_dump(mode="json") for p in parents],
            "conflict_resolution": resolution}
        # When staging a visual merge, then conflicting identity labels are never overwritten.
        staged = stage_import(before, envelope(store, manifest,
            json.dumps({"clusterDecisions": [draft]}).encode()), manifest)
        if resolution == "reject":
            assert staged.request is None and "merge-label-conflict" in staged.conflicts[0]
        else:
            assert staged.cluster_plans[0].label_conflicts == ("character:0", "character:1")
            receipt = confirm_import(store, staged, staged.fingerprint())
            for current, previous in zip(store.snapshot().records[:2], before.records[:2], strict=True):
                assert current.subjects[0].relations == previous.subjects[0].relations
                assert current.subjects[0].disposition == "deferred"
            store.undo(receipt.batch_id)
            assert store.snapshot().records == before.records


def test_mark_refused_when_subject_already_has_opposite_character_mark(tmp_path: Path) -> None:
    # Given explicit baseline then variant commands for the same subject/character.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        manifest = seed(store)
        entity = Entity(entity_id="c", entity_type="character", name="Name")
        commands = tuple(Command(action="confirm_relation", members=("face-0-0",), entity=entity,
            role=role) for role in ("baseline", "variant"))
        # When staging, then the invariant blocks publication, not just a UI checkbox.
        staged = stage_import(store.snapshot(), envelope(store, manifest, b'{}').model_copy(
            update={"operations": commands}), manifest)
        assert staged.request is None
        assert "baseline-variant-exclusive" in staged.conflicts[0]


@pytest.mark.parametrize("kind", ["work", "artist", "original-series", "character", "ordinary-person", "undetermined"])
def test_typed_naming_when_namespace_is_open(tmp_path: Path, kind: str) -> None:
    # Given an explicit typed name outside a model vocabulary.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        manifest = seed(store)
        entity = Entity.model_validate({"entity_id": kind, "entity_type": kind, "name": "same display"})
        command = Command(action="confirm_relation", members=("face-0-0",), entity=entity)
        staged = stage_import(store.snapshot(), envelope(store, manifest, b'{}').model_copy(
            update={"operations": (command,)}), manifest)
        # When confirmed, then the typed identity survives exactly without assigning siblings.
        confirm_import(store, staged, staged.fingerprint())
        record = store.snapshot().records[0]
        assert record.subjects[0].relations[0].entity_type == kind
        assert not record.subjects[1].relations
