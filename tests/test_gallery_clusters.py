"""Offline cluster payload and exported G3 wire regressions; never publish."""
import json
import subprocess
from pathlib import Path

import pytest

from tools import build_gallery
from artcurator.album_map_browser import BrowserEnvelope, stage_import
from artcurator.album_map_exchange import Manifest
from artcurator.album_map_promotion import DiscoveryDecision, stage_discovery
from artcurator.album_map_protocol import Snapshot

FIXTURE = Path(__file__).parent / "fixtures/gallery/cluster-payload.json"


def test_clusters_when_absent_remain_unavailable(tmp_path: Path) -> None:
    # Given an image-only directory; when encoded; then no cluster is invented.
    payload = build_gallery.build_payload(tmp_path, (), ())
    assert build_gallery.compact_payload(payload)["cl"] is None


def test_clusters_when_embedded_preserve_backend_outputs() -> None:
    # Given backend-generated frozen wall/discovery outputs.
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # When encoded by the existing gallery builder.
    payload = build_gallery.build_payload(FIXTURE.parent, (), ())
    # Then no member, wall order, digest or missing evidence is reconstructed.
    assert build_gallery.compact_payload(payload)["cl"] == expected


@pytest.mark.parametrize("text", ["{", "[]", '{"schema_version":"future"}'])
def test_clusters_when_invalid_fail_closed(tmp_path: Path, text: str) -> None:
    # Given invalid optional data; when loaded; then it cannot silently disappear.
    (tmp_path / "cluster-payload.json").write_text(text, encoding="utf-8")
    with pytest.raises(build_gallery.GalleryInputError):
        build_gallery.build_payload(tmp_path, (), ())


def wire_result(action: str, count: int = 1, namespace: str = "work") -> str:
    """Run the actual browser wire functions in Node, not a Python reimplementation."""
    script = r"""
const fs = require('node:fs'), vm = require('node:vm');
const data = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const action = process.argv[2], count = Number(process.argv[3]), namespace = process.argv[4];
vm.runInThisContext(fs.readFileSync('tools/gallery_clusters_wire.js', 'utf8'));
parseClusterPayload(data);
const members = data.clusters[0].snapshot.members.map(m => m.legacy_id);
const choice = {cluster: data.clusters[0].snapshot.snapshot_id,
  action: action === 'merge-blocked' ? 'merge' : action, actor:'qa-human',
  selected: members.slice(0,count), partitions:[members.slice(0,1), members.slice(1,2)],
  merge:[data.clusters[1].snapshot.snapshot_id], defer: action !== 'merge-blocked',
  entity:{entity_id:'qa-entity', entity_type:namespace, name:'中文测试名称'}};
clusterEnvelope(data, choice).then(v => console.log(JSON.stringify(v)))
  .catch(e => { console.error(e.message); process.exitCode = 2; });
"""
    result = subprocess.run(["node", "-e", script, str(FIXTURE), action, str(count), namespace],
                            capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode:
        return result.stderr.strip()
    return result.stdout


@pytest.mark.parametrize("namespace", ["work", "artist", "original-series", "character", "ordinary-person", "undetermined"])
def test_typed_name_when_exported_stages_exact_selected_subject(namespace: str) -> None:
    # Given a frozen synthetic snapshot and the actual JS-produced envelope.
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    before = Snapshot.model_validate_json((FIXTURE.parent / "cluster-before.json").read_bytes())
    raw = json.loads(wire_result("name", namespace=namespace))
    envelope = BrowserEnvelope.model_validate(raw["wire"])
    # When staging without any store publication.
    staged = stage_import(before, envelope, Manifest.model_validate(data["manifest"]))
    # Then exactly one chosen subject gains the typed relation in the preview, never its sibling.
    assert staged.conflicts == () and staged.request is not None
    assert len(staged.request.changes) == 1
    after = staged.request.changes[0].after
    original = next(r for r in before.records if r.image_id == after.image_id)
    assert after.subjects[1] == original.subjects[1]
    relation = after.subjects[0].relations[-1]
    assert (relation.entity_type, relation.source, relation.verified) == (namespace, "human", True)
    assert bytes.fromhex(envelope.original_journal.payload_hex) == raw["journal"].encode()
    assert set(raw["wire"]) == set(BrowserEnvelope.model_fields)


@pytest.mark.parametrize("action", ["split", "merge", "outlier", "exclusion"])
def test_structural_export_when_staged_preserves_all_accepted_relations(action: str) -> None:
    # Given a real JS-produced structural draft with frozen parents.
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    before = Snapshot.model_validate_json((FIXTURE.parent / "cluster-before.json").read_bytes())
    raw = json.loads(wire_result(action))
    # When staging; then relation sets and siblings are unchanged, including conflicting entities.
    staged = stage_import(before, BrowserEnvelope.model_validate(raw["wire"]), Manifest.model_validate(data["manifest"]))
    assert staged.request is not None and not staged.conflicts
    for change in staged.request.changes:
        original = next(r for r in before.records if r.image_id == change.key)
        assert change.after.subjects[0].relations == original.subjects[0].relations
        assert change.after.subjects[1] == original.subjects[1]
        if action == "merge":
            assert change.after.subjects[0].disposition == "deferred"
    assert len(staged.cluster_plans[0].snapshots) == (1 if action == "merge" else 3 if action == "split" else 2)


def test_merge_when_conflicts_unacknowledged_cannot_export() -> None:
    # Given conflicting accepted entities; when defer is absent; then no envelope is generated.
    assert not wire_result("merge-blocked").startswith("{")


@pytest.mark.parametrize("count", [9, 10])
def test_promotion_when_selected_count_crosses_gate(count: int) -> None:
    # Given a qualified backend proposal and an exact selected subset.
    result = wire_result("promote", count)
    # When exporting and staging; then nine refuses and ten stages without publication.
    if count == 9:
        assert not result.startswith("{")
        return
    before = Snapshot.model_validate_json((FIXTURE.parent / "cluster-before.json").read_bytes())
    raw = json.loads(result)["wire"]
    staged = stage_discovery(before, DiscoveryDecision.model_validate(raw))
    assert staged.request is not None and len(staged.request.changes) == 10
    assert set(raw) == set(DiscoveryDecision.model_fields)


@pytest.mark.parametrize("filename", ["keyboard-envelope.json", "merge-envelope.json", "split-envelope.json", "outlier-envelope.json", "exclusion-envelope.json"])
def test_real_browser_download_when_staged_matches_wire(filename: str) -> None:
    # Given actual browser downloads, not a reconstructed JSON fixture.
    evidence = Path(__file__).parents[1] / "docs/assets/clusters"
    before = Snapshot.model_validate_json((FIXTURE.parent / "cluster-before.json").read_bytes())
    raw = json.loads((evidence / filename).read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json((evidence / "manifest.json").read_bytes())
    # When consumed by the real staging boundary without any AlbumStore.
    staged = stage_import(before, BrowserEnvelope.model_validate(raw), manifest)
    # Then the exact exported envelope stages and remains zero-source-move.
    assert staged.request is not None and not staged.conflicts
    assert staged.source_moves == 0
    assert set(raw) == set(BrowserEnvelope.model_fields)


def test_real_browser_promotion_when_staged_keeps_exact_selected_count() -> None:
    # Given a browser-exported ten-member promotion.
    evidence = Path(__file__).parents[1] / "docs/assets/clusters/promotion.json"
    before = Snapshot.model_validate_json((FIXTURE.parent / "cluster-before.json").read_bytes())
    decision = DiscoveryDecision.model_validate_json(evidence.read_bytes())
    # When staged without a store; then the selected set, not siblings, is proposed.
    staged = stage_discovery(before, decision)
    assert len(decision.selected_members) == 10
    assert staged.request is not None and len(staged.request.changes) == 10
