"""Candidate sidecar embedding preserves the offline and forward-compatible boundary."""
import base64
import csv
import gzip
import json
from pathlib import Path

from tools import build_gallery


def test_candidates_when_sidecar_exists(tmp_path: Path) -> None:
    # Given a face and future optional candidate evidence.
    face = {"face_id": "f_00000001", "image_sha16": "a" * 16}
    candidate = {"character": "A", "score": .8, "margin_vs_runner_up": .2,
                 "source": "anchor", "attributes": {"version": 1}}
    (tmp_path / "identities.json").write_text(json.dumps({"faces": [face]}))
    (tmp_path / "identity-candidates.json").write_text(json.dumps({"version": 1,
        "faces": [{**face, "candidates": [candidate], "suggested": "A", "abstained": False}]}))
    # When the gallery loads identity metadata.
    result = build_gallery.load_identities(tmp_path / "identities.json")
    # Then candidate extensions remain intact in the embedded face record.
    assert result["faces"][0]["candidate_evidence"]["candidates"] == [candidate]


def test_candidates_when_image_binding_is_wrong(tmp_path: Path) -> None:
    # Given a stale face/image association.
    (tmp_path / "identities.json").write_text(json.dumps({"faces": [
        {"face_id": "f_00000001", "image_sha16": "a" * 16}]}))
    (tmp_path / "identity-candidates.json").write_text(json.dumps({"version": 1, "faces": [
        {"face_id": "f_00000001", "image_sha16": "b" * 16, "candidates": []}]}))
    # When loaded; then stale evidence cannot attach to another image.
    result = build_gallery.load_identities(tmp_path / "identities.json")
    assert "candidate_evidence" not in result["faces"][0]


def test_picker_when_studio_lists_ranked_choices() -> None:
    # Given the generated studio template after candidate injection.
    template = build_gallery.HTML_TEMPLATE
    # When inspecting the face naming popover contract.
    # Then ranked choices, honesty, keyboard map and journal fields are present.
    assert "renderSuggestionTiers(evidence)" in template
    assert 'make("other", "其他")' in template
    assert 'make("full", "新建角色")' in template
    assert 'make("ignore", "不是")' in template
    assert 'make("skip", "跳过")' in template
    assert r"/^[1-5]$/" in template
    assert "handleCandidateKey" in template
    assert "advanceToNextUnlabeledFace" in template
    assert "candidateSkipped" in template
    assert ".candidate-choice" in template
    assert 'source:"review-studio"' in template
    assert "character_labels.json" in template
    assert "face_id:String(label.face_id||\"\")" in template
    assert "image_sha16:String(label.image_sha16||\"\")" in template


def test_candidates_when_compact_payload_keeps_evidence(tmp_path: Path) -> None:
    # Given scores plus a sidecar that carries optional attribute evidence.
    scores = tmp_path / "scores.csv"
    with scores.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=build_gallery.CSV_COLUMNS)
        writer.writeheader()
        row = {column: "" for column in build_gallery.CSV_COLUMNS}
        row.update({"sha16": "sha-one", "abs_path": "C:/one.png", "path_rel": "one.png",
                    "filename": "one.png", "width": "32", "height": "32", "filesize": "100",
                    "phash": "abcd", "family_id": "fam_0001", "aes_v25": "1.0", "topiq_iaa": "1.0",
                    "topiq_nr": "1.0", "nsfw_prob": "0.0", "identity_sim": "1.0", "novelty": "1.0",
                    "consensus_z": "0.0", "disagreement": "0.0", "proposed_tier": "queue"})
        writer.writerow(row)
    face = {"face_id": "f_00000001", "image_sha16": "sha-one"}
    candidate = {"character": "A", "score": .8, "margin_vs_runner_up": .2,
                 "source": "anchor", "attributes": {"version": 1, "hair": {"score": .2}}}
    (tmp_path / "identities.json").write_text(json.dumps({"faces": [face], "images": [
        {"sha16": "sha-one", "faces": ["f_00000001"]}], "clusters": []}))
    (tmp_path / "identity-candidates.json").write_text(json.dumps({"version": 1, "faces": [
        {**face, "candidates": [candidate], "suggested": "A", "abstained": False}]}))
    # When the browser payload is compressed.
    payload = build_gallery.build_payload(tmp_path, tuple(build_gallery.read_scores(scores)),
                                          build_gallery.CSV_COLUMNS)
    encoded, _ = build_gallery.encode_payload(payload)
    decoded = json.loads(gzip.decompress(base64.b64decode(encoded)).decode("utf-8"))
    # Then optional evidence survives the Python/browser boundary.
    assert decoded["y"]["faces"][0]["candidate_evidence"]["candidates"] == [candidate]


def test_candidates_v2_when_sources_and_memory_sidecars_exist(tmp_path: Path) -> None:
    # Given v2 candidate provenance plus a v1 character-memory document.
    face = {"face_id": "f_v2", "image_sha16": "sha-v2"}
    candidate_document = {
        "version": 2.1,
        "sources": {
            "model": {"name": "WD tagger", "license": "Apache-2.0", "closed_set": 2751},
            "memory": {"name": "character-memory", "version": 1},
        },
        "faces": [
            {
                **face,
                "candidates": [
                    {"name": "人物甲", "display": "人物甲", "source": "model", "score_model": 0.91},
                    {"name": "人物乙", "display": "人物乙", "source": "memory", "score_memory": 0.82},
                    {"name": "其他", "display": "其他", "source": "bucket"},
                    {"name": "新建角色", "display": "新建角色", "source": "action"},
                ],
                "suggested": {"name": "人物甲", "display": "人物甲"},
                "suggested_verified": {"name": "人物甲", "display": "人物甲"},
                "suggested_model": {"name": "人物乙", "display": "人物乙", "score": .99,
                    "margin_vs_runner_up": .64, "verified": False, "gate": "wd-score-margin-v1"},
                "model_demoted": True,
                "disagreements": [{"model_name": "人物乙", "evidence_name": "人物甲", "source": "memory"}],
                "abstained": False,
                "attributes": {
                    "source": "wd-tagger",
                    "hair_color": "black",
                    "hair_style": "long hair",
                    "tags": [{"tag": "portrait", "score": 0.88}],
                },
            }
        ],
    }
    (tmp_path / "identities.json").write_text(json.dumps({"faces": [face]}), encoding="utf-8")
    (tmp_path / "identity-candidates.json").write_text(json.dumps(candidate_document), encoding="utf-8")
    memory_document = {
        "characters": [
            {
                "name": "人物甲",
                "origin": "model",
                "aliases": [],
                "baseline_faces": ["f_v2"],
                "variant_faces": [{"face_id": "f_v2", "note": "side profile"}],
                "assigned_faces": ["f_v2"],
                "attribute_profile": {},
                "updated_at": "2026-09-21T00:00:00Z",
            }
        ]
    }
    (tmp_path / "character-memory.json").write_text(json.dumps(memory_document), encoding="utf-8")

    # When identity and gallery payloads are loaded.
    identities = build_gallery.load_identities(tmp_path / "identities.json")
    payload = build_gallery.build_payload(tmp_path, (), ())

    # Then root provenance, face evidence, and memory remain available to the browser.
    assert identities is not None
    evidence = identities["faces"][0]["candidate_evidence"]
    assert evidence["version"] == 2.1
    assert evidence["suggested_model"]["verified"] is False
    assert evidence["model_demoted"] is True
    assert evidence["suggested_verified"] == evidence["suggested"]
    assert evidence["disagreements"][0]["evidence_name"] == "人物甲"
    assert evidence["sources"]["model"]["license"] == "Apache-2.0"
    assert evidence["attributes"]["hair_color"] == "black"
    assert payload["memory"] == memory_document
    assert build_gallery.compact_payload(payload)["m"] == memory_document


def test_picker_v2_surface_contains_sections_marks_and_memory_contract() -> None:
    # Given the generated single-file studio template.
    template = build_gallery.HTML_TEMPLATE

    # When inspecting the v2 curation surface.
    # Then both candidate provenance and client-side memory operations are embedded.
    for label in ("模型枚举", "我的命名", "普通人物", "新角色设计", "无法确定"):
        assert label in template
    for marker in ("baseline", "variant", "标为基准参考形象", "标为变体参考", "character-memory.json"):
        assert marker in template
    for operation in ("重命名", "合并到", "删除", "导出", "导入"):
        assert operation in template
