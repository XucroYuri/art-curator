# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pydantic>=2", "PyYAML", "torch", "Pillow", "psutil", "scikit-learn", "onnxruntime", "transformers"]
# ///
# How to run: uv run --no-project --python .venv-identity/Scripts/python.exe python tools/check_identity_labels.py
"""Actual CLI naming/reclustering roundtrip using only synthetic identity evidence."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from artcurator import db
from artcurator.config import ROOT, Settings
from artcurator.identity_cluster import cluster
from artcurator.identity_schema import (
    ClusteringInfo, DetectorInfo, Face, IdentityDocument, IdentityOptions, ImageFaces, ModelInfo, Provenance,
)
from artcurator.identity_store import atomic_bytes, file_digest, load_document, save_array, save_model


def main() -> None:
    out = ROOT / "out/identity-labels-e2e"
    out.mkdir(exist_ok=True)
    if (out / "characters.json").exists():
        raise ValueError("synthetic naming fixture already used; retain its evidence and choose a new fixture output")
    faces = [Face(face_id=f"f_{index:08x}", image_sha16=f"{index:016x}", bbox=(0, 0, 32, 32),
                  det_score=.9, crop_rel=f"faces/f_{index:08x}.jpg") for index in range(1, 13)]
    document = IdentityDocument(detector=DetectorInfo(name="synthetic", model="fixture", revision="v1"),
        embedder=ModelInfo(name="synthetic", model="fixture", revision="v1"), clustering=ClusteringInfo(),
        image_count=12, face_count=12, cluster_count=0, clusters=[], faces=faces,
        images=[ImageFaces(sha16=f.image_sha16, path_rel=f"synthetic/{i}.png", faces=[f.face_id])
                for i, f in enumerate(faces)])
    save_model(out / "identities.json", document)
    contents = {face.image_sha16: f"{index:064x}" for index, face in enumerate(faces, 1)}
    save_model(out / "identity-provenance.json", Provenance(corpus_fingerprint="c" * 64,
        semantic_profile="d" * 64, contents=contents, crops={f.face_id: "e" * 64 for f in faces}))
    db.save_rows(out, [db.Row(sha16=f.image_sha16, sha256=contents[f.image_sha16],
        abs_path="synthetic.png", path_rel=f"synthetic/{index}.png", filename=f"{index}.png",
        width=32, height=32, filesize=1, phash="0", mode="RGB", identity_sim=.5)
        for index, f in enumerate(faces)])
    values = np.array([[1., index * .005, 0.] for index in range(6)] +
                      [[index * .005, 1., 0.] for index in range(6)], dtype=np.float16)
    save_array(out / "identities.npy", values)
    atomic_bytes(out / "identity-embedding.json", json.dumps({"faces": [f.face_id for f in faces],
        "sha256": file_digest(out / "identities.npy"), "semantic_profile": "d" * 64}).encode())
    cluster(out, IdentityOptions())
    settings = Settings(input=out, references=out, posted=out, characters_root=out, out=out)
    config = out / "config.json"
    save_model(config, settings)
    labels = out / "labels.json"
    atomic_bytes(labels, json.dumps({"version": 1, "source": "review-studio", "corpus_fingerprint": "c" * 64,
        "labels": [{"face_id": faces[6].face_id, "image_sha16": faces[6].image_sha16,
                    "character": "Character B", "action": "confirm"}]}).encode())
    before_vector = file_digest(out / "identities.npy")
    before_manifest = file_digest(out / "manifest.sqlite")
    cli = [sys.executable, "-m", "artcurator.cli"]
    subprocess.run([*cli, "identity-apply", "--config", str(config), "--out", str(out), "--labels", str(labels)], check=True)
    first_apply = json.loads((out / "identity-apply-result.json").read_bytes())
    changes = json.loads((out / "identity-assignment-changes.json").read_bytes())
    subprocess.run([*cli, "identity-cluster", "--config", str(config), "--out", str(out)], check=True)
    pinned = [c for c in load_document(out).clusters if c.confirmed_character == "Character B"]
    subprocess.run([*cli, "identity-apply", "--config", str(config), "--out", str(out), "--labels", str(labels)], check=True)
    replay = json.loads((out / "identity-apply-result.json").read_bytes())
    receipt = {"first_apply": first_apply, "assignment_changes": changes,
        "pinned_after_recluster": len(pinned), "replay": replay,
        "vectors_unchanged": before_vector == file_digest(out / "identities.npy"),
        "manifest_unchanged": before_manifest == file_digest(out / "manifest.sqlite")}
    if not (first_apply["faces_changed"] == first_apply["clusters_changed"] == len(pinned) == 1
            and changes["changed_images"] == 12 and replay["faces_changed"] == 0
            and receipt["vectors_unchanged"] and receipt["manifest_unchanged"]):
        raise ValueError("synthetic naming roundtrip failed")
    atomic_bytes(out / "receipt.json", json.dumps(receipt, indent=2).encode())
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
