"""Two-layer WD cache: schema-only changes cost zero inference; model/preprocess changes re-infer.

The cache stores model-space score vectors keyed by crop content + model artifact + preprocessing
profile. Output schema/projection is applied at read time, so adding optional output fields must
not invalidate anything. Legacy handshake-bound entries are reused only when their model,
tag table, preprocessing profile and output contract all match, and the match is unambiguous.
"""
import csv
import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from artcurator import identity_tag, wd_preprocess
from artcurator.identity_schema import (
    ClusteringInfo,
    DetectorInfo,
    Face,
    IdentityDocument,
    ImageFaces,
    ModelInfo,
    Provenance,
)
from artcurator.identity_store import digest, file_digest, save_model
from artcurator.wd_cache import (
    InferenceIdentity,
    LegacyCacheEntry,
    inference_key,
    read_inference,
    scan_legacy,
)
from artcurator.wd_projection import compact, decode_raw, encode_raw, load_tags
from artcurator.wd_schema import Attributes, Evidence, Handshake, Response, Tag, TagDocument

TAGS: list[tuple[str, int]] = [
    ("hero_one", 4), ("hero_two", 4), ("black_hair", 0), ("long_hair", 0), ("smile", 0), ("general", 9)]


def scores_for(content: str) -> np.ndarray:
    seed = int(hashlib.sha256(content.encode()).hexdigest()[:8], 16)
    return np.random.default_rng(seed).random(len(TAGS), dtype=np.float32)


def build_corpus(tmp_path: Path, count: int = 4) -> tuple[Path, Path, list[str], list[str]]:
    out, model_dir = tmp_path / "out", tmp_path / "model"
    (out / "faces").mkdir(parents=True)
    model_dir.mkdir()
    (model_dir / "model.onnx").write_bytes(b"onnx-weights")
    with (model_dir / "selected_tags.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["tag_id", "name", "category", "count"])
        writer.writerows([index, name, category, 0] for index, (name, category) in enumerate(TAGS))
    faces, images, contents, ids = [], [], [], []
    for i in range(1, count + 1):
        face_id, sha16 = f"f_{i:08x}", f"{i:016x}"
        crop = out / "faces" / f"{face_id}.jpg"
        crop.write_bytes(f"crop-{i}".encode() * 4)
        content = file_digest(crop)
        faces.append(Face(face_id=face_id, image_sha16=sha16, bbox=(0, 0, 24, 24), det_score=.9,
                          crop_rel=f"faces/{face_id}.jpg"))
        images.append(ImageFaces(sha16=sha16, path_rel=f"p{i}.png", faces=[face_id]))
        contents.append(content)
        ids.append(face_id)
    model = ModelInfo(name="siglip", model="synthetic", revision="fixed")
    save_model(out / "identities.json", IdentityDocument(
        detector=DetectorInfo(name="synthetic", model="synthetic", revision="fixed"), embedder=model,
        clustering=ClusteringInfo(), image_count=count, face_count=count, cluster_count=0,
        images=images, faces=faces, clusters=[]))
    save_model(out / "identity-provenance.json", Provenance(
        corpus_fingerprint="c" * 64, semantic_profile="d" * 64,
        contents={f"{i:016x}": "a" * 64 for i in range(1, count + 1)},
        crops=dict(zip(ids, contents, strict=True))))
    return out, model_dir, contents, ids


class RecordingExchange:
    def __init__(self, scores: Callable[[str], np.ndarray], calls: list[int]) -> None:
        self.scores, self.calls = scores, calls

    def request(self, request: Any) -> Response:
        self.calls.append(len(request.input_ids))
        raw = [encode_raw(self.scores(content)) for content in request.input_ids]
        return Response(handshake=request.handshake, run_id=request.run_id, request_id=request.request_id,
            input_ids=request.input_ids, evidence=[compact(decode_raw(text), TAGS) for text in raw], raw=raw,
            providers_available=[request.handshake.provider], providers_active=[request.handshake.provider],
            load_seconds=0, inference_seconds=0)


def install(monkeypatch: pytest.MonkeyPatch, calls: list[int],
            scores: Callable[[str], np.ndarray] = scores_for) -> None:
    @contextmanager
    def factory(python: Path, error_log: Any) -> Iterator[RecordingExchange]:
        yield RecordingExchange(scores, calls)
    monkeypatch.setattr(identity_tag, "worker", factory)


def options(model_dir: Path) -> Any:
    return identity_tag.TagOptions(model_dir=model_dir, python=Path("unused"), batch_size=2,
                                   provider="CPUExecutionProvider")


def identity_of(model_dir: Path) -> InferenceIdentity:
    return InferenceIdentity(model_sha256=file_digest(model_dir / "model.onnx"),
                             tags_sha256=file_digest(model_dir / "selected_tags.csv"),
                             preprocess=wd_preprocess.preprocess_digest())


def write_legacy(cache: Path, content: str, handshake: Handshake, evidence: Evidence) -> str:
    key = digest((content + handshake.model_dump_json()).encode())
    save_model(cache / f"{key}.json", LegacyCacheEntry(key=key, handshake=handshake, evidence=evidence,
        payload_sha256=digest(evidence.model_dump_json().encode())))
    return key


def legacy_handshake(model: Path, build: str = "a" * 64, provider: str = "CPUExecutionProvider",
                     model_sha256: str | None = None) -> Handshake:
    return Handshake(build=build, model_sha256=model_sha256 or file_digest(model / "model.onnx"),
                     tags_sha256=file_digest(model / "selected_tags.csv"), packages={}, provider=provider)


# --- two-layer inference/projection behavior ------------------------------------------------

def test_schema_only_change_when_optional_field_added_then_zero_new_inferences(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a fully cached corpus and a schema-only change (worker/schema bytes plus output field).
    out, model_dir, contents, _ = build_corpus(tmp_path)
    calls: list[int] = []
    install(monkeypatch, calls)
    first = identity_tag.tag(out, options(model_dir))
    assert sum(calls) == len(contents)
    monkeypatch.setattr(identity_tag, "build_digest", lambda: "f" * 64)
    def compact_v2(scores: np.ndarray, tags: list[tuple[str, int]]) -> Evidence:
        base = compact(scores, tags)
        return base.model_copy(update={"attributes": base.attributes.model_copy(update={"schema_probe": "v2"})})
    monkeypatch.setattr(identity_tag, "compact", compact_v2)
    calls.clear()
    # When re-tagging; then every crop is served from the raw cache with zero inference.
    second = identity_tag.tag(out, options(model_dir))
    assert calls == []
    assert second.cached == len(contents)
    # And the new schema projection is applied at read time.
    assert all(face.evidence.attributes.schema_probe == "v2" for face in second.faces)  # type: ignore[attr-defined]
    assert [f.evidence.attributes.tags for f in second.faces] == [f.evidence.attributes.tags for f in first.faces]


def test_model_change_when_weights_change_then_all_crops_reinferred(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a cached corpus; when the model artifact changes; then every crop is re-inferred.
    out, model_dir, contents, _ = build_corpus(tmp_path)
    calls: list[int] = []
    install(monkeypatch, calls)
    identity_tag.tag(out, options(model_dir))
    calls.clear()
    (model_dir / "model.onnx").write_bytes(b"onnx-weights-v2")
    identity_tag.tag(out, options(model_dir))
    assert sum(calls) == len(contents)


def test_preprocess_change_when_profile_changes_then_all_crops_reinferred(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a cached corpus; when the preprocessing profile changes; then every crop is re-inferred.
    out, model_dir, contents, _ = build_corpus(tmp_path)
    calls: list[int] = []
    install(monkeypatch, calls)
    identity_tag.tag(out, options(model_dir))
    calls.clear()
    monkeypatch.setattr(wd_preprocess, "PREPROCESS", "wd-white-square-bicubic448-bgr-f32-0-255-v2")
    identity_tag.tag(out, options(model_dir))
    assert sum(calls) == len(contents)


def test_raw_cache_when_written_then_scores_reload_without_inference(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a first run; the second run loads raw vectors and never touches the worker.
    out, model_dir, contents, _ = build_corpus(tmp_path)
    calls: list[int] = []
    install(monkeypatch, calls)
    identity_tag.tag(out, options(model_dir))
    cache = out / "cache" / "wd-tagger"
    assert len(list(cache.glob("*.npy"))) == len(contents)
    identity = identity_of(model_dir)
    for content in contents:
        values = read_inference(cache, inference_key(content, identity), identity)
        assert values is not None and values.dtype == np.float32 and len(values) == len(TAGS)
    second = identity_tag.tag(out, options(model_dir))
    assert second.cached == len(contents)


def test_saved_document_when_written_then_raw_vectors_not_persisted(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a tag run; the audit document keeps batch metadata but never the raw class vectors.
    out, model_dir, _, _ = build_corpus(tmp_path)
    install(monkeypatch, [])
    identity_tag.tag(out, options(model_dir))
    data = json.loads((out / "wd-tagger.json").read_bytes())
    assert data["batches"] and all("raw" not in batch for batch in data["batches"])


def test_produced_evidence_when_inferred_then_byte_identical_to_pre_refactor(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a fresh run; the shipped projection must emit the frozen pre-refactor bytes exactly.
    out, model_dir, contents, ids = build_corpus(tmp_path)
    install(monkeypatch, [])
    result = identity_tag.tag(out, options(model_dir))
    expected = {face_id: _historical_compact(scores_for(content), TAGS).model_dump_json()
                for face_id, content in zip(ids, contents, strict=True)}
    assert {face.face_id: face.evidence.model_dump_json() for face in result.faces} == expected


# --- legacy (handshake-bound) cache reuse and invalidation -----------------------------------

def test_legacy_cache_when_compatible_then_reused_without_inference(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given old-format entries whose model/tags/preprocess/contract match the current run.
    out, model_dir, contents, _ = build_corpus(tmp_path)
    cache = out / "cache" / "wd-tagger"
    cache.mkdir(parents=True)
    expected = {}
    for content in contents:
        evidence = compact(scores_for(content), TAGS)
        expected[content] = evidence.model_dump_json()
        write_legacy(cache, content, legacy_handshake(model_dir, build="b" * 64), evidence)
    calls: list[int] = []
    install(monkeypatch, calls)
    # When tagging; then all evidence is reused safely with a reported count and no inference.
    result = identity_tag.tag(out, options(model_dir))
    assert calls == []
    assert (result.legacy_scanned, result.legacy_reused, result.legacy_invalidated) == (len(contents), len(contents), 0)
    assert {face.crop_sha256: face.evidence.model_dump_json() for face in result.faces} == expected


def test_legacy_cache_when_provider_duplicates_then_clear_match_reused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the same crop under two providers with different scores, the current provider wins.
    out, model_dir, contents, _ = build_corpus(tmp_path)
    cache = out / "cache" / "wd-tagger"
    cache.mkdir(parents=True)
    for content in contents:
        same = compact(scores_for(content), TAGS)
        other = compact(1 - scores_for(content), TAGS)
        write_legacy(cache, content, legacy_handshake(model_dir, build="c" * 64, provider="CPUExecutionProvider"), same)
        write_legacy(cache, content, legacy_handshake(model_dir, build="d" * 64, provider="CUDAExecutionProvider"), other)
    calls: list[int] = []
    install(monkeypatch, calls)
    result = identity_tag.tag(out, options(model_dir))
    assert calls == []
    assert result.legacy_reused == len(contents) and result.legacy_invalidated == 0
    assert {face.crop_sha256 for face in result.faces} == set(contents)


def test_legacy_cache_when_model_changed_then_declared_invalidated_and_reinferred(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given old entries from a different model artifact; they must be invalidated, not mis-read.
    out, model_dir, contents, _ = build_corpus(tmp_path)
    cache = out / "cache" / "wd-tagger"
    cache.mkdir(parents=True)
    for content in contents:
        write_legacy(cache, content, legacy_handshake(model_dir, model_sha256="b" * 64),
                     compact(scores_for(content), TAGS))
    calls: list[int] = []
    install(monkeypatch, calls)
    result = identity_tag.tag(out, options(model_dir))
    assert sum(calls) == len(contents)
    assert result.legacy_reused == 0 and result.legacy_invalidated == len(contents)


def test_legacy_cache_when_ambiguous_evidence_then_declared_invalidated_and_reinferred(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given two compatible entries for one crop whose evidence disagrees, the key is ambiguous.
    out, model_dir, contents, _ = build_corpus(tmp_path)
    cache = out / "cache" / "wd-tagger"
    cache.mkdir(parents=True)
    for content in contents:
        write_legacy(cache, content, legacy_handshake(model_dir, build="1" * 64), compact(scores_for(content), TAGS))
        write_legacy(cache, content, legacy_handshake(model_dir, build="2" * 64), compact(1 - scores_for(content), TAGS))
    calls: list[int] = []
    install(monkeypatch, calls)
    result = identity_tag.tag(out, options(model_dir))
    # Both ambiguous entries per crop are explicitly invalidated and inference happens instead.
    assert result.legacy_reused == 0 and result.legacy_invalidated == 2 * len(contents)
    assert sum(calls) == len(contents)


def test_new_cache_when_payload_digest_mismatch_then_fails_closed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a corrupted raw payload; the reader refuses it instead of projecting wrong scores.
    out, model_dir, _, _ = build_corpus(tmp_path)
    install(monkeypatch, [])
    identity_tag.tag(out, options(model_dir))
    payload = next((out / "cache" / "wd-tagger").glob("*.npy"))
    payload.write_bytes(b"\x00" + payload.read_bytes()[1:])
    with pytest.raises(ValueError, match="payload"):
        identity_tag.tag(out, options(model_dir))


def test_legacy_entry_when_key_field_mismatches_filename_then_fails_closed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a legacy entry whose recorded key disagrees with its filename.
    out, model_dir, contents, _ = build_corpus(tmp_path)
    cache = out / "cache" / "wd-tagger"
    cache.mkdir(parents=True)
    content = contents[0]
    key = write_legacy(cache, content, legacy_handshake(model_dir), compact(scores_for(content), TAGS))
    document = json.loads((cache / f"{key}.json").read_bytes())
    document["key"] = "0" * 64
    (cache / f"{key}.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="key"):
        scan_legacy(cache)


# --- backward-compatible artifacts and byte-identical projection -----------------------------

def _historical_compact(scores: np.ndarray, tags: list[tuple[str, int]]) -> Evidence:
    """Verbatim pre-refactor wd_worker.compact, frozen here as the byte-identity oracle."""
    if len(scores) != len(tags) or not np.isfinite(scores).all():
        raise ValueError("invalid WD scores")
    ranked = sorted(zip(tags, scores, strict=True), key=lambda item: (-float(item[1]), item[0][0]))
    characters = [Tag(tag=name, score=float(score)) for (name, category), score in ranked
                  if category == 4 and score > .35][:5]
    attributes = [Tag(tag=name, score=float(score)) for (name, category), score in ranked
                  if category == 0 and score > .35][:40]
    colors = [row.tag[:-5] for row in attributes if row.tag.endswith("_hair") and row.tag[:-5] in {
        "black", "brown", "blonde", "white", "grey", "gray", "red", "blue",
        "green", "pink", "purple", "orange", "silver", "multicolored"}]
    styles = [row.tag.replace("_", " ") for row in attributes
              if row.tag.endswith("_hair") and row.tag[:-5] not in {
                  "black", "brown", "blonde", "white", "grey", "gray", "red", "blue",
                  "green", "pink", "purple", "orange", "silver", "multicolored"}]
    return Evidence(characters=characters, attributes=Attributes(
        tags=attributes, hair_color=colors[0] if colors else None, hair_style=styles[0] if styles else None))


def test_projection_when_random_scores_then_byte_identical_to_pre_refactor() -> None:
    # Given seeded model-space scores; the new projection emits byte-identical evidence.
    rng = np.random.default_rng(11)
    boundary = np.asarray([.35, .350001, .9, 0.0, .5, .5], dtype=np.float32)
    samples = [rng.random(len(TAGS), dtype=np.float32) for _ in range(24)] + [boundary]
    for scores in samples:
        assert compact(scores, TAGS).model_dump_json() == _historical_compact(scores, TAGS).model_dump_json()


def test_raw_codec_when_float32_then_round_trips_exactly() -> None:
    rng = np.random.default_rng(3)
    values = rng.random(37, dtype=np.float32)
    decoded = decode_raw(encode_raw(values))
    assert decoded.dtype == np.float32 and decoded.tobytes() == values.tobytes()


def test_tag_table_when_loaded_from_csv_then_matches_worker_order(tmp_path: Path) -> None:
    _, model_dir, _, _ = build_corpus(tmp_path)
    assert load_tags(model_dir / "selected_tags.csv") == TAGS


def test_document_when_legacy_artifact_without_new_fields_parses() -> None:
    # Given a document written before raw batches / legacy counters existed.
    handshake = Handshake(build="a" * 64, model_sha256="b" * 64, tags_sha256="c" * 64, packages={})
    response = Response(handshake=handshake, run_id="r", request_id="q", input_ids=["d" * 64],
        evidence=[Evidence()], providers_available=["CPUExecutionProvider"],
        providers_active=["CPUExecutionProvider"], load_seconds=0, inference_seconds=0)
    legacy = {"version": 1, "handshake": json.loads(handshake.model_dump_json()),
              "corpus_fingerprint": "c" * 64, "faces": [], "batches": [json.loads(response.model_dump_json())]}
    parsed = TagDocument.model_validate_json(json.dumps(legacy))
    assert parsed.batches[0].raw is None
    assert (parsed.legacy_scanned, parsed.legacy_reused, parsed.legacy_invalidated) == (0, 0, 0)
    assert "raw" not in json.dumps(legacy["batches"][0])


def test_schema_when_optional_field_added_then_old_evidence_still_parses() -> None:
    # Given evidence serialized before an optional output field existed (extra fields are additive).
    old = json.loads(Evidence(characters=[Tag(tag="hero", score=.9)]).model_dump_json())
    parsed = Evidence.model_validate(old)
    assert parsed.characters[0].tag == "hero"
