"""Analytic pool growth, lineage, compatibility and seed boundary evidence."""
from pathlib import Path

import pytest

from artcurator.album_map import AlbumStore
from artcurator.album_map_discovery import DiscoveryInput, VectorMember, preview_pool, recluster
from artcurator.album_map_protocol import BatchRequest
from artcurator.album_map_schema import MappingError, MappingRecord
from artcurator.identity_schema import IdentityOptions


def inputs(count: int) -> DiscoveryInput:
    return DiscoveryInput(profile="c" * 64, options=IdentityOptions(cluster="dbscan"), vectors=tuple(
        VectorMember(legacy_id=f"legacy-{i}", image_id=f"{i:064x}", subject_id=f"{i:064x}",
            crop_id=f"{i:064x}", profile="c" * 64, vector=(1., 0.)) for i in range(count)))


@pytest.mark.parametrize("count", [9, 10, 11])
def test_seed_gate_when_distinct_image_count_crosses_ten(tmp_path: Path, count: int) -> None:
    # Given a frozen analytic pool at the exact seed boundary.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        request = BatchRequest.create(store.snapshot().root,
            tuple(MappingRecord.pending(f"{i:064x}", "library") for i in range(count)), "initial")
        store.prepare(request, request.fingerprint())
        store.publish("initial")
        # When clustering, then eligibility follows distinct images, not face count.
        result = recluster(preview_pool(store.snapshot(), inputs(count)))
        assert result.clusters[0].seed_eligible == (count >= 10)
        assert len(result.clusters[0].representatives) <= 12


def test_lineage_when_pool_grows_and_parameters_change(tmp_path: Path) -> None:
    # Given an earlier frozen cluster and an added unresolved image.
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        request = BatchRequest.create(store.snapshot().root,
            tuple(MappingRecord.pending(f"{i:064x}", "library") for i in range(10)), "initial")
        store.prepare(request, request.fingerprint())
        store.publish("initial")
        first = recluster(preview_pool(store.snapshot(), inputs(10)))
        addition = BatchRequest.create(store.snapshot().root, (MappingRecord.pending(f"{10:064x}", "library"),), "growth")
        store.prepare(addition, addition.fingerprint())
        store.publish("growth")
        later = inputs(11).model_copy(update={"previous": first,
            "options": IdentityOptions(cluster="dbscan", eps=.16)})
        # When re-clustering, then overlap derives lineage and exact additions, not supplied guesses.
        second = recluster(preview_pool(store.snapshot(), later))
        assert second.clusters[0].parents == (first.clusters[0].cluster_id,)
        assert second.clusters[0].cluster_id != first.clusters[0].cluster_id
        assert second.additions == ("legacy-10",)
        assert second.pool.parameters_changed
        assert second.pool.pair_comparison_upper_bound == 121


def test_pool_refuses_wrong_crop_binding_when_vector_profile_matches(tmp_path: Path) -> None:
    # Given a saved vector claiming the right subject/profile but wrong crop.
    from test_album_clusters import seed
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        manifest = seed(store)
        member = manifest.members[0]
        vector = VectorMember(**member.model_dump(exclude={"crop_id"}), crop_id="f" * 64, vector=(1., 0.))
        # When freezing, then stale crop evidence cannot enter discovery.
        with pytest.raises(MappingError, match="vector-content-binding"):
            preview_pool(store.snapshot(), DiscoveryInput(profile="c" * 64, options=IdentityOptions(), vectors=(vector,)))
