"""Contracts for the stdlib-only offline gallery builder."""

import csv
import base64
import gzip
import json
from dataclasses import replace
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


def test_load_families_when_pipeline_array_shape(tmp_path: Path) -> None:
    # Given the pipeline's array-shaped family metadata with a null runner-up.
    families_path = tmp_path / "families.json"
    families_path.write_text(
        json.dumps(
            [
                {
                    "family_id": "fam_0001",
                    "members": ["sha-one"],
                    "champion": "sha-one",
                    "runner_up": None,
                }
            ]
        ),
        encoding="utf-8",
    )
    # When family metadata is loaded.
    result = build_gallery.load_families(families_path, ())
    # Then it is normalized to the browser payload shape.
    assert result == {
        "fam_0001": {"members": ["sha-one"], "champion": "sha-one", "runner_up": ""}
    }


def test_load_families_when_legacy_dict_shape(tmp_path: Path) -> None:
    # Given the existing keyed-object family metadata with omitted labels.
    families_path = tmp_path / "families.json"
    families_path.write_text(
        json.dumps({"fam_0001": {"members": ["sha-one"]}}),
        encoding="utf-8",
    )
    # When family metadata is loaded.
    result = build_gallery.load_families(families_path, ())
    # Then omitted labels remain empty strings.
    assert result["fam_0001"]["champion"] == ""
    assert result["fam_0001"]["runner_up"] == ""


def test_load_families_overlays_csv_derived_members(tmp_path: Path) -> None:
    # Given CSV-derived membership plus file metadata for one existing family and one new family.
    row = build_gallery.ScoreRow(
        sha16="sha-one",
        abs_path="C:/one.png",
        path_rel="one.png",
        filename="one.png",
        width=32,
        height=32,
        filesize=100,
        phash="abcd",
        family_id="fam_0001",
        aes_v25=1.0,
        topiq_iaa=1.0,
        topiq_nr=1.0,
        nsfw_prob=0.0,
        identity_sim=1.0,
        confusable_margin=None,
        novelty=1.0,
        consensus_z=0.0,
        disagreement=0.0,
        gaming_delta=None,
        flags=(),
        proposed_tier="queue",
        thumb_rel="",
    )
    csv_only_row = replace(row, sha16="sha-csv-only", family_id="fam_csv_only")
    families_path = tmp_path / "families.json"
    families_path.write_text(
        json.dumps(
            [
                {"family_id": "fam_0001", "members": ["sha-override"]},
                {"family_id": "fam_new", "members": ["sha-new"]},
            ]
        ),
        encoding="utf-8",
    )
    # When family metadata is loaded.
    result = build_gallery.load_families(families_path, (row, csv_only_row))
    # Then file metadata overlays the existing family while preserving CSV-only families via the merge.
    assert result["fam_0001"]["members"] == ["sha-override"]
    assert result["fam_csv_only"]["members"] == ["sha-csv-only"]
    assert result["fam_new"]["members"] == ["sha-new"]


def test_load_families_when_root_shape_is_invalid(tmp_path: Path) -> None:
    # Given a JSON value that is neither supported family shape.
    families_path = tmp_path / "families.json"
    families_path.write_text("42", encoding="utf-8")
    # When family metadata is loaded, then the error explains both valid shapes.
    with pytest.raises(build_gallery.GalleryInputError, match="array of family objects"):
        build_gallery.load_families(families_path, ())


def test_localization_map_contains_required_chinese_surface() -> None:
    # Given the report's user-facing localization contract.
    required = {
        "图片审计台",
        "本地图片库 · 只读审计（离线可用）",
        "图片总数",
        "共识 Z 中位",
        "待人工复核",
        "风险标记",
        "入队候选",
        "人工复核",
        "归档候选",
        "NSFW 复核",
        "身份复核",
        "评分分歧",
        "刷分嫌疑",
        "NSFW",
        "身份低分",
        "家族备选",
        "审计抽样",
        "Q-ReAlign",
        "指标说明",
        "清除筛选",
        "审查工作台",
        "审计表格",
        "人物分组",
        "未定",
        "仅看未定",
        "精选",
        "入队通过",
        "归档",
        "NSFW 确认",
        "身份存疑",
        "跳过",
        "动作日志",
        "仅看未审",
    }
    # When the localization map is inspected.
    localized = set(build_gallery.LOCALIZATION_MAP.values())
    # Then every required user-facing label is represented by a stable key.
    assert required <= localized


def test_read_scores_tolerates_optional_qrealign_and_extra_columns(tmp_path: Path) -> None:
    # Given an old-shaped CSV with an unrelated future column and no qrealign.
    old_path = tmp_path / "old.csv"
    old_columns = tuple(column for column in build_gallery.CSV_COLUMNS if column != "qrealign") + (
        "future_metric",
    )
    _write_scores_csv(old_path, old_columns)
    # When the old shape is parsed.
    old_rows = build_gallery.read_scores(old_path)
    # Then missing qrealign and extra columns are tolerated.
    assert old_rows[0].qrealign is None

    # Given the new-shaped CSV with qrealign after TOPIQ-NR.
    new_path = tmp_path / "new.csv"
    _write_scores_csv(new_path, build_gallery.CSV_COLUMNS, qrealign="0.875")
    # When the new shape is parsed.
    new_rows = build_gallery.read_scores(new_path)
    # Then the fourth scorer is parsed as a finite numeric value.
    assert new_rows[0].qrealign == 0.875


def test_unknown_flags_are_preserved_and_counted(tmp_path: Path) -> None:
    # Given a known audit flag alongside an unknown future flag.
    path = tmp_path / "scores.csv"
    _write_scores_csv(path, build_gallery.CSV_COLUMNS, flags="audit_sample|future_flag")
    # When the CSV is parsed and summarized.
    rows = build_gallery.read_scores(path)
    result = build_gallery.build_stats(rows)
    # Then both values survive parsing and do not crash statistics rendering.
    assert rows[0].flags == ("audit_sample", "future_flag")
    assert result["flag_counts"]["audit_sample"] == 1
    assert result["flag_counts"]["future_flag"] == 1


def test_payload_tracks_qrealign_column_presence(tmp_path: Path) -> None:
    # Given a row that can be represented by either the old or new CSV header.
    scores_path = tmp_path / "scores.csv"
    _write_scores_csv(scores_path, build_gallery.CSV_COLUMNS, qrealign="0.875")
    rows = tuple(build_gallery.read_scores(scores_path))
    # When payloads are built with explicit header shapes.
    legacy_columns = tuple(column for column in build_gallery.CSV_COLUMNS if column != "qrealign")
    legacy_payload = build_gallery.build_payload(tmp_path, rows, legacy_columns)
    new_payload = build_gallery.build_payload(tmp_path, rows, build_gallery.CSV_COLUMNS)
    # Then the browser can hide or show the optional column deterministically.
    assert "qrealign" not in legacy_payload["columns"]
    assert "qrealign" in new_payload["columns"]


def test_build_stats_reports_consensus_median() -> None:
    # Given three rows whose consensus values have a distinct median.
    row = build_gallery.ScoreRow(
        sha16="sha-one",
        abs_path="C:/one.png",
        path_rel="one.png",
        filename="one.png",
        width=32,
        height=32,
        filesize=100,
        phash="abcd",
        family_id="fam_0001",
        aes_v25=1.0,
        topiq_iaa=1.0,
        topiq_nr=1.0,
        nsfw_prob=0.0,
        identity_sim=1.0,
        confusable_margin=None,
        novelty=1.0,
        consensus_z=0.0,
        disagreement=0.0,
        gaming_delta=None,
        flags=(),
        proposed_tier="queue",
        thumb_rel="",
    )
    rows = (row, replace(row, sha16="sha-two", consensus_z=9.0), replace(row, sha16="sha-three", consensus_z=-2.0))
    # When corpus statistics are calculated.
    result = build_gallery.build_stats(rows)
    # Then the header metric is the population median, not the arithmetic mean.
    assert result["consensus_z_median"] == 0.0


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
    assert "new DecompressionStream(\"gzip\")" in html
    assert "requestAnimationFrame" in html
    assert "requestIdleCallback" in html
    assert 'loading="lazy"' in html
    assert "content-visibility:auto" in html
    assert "manual_decision" in html
    assert "previews/" in html
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
                    "cluster_groups": [
                        {"cluster_id": 4, "face_count": 1, "images": ["sha-two"]}
                    ],
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
