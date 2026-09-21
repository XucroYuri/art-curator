"""Real CLI staging/confirmation/undo narrative, including a refused confirmation."""
import json
import subprocess
import sys
from pathlib import Path

from artcurator.album_map import AlbumStore
from artcurator.album_map_clusters import ClusterSnapshot
from test_album_clusters import envelope, seed


def test_cli_split_when_preview_confirmed_then_undo_and_refuse_bad_token(tmp_path: Path) -> None:
    # Given a real SQLite album and exported synthetic split command.
    path = tmp_path / "album.sqlite"
    with AlbumStore.initialize(path, "library") as store:
        manifest = seed(store)
        parent = ClusterSnapshot.create(tuple(m for m in manifest.members if m.subject_id.endswith("-0")))
        draft = {"action": "split", "cluster_id": "old", "parent_clusters": [parent.model_dump(mode="json")],
            "partitions": [["face-0-0", "face-1-0"]]}
        original = envelope(store, manifest, json.dumps({"clusterDecisions": [draft]}).encode())
        before = store.snapshot().records
    manifest_path, source_path, staged_path = (tmp_path / name for name in ("manifest.json", "draft.json", "staged.json"))
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    source_path.write_text(original.model_dump_json(), encoding="utf-8")
    base = [sys.executable, "-m", "artcurator.cli", "album-map", "--album-db", str(path)]
    staged = subprocess.run([*base, "--album-op", "stage", "--album-file", str(source_path),
        "--album-manifest", str(manifest_path)], capture_output=True, text=True, check=True)
    staged_path.write_text(staged.stdout, encoding="utf-8")
    from artcurator.album_map_browser import StagedImport
    token = StagedImport.model_validate_json(staged.stdout).fingerprint()
    # When executing the exact preview through the CLI.
    committed = subprocess.run([*base, "--album-op", "confirm", "--album-file", str(staged_path),
        "--album-authorize", token], capture_output=True, text=True, check=True)
    # Then one batch changes four images and CLI undo restores them exactly.
    receipt = json.loads(committed.stdout)
    assert receipt["mapping_mutations"] == 4
    undone = subprocess.run([*base, "--album-op", "undo", "--album-batch", receipt["batch_id"]],
        capture_output=True, text=True, check=True)
    assert not json.loads(undone.stdout)["partial_undo"]
    with AlbumStore.open(path) as store:
        assert store.snapshot().records == before


def test_cli_rejects_when_confirmation_token_does_not_match(tmp_path: Path) -> None:
    # Given a syntactically valid staged request, not an authorized one.
    from artcurator.album_map_browser import stage_import
    path = tmp_path / "album.sqlite"
    with AlbumStore.initialize(path, "library") as store:
        manifest = seed(store)
        staged = stage_import(store.snapshot(), envelope(store, manifest,
            b'{"clusterDecisions":[{"action":"name","cluster_id":1,"face_ids":["face-0-0"],"character":"Name"}]}'), manifest)
    staged_path = tmp_path / "staged.json"
    staged_path.write_text(staged.model_dump_json(), encoding="utf-8")
    # When an incorrect token is passed, then no named relation is committed.
    result = subprocess.run([sys.executable, "-m", "artcurator.cli", "album-map", "--album-db", str(path),
        "--album-op", "confirm", "--album-file", str(staged_path), "--album-authorize", "wrong"],
        capture_output=True, text=True, check=False)
    assert result.returncode != 0
    with AlbumStore.open(path) as store:
        assert not store.snapshot().records[0].subjects[0].relations
