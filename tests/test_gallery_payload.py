"""Payload, identity, and grouping contracts for the offline gallery builder."""

import base64
import csv
import gzip
import json
from pathlib import Path

import pytest

from tools import build_gallery


def _write_scores_csv(path: Path, columns: tuple[str, ...], **overrides: str) -> None:
    row = {column: "" for column in columns}
    row.update(
        {
            "sha16": "sha-one",
            "abs_path": "C:/one.png",
            "path_rel": "one.png",
            "filename": "one.png",
            "width": "32",
            "height": "32",
            "filesize": "100",
            "phash": "abcd",
            "family_id": "fam_0001",
            "aes_v25": "1.0",
            "topiq_iaa": "1.0",
            "topiq_nr": "1.0",
            "nsfw_prob": "0.0",
            "identity_sim": "1.0",
            "novelty": "1.0",
            "consensus_z": "0.0",
            "disagreement": "0.0",
            "gaming_delta": "",
            "flags": "",
            "proposed_tier": "queue",
            "thumb_rel": "",
        }
    )
    row.update({key: value for key, value in overrides.items() if key in columns})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerow(row)


def test_compact_payload_is_columnar_and_gzip_decodable(tmp_path: Path) -> None:
    # Given a report row with the optional fourth scorer.
    scores_path = tmp_path / "scores.csv"
    _write_scores_csv(scores_path, build_gallery.CSV_COLUMNS, qrealign="0.875")
    payload = build_gallery.build_payload(tmp_path, tuple(build_gallery.read_scores(scores_path)), build_gallery.CSV_COLUMNS)

    # When the browser payload encoder runs.
    encoded, metrics = build_gallery.encode_payload(payload)
    decoded = json.loads(gzip.decompress(base64.b64decode(encoded)).decode("utf-8"))

    # Then it has short-key column arrays, no row-object array, and a stable fingerprint.
    assert decoded["v"] == 4
    assert decoded["n"] == 1
    assert decoded["ng"] is None
    assert decoded["na"] == {}
    assert decoded["cl"] is None
    assert "rows" not in decoded
    assert decoded["c"]["s"] == ["sha-one"]
    assert decoded["c"]["qr"] == [0.875]
    assert decoded["i"] == metrics.fingerprint
    assert metrics.base64_bytes < metrics.legacy_json_bytes


def test_generated_gallery_contains_native_decoder_and_virtualization_contract(tmp_path: Path) -> None:
    # Given a minimal scores directory that can be rendered without image files.
    scores_path = tmp_path / "scores.csv"
    _write_scores_csv(scores_path, build_gallery.CSV_COLUMNS, qrealign="0.875")

    # When the offline report is generated with explicit generic branding.
    output = build_gallery.build_gallery(tmp_path, title="审查台", subtitle="测试语料")
    html = output.read_text(encoding="utf-8")

    # Then the generated artifact advertises the performance and review contracts.
    assert "审查台" in html
    assert "测试语料" in html
    assert 'new DecompressionStream("gzip")' in html
    assert "requestAnimationFrame" in html
    assert "requestIdleCallback" in html
    assert 'loading="lazy"' in html
    assert "content-visibility:auto" in html
    assert "manual_decision" in html
    assert "previews/" in html
    assert "row.preview_available&&!row.thumb_available" in html
    assert 'event.key==="Tab"&&els("face-popover").hidden&&!(event.target instanceof Element&&event.target.closest("[data-face-id]"))' in html
    assert "@media(min-width:1440px)" in html
    assert "body:has(.family-panel.is-open)" in html
    assert "grid-template-columns:minmax(0,1fr) var(--drawer-width)" in html
    assert "__PAYLOAD_B64__" not in html


def test_parse_args_accepts_generic_title_and_subtitle(tmp_path: Path) -> None:
    # Given explicit report branding flags.
    args = build_gallery.parse_args(
        ["--out", str(tmp_path), "--title", "批次审查", "--subtitle", "本地素材库"]
    )

    # Then both overrides survive argument parsing.
    assert args.title == "批次审查"
    assert args.subtitle == "本地素材库"


def test_load_identities_defaults_missing_fields_and_preserves_unknown_fields(tmp_path: Path) -> None:
    # Given a producer document with partial records and a future field.
    path = tmp_path / "identities.json"
    path.write_text(
        json.dumps(
            {
                "future_root": {"keep": True},
                "images": [{"sha16": "sha-one"}],
                "faces": [{"face_id": "f_one", "image_sha16": "sha-one", "bbox": [1, 2, 3, 4]}],
                "clusters": [{"cluster_id": 7}],
            }
        ),
        encoding="utf-8",
    )

    # When the optional identity document is loaded.
    result = build_gallery.load_identities(path)

    # Then browser-facing defaults exist without dropping forward-compatible data.
    assert result is not None
    assert result["version"] == 1
    assert result["detector"]["min_face_px"] == 0
    assert result["images"][0]["faces"] == []
    assert result["faces"][0]["det_score"] is None
    assert result["clusters"][0]["representative_faces"] == []
    assert result["future_root"] == {"keep": True}


def test_build_payload_hides_identity_layer_when_artifact_is_absent(tmp_path: Path) -> None:
    # Given the existing image-only contract without identities.json.
    scores_path = tmp_path / "scores.csv"
    _write_scores_csv(scores_path, build_gallery.CSV_COLUMNS)
    rows = tuple(build_gallery.read_scores(scores_path))

    # When the payload is built.
    payload = build_gallery.build_payload(tmp_path, rows, build_gallery.CSV_COLUMNS)

    # Then the optional feature has no visible metadata at all.
    assert payload["identities"] is None
    assert payload["characters"] is None


def test_compact_payload_preserves_identity_unknown_fields(tmp_path: Path) -> None:
    # Given an identity artifact carrying an unknown nested field.
    scores_path = tmp_path / "scores.csv"
    _write_scores_csv(scores_path, build_gallery.CSV_COLUMNS)
    (tmp_path / "identities.json").write_text(
        json.dumps(
            {
                "images": [{"sha16": "sha-one", "faces": ["f_one"]}],
                "faces": [{"face_id": "f_one", "image_sha16": "sha-one"}],
                "clusters": [],
                "future": {"producer_revision": "next"},
            }
        ),
        encoding="utf-8",
    )
    payload = build_gallery.build_payload(
        tmp_path,
        tuple(build_gallery.read_scores(scores_path)),
        build_gallery.CSV_COLUMNS,
    )

    # When the compressed browser payload is decoded.
    encoded, _ = build_gallery.encode_payload(payload)
    decoded = json.loads(gzip.decompress(base64.b64decode(encoded)).decode("utf-8"))

    # Then the complete future field survives the Python/browser boundary.
    assert decoded["y"]["future"] == {"producer_revision": "next"}


def test_generated_gallery_contains_character_label_export_contract(tmp_path: Path) -> None:
    # Given a generic report with a valid optional identity document.
    scores_path = tmp_path / "scores.csv"
    _write_scores_csv(scores_path, build_gallery.CSV_COLUMNS)
    (tmp_path / "identities.json").write_text(
        json.dumps(
            {
                "images": [{"sha16": "sha-one", "faces": ["f_one"]}],
                "faces": [{"face_id": "f_one", "image_sha16": "sha-one"}],
                "clusters": [],
            }
        ),
        encoding="utf-8",
    )

    # When the offline report is generated.
    html = build_gallery.build_gallery(tmp_path).read_text(encoding="utf-8")

    # Then the exact label envelope and supported actions are embedded in the UI.
    assert 'source:"review-studio"' in html
    assert "corpus_fingerprint:" in html
    assert "labels:" in html
    assert "character_labels.json" in html
    assert 'lastFocus!==document.body&&!modal.contains(lastFocus)' in html
    assert "const faceId=state.openFaceId" in html
    for action in ("confirm", "new", "ignore", "wrong_box"):
        assert f'"{action}"' in html


def _write_grouping_artifacts(directory: Path) -> None:
    """Write a small many-to-many grouping fixture for gallery boundary tests."""
    (directory / "character-groups.json").write_text(
        json.dumps(
            {
                "version": 1,
                "future_root": {"producer_revision": "next"},
                "provenance": {"algorithm": "fixture-grouping"},
                "thresholds": {"min_sim": 0.9, "min_margin": 0.05},
                "characters": [
                    {
                        "character": "人物甲",
                        "image_count": 1,
                        "face_count": 1,
                        "images": ["sha-one"],
                        "mean_sim": 0.96,
                        "min_margin": 0.08,
                        "future_character": "kept",
                    }
                ],
                "abstained": {
                    "face_count": 1,
                    "cluster_groups": [{"cluster_id": 4, "face_count": 1, "images": ["sha-two"]}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (directory / "character-groups-by-image.csv").write_text(
        "sha16,filename,characters\n"
        "sha-one,one.png,人物甲|新人物00\n"
        "sha-two,two.png,\n",
        encoding="utf-8",
    )
    (directory / "character-groups-by-character.csv").write_text(
        "character,sha16,filename,face_id,sim,margin,decision\n"
        "人物甲,sha-one,one.png,face-one,0.96,0.08,assigned\n"
        "新人物00,sha-two,two.png,face-two,0.71,0.01,abstained\n",
        encoding="utf-8",
    )
    (directory / "anchors.json").write_text(
        json.dumps({"version": 1, "future_anchor": {"keep": True}}),
        encoding="utf-8",
    )


def test_load_character_grouping_normalizes_csv_and_preserves_unknown_fields(tmp_path: Path) -> None:
    # Given grouping artifacts with a multi-role image, an empty role, and producer extensions.
    _write_grouping_artifacts(tmp_path)

    # When the optional grouping boundary is loaded.
    result = build_gallery.load_character_grouping(tmp_path)

    # Then normalized browser data keeps both role semantics and forward-compatible fields.
    assert result is not None
    assert result["future_root"] == {"producer_revision": "next"}
    assert result["by_image"][0]["characters"] == ["人物甲", "新人物00"]
    assert result["by_image"][1]["characters"] == []
    assert result["by_character"][0]["sim"] == 0.96
    assert result["anchors"] == {"version": 1, "future_anchor": {"keep": True}}


def test_compact_payload_embeds_short_key_grouping_data(tmp_path: Path) -> None:
    # Given one score row and the optional grouping artifacts.
    scores_path = tmp_path / "scores.csv"
    _write_scores_csv(scores_path, build_gallery.CSV_COLUMNS, sha16="sha-one")
    _write_grouping_artifacts(tmp_path)
    payload = build_gallery.build_payload(
        tmp_path,
        tuple(build_gallery.read_scores(scores_path)),
        build_gallery.CSV_COLUMNS,
    )

    # When the existing gzip/base64 payload boundary is encoded.
    encoded, _ = build_gallery.encode_payload(payload)
    decoded = json.loads(gzip.decompress(base64.b64decode(encoded)).decode("utf-8"))

    # Then grouping uses compact keys while preserving the artifact extension.
    assert decoded["r"]["v"] == 1
    assert decoded["r"]["i"][0][2] == ["人物甲", "新人物00"]
    assert decoded["r"]["u"]["future_root"] == {"producer_revision": "next"}


def test_generated_gallery_contains_grouping_view_contract(tmp_path: Path) -> None:
    # Given a generic score directory with all grouping artifacts.
    scores_path = tmp_path / "scores.csv"
    _write_scores_csv(scores_path, build_gallery.CSV_COLUMNS, sha16="sha-one")
    _write_grouping_artifacts(tmp_path)

    # When the offline report is generated.
    html = build_gallery.build_gallery(tmp_path).read_text(encoding="utf-8")

    # Then the third view and naming-loop affordances are present in Chinese.
    for marker in ("人物分组", "仅看未定", "开始命名未定人脸", "min_sim"):
        assert marker in html


def test_build_payload_hides_grouping_when_artifact_is_absent(tmp_path: Path) -> None:
    # Given the existing image-only contract without grouping.json.
    scores_path = tmp_path / "scores.csv"
    _write_scores_csv(scores_path, build_gallery.CSV_COLUMNS)
    rows = tuple(build_gallery.read_scores(scores_path))

    # When the payload is built.
    payload = build_gallery.build_payload(tmp_path, rows, build_gallery.CSV_COLUMNS)

    # Then the new view remains absent rather than showing an empty panel.
    assert payload["grouping"] is None
    assert payload["negotiation"] is None
