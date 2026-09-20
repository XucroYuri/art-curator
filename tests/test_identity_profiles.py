"""Execution isolation and unbiased scoring contracts on synthetic vectors."""
import importlib
from pathlib import Path

import numpy as np
import pytest

from artcurator.identity_schema import IdentityOptions
from test_identity_edges import empty_detector, synthetic_manifest
from artcurator.identity_detect import detect


def test_options_when_execution_profile_requested() -> None:
    # Given explicit CPU and GPU requests; when parsed; then both remain distinct.
    assert IdentityOptions(device="cpu").device == "cpu"
    assert IdentityOptions(device="cuda", batch_size=8).batch_size == 8
    assert IdentityOptions().device == "auto"
    assert IdentityOptions().precision == "float32"
    assert IdentityOptions(device="cuda", precision="float16").precision == "float16"
    with pytest.raises(ValueError):
        IdentityOptions(device="gpu")


def test_detection_when_only_execution_changes(tmp_path: Path) -> None:
    # Given cached CPU detection.
    synthetic_manifest(tmp_path)
    detect(tmp_path, IdentityOptions(device="cpu"), empty_detector())
    # When only the embedding execution request changes; then detection resumes.
    detect(tmp_path, IdentityOptions(device="cuda", batch_size=32), empty_detector())


def test_loo_when_member_scores_own_cluster() -> None:
    # Given two orthogonal members and one external query.
    module = importlib.import_module("artcurator.identity_report")
    vectors = np.array([[1., 0.], [0., 1.], [1., 0.]])
    # When scoring with leave-one-out; then members have no self contribution.
    result = module.loo_scores(vectors, [np.array([0, 1])])
    np.testing.assert_allclose(result, [0., 0., 2 ** -.5], atol=1e-7)


def test_loo_when_singleton_or_zero_sum() -> None:
    # Given a singleton target; when queried by itself; then score is unavailable.
    module = importlib.import_module("artcurator.identity_report")
    result = module.loo_scores(np.eye(2), [np.array([0])])
    assert np.isnan(result[0])
    assert result[1] == 0
    # Given a cancelling target; when queried externally; then it is unavailable.
    result = module.loo_scores(np.array([[1., 0.], [-1., 0.], [0., 1.]]), [np.array([0, 1])])
    assert np.isnan(result[2])


def test_namespace_when_execution_or_model_changes() -> None:
    # Given one crop under distinct execution/model profiles.
    module = importlib.import_module("artcurator.identity_profiles")
    cpu = module.ExecutionProfile(device="cpu", precision="float32", batch_size=1, runtime={})
    gpu = module.ExecutionProfile(device="cuda", precision="float16", batch_size=16, runtime={})
    # When namespaced; then neither device, revision nor preprocessing can alias.
    keys = {module.embedding_namespace(profile, revision, preproc)
            for profile in (cpu, gpu) for revision in ("a", "b") for preproc in ("v1", "v2")}
    assert len(keys) == 8


def test_auto_when_cuda_is_uncertified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given available hardware but no matching certificate.
    import torch
    from artcurator import identity_profiles as module
    monkeypatch.setattr(module, "CERTIFICATE", tmp_path / "absent.json")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda: "synthetic-gpu")
    monkeypatch.setattr(torch.cuda, "get_device_capability", lambda: (12, 0))
    # When auto is resolved; then it retains CPU rather than assuming certification.
    assert module.execution_profile(IdentityOptions()).device == "cpu"


def test_cuda_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no CUDA hardware; when explicitly requested; then no silent CPU fallback.
    import torch
    from artcurator.identity_profiles import execution_profile
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(ValueError, match="CUDA requested"):
        execution_profile(IdentityOptions(device="cuda"))


def test_auto_when_certificate_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a numerical certificate for one runtime and batch only.
    import torch
    from artcurator import identity_profiles as module
    from artcurator.identity_store import save_model
    monkeypatch.setattr(module, "CERTIFICATE", tmp_path / "certificate.json")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda: "synthetic-gpu")
    monkeypatch.setattr(torch.cuda, "get_device_capability", lambda: (12, 0))
    candidate = module.execution_profile(IdentityOptions(device="cuda"))
    save_model(module.CERTIFICATE, module.Certificate(version=1, model="fixture", revision="v1",
        preprocess=module.PREPROCESS, execution=candidate, numerical_pass=True, evidence_sha256="a" * 64))
    # When auto requests matching and different batches; then only the certified one is admitted.
    assert module.execution_profile(IdentityOptions()).device == "cuda"
    assert module.execution_profile(IdentityOptions(batch_size=7)).device == "cpu"
    assert module.execution_profile(IdentityOptions(precision="float16")).device == "cpu"
    assert module.execution_profile(IdentityOptions(threads=2)).device == "cpu"
    with pytest.raises(ValueError, match="does not cover"):
        module.certify_model(candidate, ("different-model", "v1"))


def test_embedding_when_partial_cache_and_ragged_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given three synthetic faces and a two-item execution batch.
    import json
    from artcurator import identity_embed as module
    from artcurator.identity_profiles import ExecutionProfile
    from artcurator.identity_schema import Provenance
    from artcurator.identity_store import file_digest, load_vectors, load_document, save_model
    from PIL import Image
    fixture = Path(__file__).parent / "fixtures/identity/identities.json"
    (tmp_path / "identities.json").write_bytes(fixture.read_bytes())
    document = load_document(tmp_path)
    (tmp_path / "faces").mkdir()
    for index, face in enumerate(document.faces):
        with Image.new("RGB", (32, 32), (index * 40, 80, 100)) as image:
            image.save(tmp_path / face.crop_rel)
    save_model(tmp_path / "identity-provenance.json", Provenance(corpus_fingerprint="a" * 64,
        semantic_profile="b" * 64, contents={"a" * 16: "a" * 64, "b" * 16: "b" * 64},
        crops={face.face_id: file_digest(tmp_path / face.crop_rel) for face in document.faces}))
    batches = []

    def predict(images: list[Image.Image]) -> np.ndarray:
        batches.append(len(images))
        return np.array([[np.asarray(image)[0, 0, 0] + 1., 1.] for image in images])

    profile = ExecutionProfile(device="cpu", precision="float32", batch_size=2, runtime={})
    monkeypatch.setattr(module, "load_embedder", lambda out, options:
        module.CropEmbedder("fixture", "v1", "v1", predict, profile))
    # When embedding fresh; then ragged batching preserves exact face association.
    module.embed(tmp_path, IdentityOptions(device="cpu"))
    assert batches == [2, 1]
    assert load_document(tmp_path).cluster_count == 0
    values = load_vectors(tmp_path, load_document(tmp_path))
    assert np.all(np.diff(values[:, 0]) > 0)
    first = json.loads((tmp_path / "identity-embedding.json").read_bytes())
    assert first["metrics"]["s_per_face"] == first["metrics"]["inference_seconds"] / 3
    # When resuming with one damaged entry; then only that entry is recomputed.
    entry = next((tmp_path / "cache/identity-embedding" / first["namespace"]).glob("*.npy"))
    entry.write_bytes(b"corrupt")
    batches.clear()
    module.embed(tmp_path, IdentityOptions(device="cpu"))
    assert batches == [1]
    assert json.loads((tmp_path / "identity-embedding.json").read_bytes())["metrics"]["cached"] == 2
    # When execution identity changes; then the complete corpus gets fresh keys.
    batches.clear()
    replacement = profile.model_copy(update={"runtime": {"build": "different"}})
    monkeypatch.setattr(module, "load_embedder", lambda out, options:
        module.CropEmbedder("fixture", "v1", "v1", predict, replacement))
    module.embed(tmp_path, IdentityOptions(device="cpu"))
    second = json.loads((tmp_path / "identity-embedding.json").read_bytes())
    assert batches == [2, 1]
    assert second["metrics"]["cached"] == 0
    assert second["namespace"] != first["namespace"]


def test_apply_when_confirmed_cluster_changes_target(tmp_path: Path) -> None:
    # Given synthetic vectors, manifest, and an unlabeled largest-cluster target.
    import json
    from artcurator import db
    from artcurator.config import Settings
    from artcurator.identity import run
    from artcurator.identity_schema import Provenance
    from artcurator.identity_store import file_digest, load_document, save_array, save_model
    fixture = Path(__file__).parent / "fixtures/identity/identities.json"
    (tmp_path / "identities.json").write_bytes(fixture.read_bytes())
    document = load_document(tmp_path)
    db.save_rows(tmp_path, [db.Row(sha16=char * 16, sha256=char * 64, abs_path="synthetic.png",
        path_rel="synthetic.png", filename="synthetic.png", width=32, height=32, filesize=1,
        phash="0", mode="RGB", identity_sim=.5) for char in ("a", "b")])
    save_model(tmp_path / "identity-provenance.json", Provenance(corpus_fingerprint="c" * 64,
        semantic_profile="d" * 64, contents={char * 16: char * 64 for char in ("a", "b")},
        crops={face.face_id: "e" * 64 for face in document.faces}))
    save_array(tmp_path / "identities.npy", np.array([[1., 0.], [0., 1.], [1., 0.]], dtype=np.float16))
    (tmp_path / "identity-embedding.json").write_text(json.dumps({"faces": [f.face_id for f in document.faces],
        "sha256": file_digest(tmp_path / "identities.npy"), "semantic_profile": "d" * 64}))
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"version": 1, "source": "review-studio", "corpus_fingerprint": "c" * 64,
        "labels": [{"face_id": "f_00000002", "image_sha16": "a" * 16,
                    "character": "Character B", "action": "confirm"}]}))
    settings = Settings(input=tmp_path, references=tmp_path, posted=tmp_path, characters_root=tmp_path, out=tmp_path)
    # When the real coordinator applies labels; then pinning, assignment diff and report agree.
    run(settings, "identity-apply", labels)
    assert load_document(tmp_path).clusters[1].confirmed_character == "Character B"
    changes = json.loads((tmp_path / "identity-assignment-changes.json").read_bytes())
    assert changes["changed_images"] == 1
    assert changes["changes"][0] == {"image_sha16": "b" * 16, "before": 1., "after": 0.}
    assert json.loads((tmp_path / "identity-ab.json").read_bytes())["target_clusters"] == [2]
