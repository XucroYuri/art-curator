"""Frozen unresolved-set and multi-cluster/noise adversarial fixtures."""
from pathlib import Path

from artcurator.album_map import AlbumStore
from artcurator.album_map_browser import Entity, confirm_import
from artcurator.album_map_discovery import preview_pool, recluster
from artcurator.album_map_promotion import DiscoveryDecision, stage_discovery
from artcurator.album_map_protocol import BatchRequest
from artcurator.album_map_schema import MappingRecord
from test_album_discovery_lineage import inputs


def test_pool_membership_when_every_disposition_is_present(tmp_path: Path) -> None:
    # Given the eight dispositions, with vectors for every content item.
    states = ("assigned", "hypothesis", "deferred", "unknown-foreign", "original-design", "ordinary", "non-character", "pending")
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        records = tuple(MappingRecord.model_validate({**MappingRecord.pending(f"{i:064x}", "library").model_dump(),
            "disposition": state}) for i, state in enumerate(states))
        request = BatchRequest.create(store.snapshot().root, records, "initial")
        store.prepare(request, request.fingerprint())
        store.publish("initial")
        # When freezing, then the default unresolved set is exact, not nearest-name forcing.
        pool = preview_pool(store.snapshot(), inputs(8))
        assert tuple(v.legacy_id for v in pool.members) == ("legacy-1", "legacy-2", "legacy-3", "legacy-7")
        assert pool.unresolved_without_vectors == ()


def test_selected_promotion_when_other_clusters_noise_and_missing_vectors_exist(tmp_path: Path) -> None:
    # Given two ten-image seeds, one noise image and one image without an embedding.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        request = BatchRequest.create(store.snapshot().root,
            tuple(MappingRecord.pending(f"{i:064x}", "library") for i in range(22)), "initial")
        store.prepare(request, request.fingerprint())
        store.publish("initial")
        source = inputs(22)
        vectors = tuple(v.model_copy(update={"vector": (1., 0.) if i < 10 else
            (0., 1.) if i < 20 else (-1., 0.) if i == 20 else None}) for i, v in enumerate(source.vectors))
        discovery = recluster(preview_pool(store.snapshot(), source.model_copy(update={"vectors": vectors})))
        assert len(discovery.clusters) == 2
        assert "legacy-20" in discovery.noise and f"{21:064x}" in discovery.noise
        decision = DiscoveryDecision(discovery=discovery, actor="human", cluster_id=discovery.clusters[0].cluster_id,
            entity=Entity(entity_id="series", entity_type="original-series", name="Series"))
        staged = stage_discovery(store.snapshot(), decision)
        before = store.snapshot().records
        # When promoting one cluster, then every unrelated unresolved item survives byte-for-byte.
        receipt = confirm_import(store, staged, staged.fingerprint())
        assert receipt.mapping_mutations == 10
        assert store.snapshot().records[10:] == before[10:]
        store.undo(receipt.batch_id)
        assert store.snapshot().records == before


def test_recluster_infers_lineage_when_prior_membership_was_committed(tmp_path: Path) -> None:
    # Given a committed first clustering without any explicit previous proposal supplied next time.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        request = BatchRequest.create(store.snapshot().root,
            tuple(MappingRecord.pending(f"{i:064x}", "library") for i in range(10)), "initial")
        store.prepare(request, request.fingerprint())
        store.publish("initial")
        first = recluster(preview_pool(store.snapshot(), inputs(10)))
        staged = stage_discovery(store.snapshot(), DiscoveryDecision(discovery=first, actor="human"))
        confirm_import(store, staged, staged.fingerprint())
        # When re-clustering again, then committed membership supplies parent lineage automatically.
        second = recluster(preview_pool(store.snapshot(), inputs(10)))
        assert second.clusters[0].parents == (first.clusters[0].cluster_id,)


def test_split_and_merge_lineage_when_visual_threshold_changes(tmp_path: Path) -> None:
    # Given one loose cluster containing two distinct analytic directions.
    from artcurator.identity_schema import IdentityOptions
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        request = BatchRequest.create(store.snapshot().root,
            tuple(MappingRecord.pending(f"{i:064x}", "library") for i in range(20)), "initial")
        store.prepare(request, request.fingerprint())
        store.publish("initial")
        source = inputs(20)
        vectors = tuple(v.model_copy(update={"vector": (1., 0.) if i < 10 else (0., 1.)})
            for i, v in enumerate(source.vectors))
        loose = source.model_copy(update={"vectors": vectors, "options": IdentityOptions(cluster="dbscan", eps=1.1)})
        first = recluster(preview_pool(store.snapshot(), loose))
        tight = loose.model_copy(update={"previous": first, "options": IdentityOptions(cluster="dbscan", eps=.15)})
        # When re-clustering with explicit changed parameters, then split ancestry is exact.
        second = recluster(preview_pool(store.snapshot(), tight))
        assert second.splits == (first.clusters[0].cluster_id,)
        assert len(second.clusters) == 2
