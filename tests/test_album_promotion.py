"""Promotion and re-clustering use the exact same prepared/inverse protocol."""
from pathlib import Path

import pytest

from artcurator.album_map import AlbumStore
from artcurator.album_map_browser import Entity, confirm_import
from artcurator.album_map_discovery import preview_pool, recluster
from artcurator.album_map_promotion import DiscoveryDecision, stage_discovery
from artcurator.album_map_protocol import BatchRequest
from artcurator.album_map_schema import MappingError, MappingRecord
from test_album_discovery_lineage import inputs


@pytest.mark.parametrize("promote", [False, True])
def test_discovery_batch_undo_when_membership_or_name_confirmed(tmp_path: Path, promote: bool) -> None:
    # Given a ten-image frozen pool with retained deferred text and dates.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        records = tuple(MappingRecord.pending(f"{i:064x}", "library").model_copy(update={
            "disposition": "deferred", "notes": "retain", "review_after": None}) for i in range(10))
        request = BatchRequest.create(store.snapshot().root, records, "initial")
        store.prepare(request, request.fingerprint())
        store.publish("initial")
        before = store.snapshot().records
        discovery = recluster(preview_pool(store.snapshot(), inputs(10)))
        entity = Entity(entity_id="work", entity_type="work", name="Work") if promote else None
        decision = DiscoveryDecision(discovery=discovery, actor="human", entity=entity,
            cluster_id=discovery.clusters[0].cluster_id if promote else None)
        staged = stage_discovery(store.snapshot(), decision)
        assert store.snapshot().records == before
        # When confirming, then one reversible batch covers membership and optional naming.
        receipt = confirm_import(store, staged, staged.fingerprint())
        assert receipt.mapping_mutations == 10
        assert all(r.notes == "retain" for r in store.snapshot().records)
        assert all(bool(r.relations) == promote for r in store.snapshot().records)
        assert all(r.cluster_membership is not None for r in store.snapshot().records)
        inverse = store.undo(receipt.batch_id)
        assert store.snapshot().records == before
        assert store.undo(receipt.batch_id) == inverse


def test_compatibility_preview_when_profile_requires_reembedding(tmp_path: Path) -> None:
    # Given old saved vectors and a newly requested semantic profile.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        request = BatchRequest.create(store.snapshot().root, (MappingRecord.pending("0" * 64, "library"),), "initial")
        store.prepare(request, request.fingerprint())
        store.publish("initial")
        # When previewing, then cost/missing compatibility is visible and execution is refused.
        pool = preview_pool(store.snapshot(), inputs(1).model_copy(update={"profile": "e" * 64}))
        assert pool.reembedding_required == ("legacy-0",)
        assert pool.pair_comparison_upper_bound == 1
        with pytest.raises(MappingError, match="separate-reembedding-required"):
            recluster(pool)


def test_small_selection_refused_when_promoting_large_seed(tmp_path: Path) -> None:
    # Given a qualified seed but fewer than ten selected distinct images.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        request = BatchRequest.create(store.snapshot().root,
            tuple(MappingRecord.pending(f"{i:064x}", "library") for i in range(10)), "initial")
        store.prepare(request, request.fingerprint())
        store.publish("initial")
        discovery = recluster(preview_pool(store.snapshot(), inputs(10)))
        decision = DiscoveryDecision(discovery=discovery, actor="human", cluster_id=discovery.clusters[0].cluster_id,
            entity=Entity(entity_id="c", entity_type="character", name="Name"), selected_members=("legacy-0",))
        # When promoting, then the small set remains manually nameable but cannot claim seed eligibility.
        with pytest.raises(MappingError, match="below-seed-gate"):
            stage_discovery(store.snapshot(), decision)
