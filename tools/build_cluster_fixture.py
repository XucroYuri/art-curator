# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Run with the project's installed backend: uv run --no-sync python tools/build_cluster_fixture.py
"""Generate synthetic presentation data using pure G3 outputs; never open a store."""
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from artcurator.album_map_clusters import ClusterSnapshot
from artcurator.album_map_commands import Entity
from artcurator.album_map_discovery import Discovery, DiscoveryInput, VectorMember, preview_pool, recluster
from artcurator.album_map_exchange import Manifest, ManifestMember
from artcurator.album_map_protocol import Artifact, Root, Snapshot
from artcurator.album_map_schema import Decider, MappingRecord, Model, Relation, Subject, summarize
from artcurator.album_map_vectors import Wall, representative_wall
from artcurator.identity_schema import IdentityOptions


class GalleryCluster(Model):
    label: str
    snapshot: ClusterSnapshot
    wall: Wall


class GalleryClusters(Model):
    schema_version: str = "gallery-clusters-v1"
    corpus_fingerprint: str
    parent: Root
    profile: str
    manifest: Manifest
    manifest_digest: str
    clusters: tuple[GalleryCluster, ...]
    subjects: dict[str, Subject]
    entities: tuple[Entity, ...]
    discovery: Discovery
    assets: dict[str, str]


def main() -> None:
    """Bind analytic vectors and existing synthetic artwork to full member identities."""
    directory = Path("tests/fixtures/gallery")
    stamp = datetime(2020, 1, 1, tzinfo=timezone.utc)
    entities = (Entity(entity_id="synthetic-work", entity_type="work", name="同名但不同类型的很长中文作品名称用于检查窄屏完整换行"),
                Entity(entity_id="synthetic-character", entity_type="character", name="同名但不同类型的很长中文作品名称用于检查窄屏完整换行"))
    records = []
    vectors = []
    for index in range(12):
        image = Artifact.capture(f"synthetic-cluster-image-{index}".encode()).digest
        record = MappingRecord.pending(image, "synthetic-cluster-library").model_copy(update={"created_at": stamp, "updated_at": stamp})
        subject_id = f"member-{index:02}"
        subject = Subject(**record.model_dump(exclude={"image_id"}), image_id=image, subject_id=subject_id,
                          crop_id=Artifact.capture(subject_id.encode()).digest, detection_profile="c" * 64)
        if index in {0, 10, 11}:
            entity = entities[0 if index == 0 else 1]
            relation = Relation(**{**subject.model_dump(exclude={"relations"}), "disposition": "assigned",
                "source": "human", "verified": True, "confirmation_members": (image, subject_id),
                "decider": Decider(kind="human", identity="synthetic-curator", version="v1")},
                relation_id=f"accepted-{index}", entity_id=entity.entity_id, entity_type=entity.entity_type, role="depicts")
            subject = subject.model_copy(update={"relations": (relation,), "disposition": "deferred" if index == 0 else "assigned",
                                                 "notes": "等待新参考；保留已接受关系，不是身份拒绝"})
        sibling = Subject(**record.model_dump(exclude={"image_id"}), image_id=image, subject_id=f"sibling-{index}",
                          crop_id=Artifact.capture(f"sibling-{index}".encode()).digest, detection_profile="c" * 64)
        records.append(record.model_copy(update={"subjects": (subject, sibling), "disposition": summarize((subject.disposition, sibling.disposition))}))
        vectors.append(VectorMember(legacy_id=subject_id, image_id=image, subject_id=subject_id,
                                   crop_id=subject.crop_id, profile="c" * 64, vector=(1., 0.) if index < 10 else (0., 1.)))
    root = Root(library_id="synthetic-cluster-library", revision=1, root_digest=Artifact.capture(b"synthetic-root-not-a-live-store").digest)
    before = Snapshot(root=root, records=tuple(records), supports=(), history=())
    manifest = Manifest(members=tuple(ManifestMember.model_validate(v.model_dump(exclude={"vector"})) for v in vectors))
    discovery = recluster(preview_pool(before, DiscoveryInput(profile="c" * 64, options=IdentityOptions(cluster="dbscan"), vectors=tuple(vectors))))
    main_cluster = discovery.clusters[0]
    clusters = (GalleryCluster(label="未知池 / 十张合成图 · 含待查证主体", snapshot=main_cluster.snapshot,
                              wall=representative_wall(Wall(members=tuple(vectors[:10])))),
                GalleryCluster(label="已接受角色 / 与作品类型冲突的对照簇", snapshot=ClusterSnapshot.create(manifest.members[10:]),
                              wall=representative_wall(Wall(members=tuple(vectors[10:])))))
    assets = {v.legacy_id: "data:image/png;base64," + base64.b64encode((directory / f"negotiation-synthetic-{i}.png").read_bytes()).decode()
              for i, v in enumerate(vectors)}
    payload = GalleryClusters(corpus_fingerprint=manifest.fingerprint(), parent=root, profile="c" * 64,
        manifest=manifest, manifest_digest=manifest.fingerprint(), clusters=clusters,
        subjects={s.subject_id: s for r in records for s in r.subjects if s.subject_id.startswith("member-")},
        entities=entities, discovery=discovery, assets=assets)
    (directory / "cluster-payload.json").write_text(json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "cluster-before.json").write_text(before.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
