import importlib.util
from pathlib import Path

from artcurator.album_map import AlbumStore
from artcurator.album_map_protocol import BatchRequest
from artcurator.album_map_schema import MappingRecord


def test_unknown_pool_freezes_and_promotes_when_seed_has_ten_images(tmp_path: Path) -> None:
    # Given ten unresolved images with compatible analytic vectors and one resolved image.
    assert importlib.util.find_spec("artcurator.album_map_discovery"), "unknown pool missing"
    from artcurator.album_map_discovery import DiscoveryInput, VectorMember, preview_pool, recluster, promotion
    from artcurator.album_map_browser import Entity, confirm_import
    from artcurator.identity_schema import IdentityOptions
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        ids = tuple(f"{i:064x}" for i in range(11))
        records = tuple(MappingRecord.pending(key, "library").model_copy(update={
            "disposition": "ordinary" if index == 10 else "pending"}) for index, key in enumerate(ids))
        initial = BatchRequest.create(store.snapshot().root, records, "initial")
        store.prepare(initial, initial.fingerprint())
        store.publish("initial")
        inputs = DiscoveryInput(profile="c" * 64, options=IdentityOptions(cluster="dbscan"),
            vectors=tuple(VectorMember(legacy_id=key, image_id=key, subject_id=key,
                crop_id=key, profile="c" * 64, vector=(1., 0.)) for key in ids))
        # When freezing/reclustering and explicitly confirming one promotion.
        pool = preview_pool(store.snapshot(), inputs)
        result = recluster(pool)
        assert len(pool.members) == 10
        assert len(result.clusters) == 1 and result.clusters[0].seed_eligible
        staged = promotion(store.snapshot(), result, Entity(entity_id="entity", entity_type="character", name="name"))
        receipt = confirm_import(store, staged, staged.fingerprint())
        # Then one batch changes exactly the selected unresolved content and can be undone.
        assert receipt.mapping_mutations == 10
        assert store.snapshot().records[-1].disposition == "ordinary"
        assert store.undo(receipt.batch_id).mapping_mutations == 10


def test_pool_digest_changes_when_unresolved_without_vector_added(tmp_path: Path) -> None:
    # Given the same saved vectors and two different unresolved snapshots.
    from artcurator.album_map_discovery import DiscoveryInput, preview_pool
    from artcurator.identity_schema import IdentityOptions
    with AlbumStore.initialize(tmp_path / "album.sqlite", "library") as store:
        inputs = DiscoveryInput(profile="c" * 64, options=IdentityOptions(), vectors=())
        before = preview_pool(store.snapshot(), inputs)
        initial = BatchRequest.create(store.snapshot().root, (MappingRecord.pending("a" * 64, "library"),), "initial")
        store.prepare(initial, initial.fingerprint())
        store.publish("initial")
        # When freezing the pool again, then missing vectors do not erase membership identity.
        after = preview_pool(store.snapshot(), inputs)
        assert after.member_digest != before.member_digest
        assert after.unresolved_without_vectors == ("a" * 64,)
