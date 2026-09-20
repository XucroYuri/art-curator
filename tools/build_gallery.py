#!/usr/bin/env python3
# noqa: SIZE_OK - the offline HTML/CSS/JS artifact is intentionally co-located with its generator.
"""Build a self-contained, offline Chinese image review studio."""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import html
import json
import math
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, TypedDict, assert_never


CSV_COLUMNS: Final[tuple[str, ...]] = (
    "sha16",
    "abs_path",
    "path_rel",
    "filename",
    "width",
    "height",
    "filesize",
    "phash",
    "family_id",
    "aes_v25",
    "topiq_iaa",
    "topiq_nr",
    "qrealign",
    "hpsv3_mu",
    "hpsv3_sigma",
    "nsfw_prob",
    "identity_sim",
    "confusable_margin",
    "novelty",
    "consensus_z",
    "disagreement",
    "gaming_delta",
    "flags",
    "proposed_tier",
    "thumb_rel",
)
TIERS: Final[tuple[str, ...]] = (
    "queue",
    "review",
    "archive_candidate",
    "route_nsfw",
    "route_identity",
)
FLAGS: Final[tuple[str, ...]] = (
    "uncertain",
    "gaming_suspect",
    "nsfw",
    "id_low",
    "near_dup_runnerup",
    "audit_sample",
)
DEFAULT_TITLE: Final[str] = "图片审计台"
DEFAULT_SUBTITLE: Final[str] = "本地图片库 · 只读审计（离线可用）"
PREFETCH_K: Final[int] = 6
PREFETCH_CONCURRENCY: Final[int] = 4
LOCALIZATION_MAP: Final[dict[str, str]] = {
    "title": DEFAULT_TITLE,
    "subtitle": DEFAULT_SUBTITLE,
    "eyebrow": "离线 · 只读 · 图片审查",
    "mode_studio": "审查工作台",
    "mode_table": "审计表格",
    "mode_grouping": "人物分组",
    "grouping_unassigned": "未定",
    "grouping_only_unassigned": "仅看未定",
    "stat_total": "图片总数",
    "stat_consensus": "共识 Z 中位",
    "stat_review": "待人工复核",
    "stat_risk": "风险标记",
    "tier_queue": "入队候选",
    "tier_review": "人工复核",
    "tier_archive_candidate": "归档候选",
    "tier_route_nsfw": "NSFW 复核",
    "tier_route_identity": "身份复核",
    "flag_uncertain": "评分分歧",
    "flag_gaming_suspect": "刷分嫌疑",
    "flag_nsfw": "NSFW",
    "flag_id_low": "身份低分",
    "flag_near_dup_runnerup": "家族备选",
    "flag_audit_sample": "审计抽样",
    "column_qrealign": "Q-ReAlign",
    "column_hpsv3_mu": "HPSv3 μ",
    "column_hpsv3_sigma": "HPSv3 σ",
    "search": "搜索：文件名、SHA、家族",
    "metric_legend": "指标说明",
    "clear_filters": "清除筛选",
    "action_select": "精选",
    "action_queue": "入队通过",
    "action_archive": "归档",
    "action_nsfw": "NSFW 确认",
    "action_identity": "身份存疑",
    "action_skip": "跳过",
    "manual_decision": "人工决定",
    "proposed_tier": "处置提案",
    "journal": "动作日志",
    "show_nsfw": "显示 NSFW",
    "only_unreviewed": "仅看未审",
}
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


class GalleryInputError(Exception):
    """Raised when a pipeline artifact does not satisfy the frozen contract."""


class RowPayload(TypedDict):
    sha16: str
    abs_path: str
    path_rel: str
    filename: str
    width: int | None
    height: int | None
    filesize: int | None
    phash: str
    family_id: str
    aes_v25: float | None
    topiq_iaa: float | None
    topiq_nr: float | None
    qrealign: float | None
    hpsv3_mu: float | None
    hpsv3_sigma: float | None
    nsfw_prob: float | None
    identity_sim: float | None
    confusable_margin: float | None
    novelty: float | None
    consensus_z: float | None
    disagreement: float | None
    gaming_delta: float | None
    flags: list[str]
    proposed_tier: str
    thumb_rel: str


class FamilyPayload(TypedDict):
    members: list[str]
    champion: str
    runner_up: str


class StatsPayload(TypedDict):
    total: int
    tier_counts: dict[str, int]
    flag_counts: dict[str, int]
    consensus_z_median: float | None
    average_consensus_z: float | None
    pass_rate: float


class GalleryPayload(TypedDict):
    rows: list[RowPayload]
    columns: list[str]
    families: dict[str, FamilyPayload]
    stats: StatsPayload
    source: str
    identities: dict[str, JsonValue] | None
    characters: JsonValue | None
    grouping: dict[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class ScoreRow:
    """Parsed and normalized representation of one scores.csv record."""

    sha16: str
    abs_path: str
    path_rel: str
    filename: str
    width: int | None
    height: int | None
    filesize: int | None
    phash: str
    family_id: str
    aes_v25: float | None
    topiq_iaa: float | None
    topiq_nr: float | None
    qrealign: float | None = field(default=None, kw_only=True)
    hpsv3_mu: float | None = field(default=None, kw_only=True)
    hpsv3_sigma: float | None = field(default=None, kw_only=True)
    nsfw_prob: float | None
    identity_sim: float | None
    confusable_margin: float | None
    novelty: float | None
    consensus_z: float | None
    disagreement: float | None
    gaming_delta: float | None
    flags: tuple[str, ...]
    proposed_tier: str
    thumb_rel: str

    def to_payload(self) -> RowPayload:
        """Convert the typed row to the legacy JSON-compatible shape."""
        return {
            "sha16": self.sha16,
            "abs_path": self.abs_path,
            "path_rel": self.path_rel,
            "filename": self.filename,
            "width": self.width,
            "height": self.height,
            "filesize": self.filesize,
            "phash": self.phash,
            "family_id": self.family_id,
            "aes_v25": self.aes_v25,
            "topiq_iaa": self.topiq_iaa,
            "topiq_nr": self.topiq_nr,
            "qrealign": self.qrealign,
            "hpsv3_mu": self.hpsv3_mu,
            "hpsv3_sigma": self.hpsv3_sigma,
            "nsfw_prob": self.nsfw_prob,
            "identity_sim": self.identity_sim,
            "confusable_margin": self.confusable_margin,
            "novelty": self.novelty,
            "consensus_z": self.consensus_z,
            "disagreement": self.disagreement,
            "gaming_delta": self.gaming_delta,
            "flags": list(self.flags),
            "proposed_tier": self.proposed_tier,
            "thumb_rel": self.thumb_rel,
        }


@dataclass(frozen=True, slots=True)
class PayloadMetrics:
    """Sizes emitted by the compact payload encoder."""

    legacy_json_bytes: int
    columnar_json_bytes: int
    gzip_bytes: int
    base64_bytes: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class GalleryBuild:
    """Build output and measurements used by the CLI report."""

    path: Path
    rows: int
    html_bytes: int
    metrics: PayloadMetrics


def _cell(raw: Mapping[str, str | None], field: str) -> str:
    value = raw.get(field)
    return "" if value is None else value.strip()


def _parse_integer(value: str, field: str, line_number: int) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise GalleryInputError(f"scores.csv line {line_number}: {field} must be an integer") from exc


def _parse_float(value: str, field: str, line_number: int) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise GalleryInputError(f"scores.csv line {line_number}: {field} must be numeric") from exc
    if not math.isfinite(parsed):
        raise GalleryInputError(f"scores.csv line {line_number}: {field} must be finite")
    return parsed


def _parse_flags(value: str, line_number: int) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(dict.fromkeys(part.strip() for part in value.split("|") if part.strip()))


def _parse_row(raw: Mapping[str, str | None], line_number: int) -> ScoreRow:
    tier = _cell(raw, "proposed_tier") or "review"
    if tier not in TIERS:
        raise GalleryInputError(f"scores.csv line {line_number}: unsupported proposed_tier {tier!r}")
    return ScoreRow(
        sha16=_cell(raw, "sha16"),
        abs_path=_cell(raw, "abs_path"),
        path_rel=_cell(raw, "path_rel"),
        filename=_cell(raw, "filename"),
        width=_parse_integer(_cell(raw, "width"), "width", line_number),
        height=_parse_integer(_cell(raw, "height"), "height", line_number),
        filesize=_parse_integer(_cell(raw, "filesize"), "filesize", line_number),
        phash=_cell(raw, "phash"),
        family_id=_cell(raw, "family_id") or "unassigned",
        aes_v25=_parse_float(_cell(raw, "aes_v25"), "aes_v25", line_number),
        topiq_iaa=_parse_float(_cell(raw, "topiq_iaa"), "topiq_iaa", line_number),
        topiq_nr=_parse_float(_cell(raw, "topiq_nr"), "topiq_nr", line_number),
        nsfw_prob=_parse_float(_cell(raw, "nsfw_prob"), "nsfw_prob", line_number),
        identity_sim=_parse_float(_cell(raw, "identity_sim"), "identity_sim", line_number),
        confusable_margin=_parse_float(
            _cell(raw, "confusable_margin"), "confusable_margin", line_number
        ),
        novelty=_parse_float(_cell(raw, "novelty"), "novelty", line_number),
        consensus_z=_parse_float(_cell(raw, "consensus_z"), "consensus_z", line_number),
        disagreement=_parse_float(_cell(raw, "disagreement"), "disagreement", line_number),
        gaming_delta=_parse_float(_cell(raw, "gaming_delta"), "gaming_delta", line_number),
        flags=_parse_flags(_cell(raw, "flags"), line_number),
        proposed_tier=tier,
        thumb_rel=_cell(raw, "thumb_rel").replace("\\", "/"),
        qrealign=_parse_float(_cell(raw, "qrealign"), "qrealign", line_number),
        hpsv3_mu=_parse_float(_cell(raw, "hpsv3_mu"), "hpsv3_mu", line_number),
        hpsv3_sigma=_parse_float(_cell(raw, "hpsv3_sigma"), "hpsv3_sigma", line_number),
    )


@dataclass(frozen=True, slots=True)
class ScoresDocument:
    """Parsed rows plus the input header used to gate optional UI columns."""

    rows: tuple[ScoreRow, ...]
    columns: tuple[str, ...]


def _read_scores_document(scores_path: Path) -> ScoresDocument:
    """Read rows while tolerating missing and additional CSV columns."""
    try:
        stream = scores_path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise GalleryInputError(f"cannot open {scores_path}: {exc}") from exc
    with stream:
        reader = csv.DictReader(stream)
        actual_columns = tuple(reader.fieldnames or ())
        rows = tuple(_parse_row(raw, line_number) for line_number, raw in enumerate(reader, start=2))
    return ScoresDocument(rows=rows, columns=actual_columns)


def read_scores(scores_path: Path) -> list[ScoreRow]:
    """Read and parse scores.csv while preserving the list-based public API."""
    return list(_read_scores_document(scores_path).rows)


def derive_families(rows: Sequence[ScoreRow]) -> dict[str, FamilyPayload]:
    """Derive family membership when the optional families.json is absent."""
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row.family_id, []).append(row.sha16)
    return {
        family_id: {"members": members, "champion": "", "runner_up": ""}
        for family_id, members in grouped.items()
    }


def _family_string_list(value: JsonValue, field: str, family_id: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise GalleryInputError(f"families.json family {family_id!r}: {field} must be a string list")
    return list(value)


def _family_string_or_empty(value: JsonValue, field: str, family_id: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise GalleryInputError(
            f"families.json family {family_id!r}: {field} must be a string or null"
        )
    return value


def _normalize_family_entry(family_id: str, value: JsonValue) -> FamilyPayload:
    if not isinstance(value, dict):
        raise GalleryInputError(
            f"families.json family {family_id!r}: entry must be an object with members"
        )
    return {
        "members": _family_string_list(value.get("members", []), "members", family_id),
        "champion": _family_string_or_empty(value.get("champion"), "champion", family_id),
        "runner_up": _family_string_or_empty(value.get("runner_up"), "runner_up", family_id),
    }


def _family_entries(raw: JsonValue) -> list[tuple[str, FamilyPayload]]:
    if isinstance(raw, list):
        entries: list[tuple[str, FamilyPayload]] = []
        for index, value in enumerate(raw):
            if not isinstance(value, dict):
                raise GalleryInputError(
                    f"families.json array entry {index} must be an object with a string family_id"
                )
            family_id = value.get("family_id")
            if not isinstance(family_id, str) or not family_id:
                raise GalleryInputError(
                    f"families.json array entry {index} must contain a non-empty string family_id"
                )
            entries.append((family_id, _normalize_family_entry(family_id, value)))
        return entries
    if isinstance(raw, dict):
        entries = []
        for family_id, value in raw.items():
            if not isinstance(family_id, str):
                raise GalleryInputError("families.json object keys must be family_id strings")
            entries.append((family_id, _normalize_family_entry(family_id, value)))
        return entries
    raise GalleryInputError(
        "families.json must contain either an array of family objects with family_id "
        "or an object keyed by family_id"
    )


def load_families(families_path: Path, rows: Sequence[ScoreRow]) -> dict[str, FamilyPayload]:
    """Load optional family metadata and fill gaps from CSV membership."""
    families = derive_families(rows)
    if not families_path.exists():
        return families
    try:
        raw: JsonValue = json.loads(families_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GalleryInputError(f"cannot read {families_path}: {exc}") from exc
    for family_id, family in _family_entries(raw):
        families[family_id] = family
    return families


def _json_object(value: JsonValue | None) -> dict[str, JsonValue]:
    """Copy a JSON object or provide an empty object for tolerant defaults."""
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: JsonValue | None) -> list[JsonValue]:
    """Copy a JSON list or provide an empty list for tolerant defaults."""
    return list(value) if isinstance(value, list) else []


def _identity_string(value: JsonValue | None, default: str = "") -> str:
    """Read a string field from an optional identity record."""
    return value if isinstance(value, str) else default


def _identity_nullable_string(value: JsonValue | None) -> str | None:
    """Read a nullable string field from an optional identity record."""
    return value if isinstance(value, str) or value is None else None


def _identity_integer(value: JsonValue | None, default: int = 0) -> int:
    """Read a finite integer-like identity field with a safe default."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    parsed = float(value)
    return int(parsed) if math.isfinite(parsed) else default


def _identity_float(value: JsonValue | None, default: float | None = None) -> float | None:
    """Read a finite nullable numeric identity field."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    parsed = float(value)
    return parsed if math.isfinite(parsed) else default


def _identity_string_list(value: JsonValue | None) -> list[str]:
    """Keep only string IDs in a producer-provided identity list."""
    return [item for item in _json_list(value) if isinstance(item, str)]


def _identity_bbox(value: JsonValue | None) -> list[JsonValue]:
    """Normalize a face box to four finite numbers without dropping extra fields."""
    values = _json_list(value)
    bbox: list[JsonValue] = []
    for item in values[:4]:
        parsed = _identity_float(item, 0.0)
        bbox.append(parsed if parsed is not None else 0.0)
    return bbox + [0.0] * (4 - len(bbox))


def _normalize_identity_images(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    """Normalize image-to-face links while preserving producer extensions."""
    images: list[dict[str, JsonValue]] = []
    for raw in _json_list(value):
        entry = _json_object(raw)
        entry["sha16"] = _identity_string(entry.get("sha16"))
        entry["path_rel"] = _identity_string(entry.get("path_rel")).replace("\\", "/")
        entry["faces"] = _identity_string_list(entry.get("faces"))
        images.append(entry)
    return images


def _normalize_identity_faces(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    """Normalize face records while preserving unknown detector fields."""
    faces: list[dict[str, JsonValue]] = []
    for raw in _json_list(value):
        entry = _json_object(raw)
        entry["face_id"] = _identity_string(entry.get("face_id"))
        entry["image_sha16"] = _identity_string(entry.get("image_sha16"))
        entry["bbox"] = _identity_bbox(entry.get("bbox"))
        entry["det_score"] = _identity_float(entry.get("det_score"))
        entry["crop_rel"] = _identity_string(entry.get("crop_rel")).replace("\\", "/")
        cluster_id = entry.get("cluster_id")
        if not (
            cluster_id is None
            or (isinstance(cluster_id, (int, str)) and not isinstance(cluster_id, bool))
        ):
            cluster_id = None
        entry["cluster_id"] = cluster_id
        entry["cluster_prob"] = _identity_float(entry.get("cluster_prob"))
        entry["is_outlier"] = entry.get("is_outlier") if isinstance(entry.get("is_outlier"), bool) else False
        entry["cluster_margin"] = _identity_float(entry.get("cluster_margin"))
        faces.append(entry)
    return faces


def _normalize_identity_clusters(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    """Normalize cluster records while preserving unknown clustering metadata."""
    clusters: list[dict[str, JsonValue]] = []
    for raw in _json_list(value):
        entry = _json_object(raw)
        cluster_id = entry.get("cluster_id")
        if not (
            cluster_id is None
            or (isinstance(cluster_id, (int, str)) and not isinstance(cluster_id, bool))
        ):
            cluster_id = None
        entry["cluster_id"] = cluster_id
        entry["size"] = _identity_integer(entry.get("size"))
        entry["centroid_face_id"] = _identity_string(entry.get("centroid_face_id"))
        entry["confidence"] = _identity_float(entry.get("confidence"))
        entry["suggested_character"] = _identity_nullable_string(entry.get("suggested_character"))
        entry["confirmed_character"] = _identity_nullable_string(entry.get("confirmed_character"))
        entry["representative_faces"] = _identity_string_list(entry.get("representative_faces"))
        clusters.append(entry)
    return clusters


def load_identities(identities_path: Path) -> dict[str, JsonValue] | None:
    """Load optional identity metadata with safe defaults and forward compatibility."""
    if not identities_path.exists():
        return None
    try:
        raw: JsonValue = json.loads(identities_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GalleryInputError(f"cannot read {identities_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GalleryInputError(f"invalid JSON in {identities_path}: {exc}") from exc
    if not isinstance(raw, dict):
        return None
    document = dict(raw)
    detector = _json_object(document.get("detector"))
    detector["name"] = _identity_string(detector.get("name"))
    detector["model"] = _identity_string(detector.get("model"))
    detector["revision"] = _identity_string(detector.get("revision"))
    detector["min_face_px"] = _identity_integer(detector.get("min_face_px"))
    embedder = _json_object(document.get("embedder"))
    embedder["name"] = _identity_string(embedder.get("name"))
    embedder["model"] = _identity_string(embedder.get("model"))
    embedder["revision"] = _identity_string(embedder.get("revision"))
    clustering = _json_object(document.get("clustering"))
    clustering["algorithm"] = _identity_string(clustering.get("algorithm"))
    clustering["min_cluster_size"] = _identity_integer(clustering.get("min_cluster_size"))
    images = _normalize_identity_images(document.get("images"))
    faces = _normalize_identity_faces(document.get("faces"))
    clusters = _normalize_identity_clusters(document.get("clusters"))
    document["version"] = _identity_integer(document.get("version"), 1)
    document["detector"] = detector
    document["embedder"] = embedder
    document["clustering"] = clustering
    document["images"] = images
    document["faces"] = faces
    document["clusters"] = clusters
    document["image_count"] = _identity_integer(document.get("image_count"), len(images))
    document["face_count"] = _identity_integer(document.get("face_count"), len(faces))
    document["cluster_count"] = _identity_integer(document.get("cluster_count"), len(clusters))
    return document


def load_characters(characters_path: Path) -> JsonValue | None:
    """Load optional read-only character names without constraining producer shape."""
    if not characters_path.exists():
        return None
    try:
        return json.loads(characters_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GalleryInputError(f"cannot read {characters_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GalleryInputError(f"invalid JSON in {characters_path}: {exc}") from exc


def _read_grouping_csv(path: Path) -> list[dict[str, str]]:
    """Read a grouping CSV while retaining future columns as strings."""
    if not path.exists():
        return []
    try:
        stream = path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise GalleryInputError(f"cannot read {path}: {exc}") from exc
    with stream:
        reader = csv.DictReader(stream)
        return [
            {key: _cell(raw, key) for key in (reader.fieldnames or ()) if key}
            for raw in reader
        ]


def _normalize_grouping_entries(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    """Normalize character entries without dropping producer extensions."""
    entries: list[dict[str, JsonValue]] = []
    for raw in _json_list(value):
        entry = _json_object(raw)
        entry["character"] = _identity_string(entry.get("character"), "未命名")
        entry["image_count"] = _identity_integer(entry.get("image_count"))
        entry["face_count"] = _identity_integer(entry.get("face_count"))
        entry["images"] = _identity_string_list(entry.get("images"))
        entry["mean_sim"] = _identity_float(entry.get("mean_sim"))
        entry["min_margin"] = _identity_float(entry.get("min_margin"))
        entries.append(entry)
    return entries


def _normalize_grouping_csv_rows(
    rows: Sequence[dict[str, str]], kind: str,
) -> list[dict[str, JsonValue]]:
    """Normalize one grouping CSV family and preserve unknown columns."""
    normalized: list[dict[str, JsonValue]] = []
    for raw in rows:
        entry: dict[str, JsonValue] = dict(raw)
        entry["sha16"] = raw.get("sha16", "")
        entry["filename"] = raw.get("filename", "")
        match kind:
            case "image":
                roles = raw.get("characters", "")
                entry["characters"] = list(dict.fromkeys(role for role in roles.split("|") if role))
            case "character":
                entry["character"] = raw.get("character", "")
                entry["face_id"] = raw.get("face_id", "")
                entry["sim"] = _grouping_csv_float(raw.get("sim", ""))
                entry["margin"] = _grouping_csv_float(raw.get("margin", ""))
                entry["decision"] = raw.get("decision", "")
            case unreachable:
                assert_never(unreachable)
        normalized.append(entry)
    return normalized


def _grouping_csv_float(value: str) -> float | None:
    """Parse an optional grouping CSV number without making the view fail closed."""
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def load_character_grouping(out_dir: Path) -> dict[str, JsonValue] | None:
    """Load optional grouping JSON and CSV exports with tolerant defaults."""
    grouping_path = out_dir / "character-groups.json"
    if not grouping_path.exists():
        return None
    try:
        raw: JsonValue = json.loads(grouping_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GalleryInputError(f"cannot read {grouping_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GalleryInputError(f"invalid JSON in {grouping_path}: {exc}") from exc
    if not isinstance(raw, dict):
        return None
    document = dict(raw)
    thresholds = _json_object(document.get("thresholds"))
    thresholds["min_sim"] = _identity_float(thresholds.get("min_sim"))
    thresholds["min_margin"] = _identity_float(thresholds.get("min_margin"))
    abstained = _json_object(document.get("abstained"))
    cluster_groups: list[dict[str, JsonValue]] = []
    for raw_group in _json_list(abstained.get("cluster_groups")):
        group = _json_object(raw_group)
        cluster_id = group.get("cluster_id")
        if not (
            cluster_id is None
            or (isinstance(cluster_id, (int, str)) and not isinstance(cluster_id, bool))
        ):
            cluster_id = None
        group["cluster_id"] = cluster_id
        group["face_count"] = _identity_integer(group.get("face_count"))
        group["images"] = _identity_string_list(group.get("images"))
        cluster_groups.append(group)
    abstained["face_count"] = _identity_integer(abstained.get("face_count"))
    abstained["cluster_groups"] = cluster_groups
    anchors_path = out_dir / "anchors.json"
    anchors = load_characters(anchors_path) if anchors_path.exists() else None
    document["version"] = _identity_integer(document.get("version"), 1)
    document["provenance"] = _json_object(document.get("provenance"))
    document["thresholds"] = thresholds
    document["characters"] = _normalize_grouping_entries(document.get("characters"))
    document["abstained"] = abstained
    document["by_image"] = _normalize_grouping_csv_rows(
        _read_grouping_csv(out_dir / "character-groups-by-image.csv"), "image"
    )
    document["by_character"] = _normalize_grouping_csv_rows(
        _read_grouping_csv(out_dir / "character-groups-by-character.csv"), "character"
    )
    document["anchors"] = anchors
    return document


def build_stats(rows: Sequence[ScoreRow]) -> StatsPayload:
    """Calculate the compact corpus summary shown in the report header."""
    tier_counts = {tier: 0 for tier in TIERS}
    flag_counts = {flag: 0 for flag in FLAGS}
    consensus_values: list[float] = []
    for row in rows:
        tier_counts[row.proposed_tier] += 1
        for flag in row.flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
        if row.consensus_z is not None:
            consensus_values.append(row.consensus_z)
    archive_count = tier_counts["archive_candidate"]
    return {
        "total": len(rows),
        "tier_counts": tier_counts,
        "flag_counts": flag_counts,
        "consensus_z_median": statistics.median(consensus_values) if consensus_values else None,
        "average_consensus_z": statistics.fmean(consensus_values) if consensus_values else None,
        "pass_rate": archive_count / len(rows) if rows else 0.0,
    }


def build_payload(
    out_dir: Path,
    rows: Sequence[ScoreRow],
    columns: Sequence[str] | None = None,
) -> GalleryPayload:
    """Build the compatibility payload before compact columnar encoding."""
    available_columns = tuple(columns) if columns is not None else tuple(
        column for column in CSV_COLUMNS if column != "qrealign" or any(row.qrealign is not None for row in rows)
    )
    return {
        "rows": [row.to_payload() for row in rows],
        "columns": list(available_columns),
        "families": load_families(out_dir / "families.json", rows),
        "stats": build_stats(rows),
        "source": str((out_dir / "scores.csv").resolve()),
        "identities": load_identities(out_dir / "identities.json"),
        "characters": load_characters(out_dir / "characters.json"),
        "grouping": load_character_grouping(out_dir),
    }


def safe_json(payload: GalleryPayload) -> str:
    """Serialize the compatibility payload safely for tests and comparisons."""
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


COMPACT_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("s", "sha16"),
    ("a", "abs_path"),
    ("p", "path_rel"),
    ("n", "filename"),
    ("w", "width"),
    ("h", "height"),
    ("b", "filesize"),
    ("x", "phash"),
    ("f", "family_id"),
    ("ae", "aes_v25"),
    ("ia", "topiq_iaa"),
    ("nr", "topiq_nr"),
    ("qr", "qrealign"),
    ("hm", "hpsv3_mu"),
    ("hs", "hpsv3_sigma"),
    ("ns", "nsfw_prob"),
    ("id", "identity_sim"),
    ("cm", "confusable_margin"),
    ("nv", "novelty"),
    ("cz", "consensus_z"),
    ("dg", "disagreement"),
    ("gd", "gaming_delta"),
    ("fl", "flags"),
    ("pt", "proposed_tier"),
    ("th", "thumb_rel"),
)


def _grouping_extras(entry: Mapping[str, JsonValue], known: Sequence[str]) -> dict[str, JsonValue]:
    """Keep producer fields that the compact browser view does not interpret."""
    known_fields = set(known)
    return {key: value for key, value in entry.items() if key not in known_fields}


def compact_grouping(grouping: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Encode grouping artifacts with short keys while preserving extensions."""
    compact_characters: list[JsonValue] = []
    for raw in _json_list(grouping.get("characters")):
        entry = _json_object(raw)
        compact_characters.append(
            [
                entry.get("character", "未命名"),
                entry.get("image_count", 0),
                entry.get("face_count", 0),
                entry.get("images", []),
                entry.get("mean_sim"),
                entry.get("min_margin"),
                _grouping_extras(
                    entry,
                    ("character", "image_count", "face_count", "images", "mean_sim", "min_margin"),
                ),
            ]
        )
    compact_images: list[JsonValue] = []
    for raw in _json_list(grouping.get("by_image")):
        entry = _json_object(raw)
        compact_images.append(
            [
                entry.get("sha16", ""),
                entry.get("filename", ""),
                entry.get("characters", []),
                _grouping_extras(entry, ("sha16", "filename", "characters")),
            ]
        )
    compact_faces: list[JsonValue] = []
    for raw in _json_list(grouping.get("by_character")):
        entry = _json_object(raw)
        compact_faces.append(
            [
                entry.get("character", ""),
                entry.get("sha16", ""),
                entry.get("filename", ""),
                entry.get("face_id", ""),
                entry.get("sim"),
                entry.get("margin"),
                entry.get("decision", ""),
                _grouping_extras(
                    entry,
                    ("character", "sha16", "filename", "face_id", "sim", "margin", "decision"),
                ),
            ]
        )
    unknown_root = _grouping_extras(
        grouping,
        ("version", "provenance", "thresholds", "characters", "abstained", "by_image", "by_character", "anchors"),
    )
    return {
        "v": grouping.get("version", 1),
        "p": grouping.get("provenance", {}),
        "t": grouping.get("thresholds", {}),
        "c": compact_characters,
        "a": grouping.get("abstained", {}),
        "i": compact_images,
        "f": compact_faces,
        "h": grouping.get("anchors"),
        "u": unknown_root,
    }


def compact_payload(payload: GalleryPayload) -> dict[str, JsonValue]:
    """Convert row objects into a gzip-friendly short-key columnar payload."""
    row_maps = [dict(row) for row in payload["rows"]]
    columns: dict[str, JsonValue] = {}
    available = set(payload["columns"])
    flag_values = list(FLAGS)
    for row in row_maps:
        for flag in row["flags"]:
            if flag not in flag_values:
                flag_values.append(flag)
    flag_index = {flag: index for index, flag in enumerate(flag_values)}
    tier_index = {tier: index for index, tier in enumerate(TIERS)}
    for short_key, field_name in COMPACT_COLUMNS:
        if field_name == "qrealign" and "qrealign" not in available:
            continue
        if field_name == "flags":
            columns[short_key] = [
                [flag_index[flag] for flag in row["flags"]]
                for row in row_maps
            ]
        elif field_name == "proposed_tier":
            columns[short_key] = [tier_index[row["proposed_tier"]] for row in row_maps]
        else:
            columns[short_key] = [row[field_name] for row in row_maps]
    output_root = Path(payload["source"]).parent
    preview_available: list[bool] = []
    thumb_available: list[bool] = []
    for row in row_maps:
        sha16 = str(row["sha16"])
        thumb_rel = str(row["thumb_rel"] or f"thumbs/{sha16}.jpg").replace("\\", "/")
        preview_path = output_root / "previews" / f"{sha16}.jpg"
        preview_available.append(preview_path.is_file())
        thumb_available.append(bool(thumb_rel) and (output_root / thumb_rel).is_file())
    columns["pr"] = preview_available
    columns["tb"] = thumb_available
    compact_families: dict[str, JsonValue] = {
        family_id: [family["members"], family["champion"], family["runner_up"]]
        for family_id, family in payload["families"].items()
    }
    stats = payload["stats"]
    compact_stats: dict[str, JsonValue] = {
        "n": stats["total"],
        "t": stats["tier_counts"],
        "f": stats["flag_counts"],
        "m": stats["consensus_z_median"],
        "a": stats["average_consensus_z"],
        "p": stats["pass_rate"],
    }
    grouping = payload["grouping"]
    return {
        "v": 4,
        "n": len(row_maps),
        "k": PREFETCH_K,
        "d": list(payload["columns"]),
        "c": columns,
        "g": flag_values,
        "l": list(TIERS),
        "f": compact_families,
        "z": compact_stats,
        "o": payload["source"],
        "y": payload["identities"],
        "q": payload["characters"],
        "r": compact_grouping(grouping) if grouping is not None else None,
    }


def encode_payload(payload: GalleryPayload) -> tuple[str, PayloadMetrics]:
    """Compress the compact payload and return base64 text plus measurements."""
    compact = compact_payload(payload)
    fingerprint_basis = json.dumps(
        compact, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    fingerprint = hashlib.sha256(fingerprint_basis).hexdigest()[:20]
    compact["i"] = fingerprint
    raw_bytes = json.dumps(
        compact, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    compressed = gzip.compress(raw_bytes, compresslevel=9, mtime=0)
    encoded = base64.b64encode(compressed).decode("ascii")
    metrics = PayloadMetrics(
        legacy_json_bytes=len(safe_json(payload).encode("utf-8")),
        columnar_json_bytes=len(raw_bytes),
        gzip_bytes=len(compressed),
        base64_bytes=len(encoded),
        fingerprint=fingerprint,
    )
    return encoded, metrics


def _resolve_branding(title: str | None, subtitle: str | None) -> tuple[str, str]:
    """Apply generic branding defaults while honoring explicit CLI overrides."""
    clean_title = (title or DEFAULT_TITLE).strip() or DEFAULT_TITLE
    clean_subtitle = (subtitle or DEFAULT_SUBTITLE).strip() or DEFAULT_SUBTITLE
    return clean_title, clean_subtitle


def write_gallery(
    out_dir: Path,
    payload: GalleryPayload,
    title: str | None = None,
    subtitle: str | None = None,
) -> Path:
    """Write one compressed, self-contained report next to scores.csv."""
    resolved_title, resolved_subtitle = _resolve_branding(title, subtitle)
    encoded, metrics = encode_payload(payload)
    destination = out_dir / "gallery.html"
    template = (
        HTML_TEMPLATE.replace("__REPORT_TITLE__", html.escape(resolved_title, quote=True))
        .replace("__REPORT_SUBTITLE__", html.escape(resolved_subtitle, quote=True))
        .replace("__PAYLOAD_B64__", encoded, 1)
        .replace("__LEGACY_BYTES__", str(metrics.legacy_json_bytes))
        .replace("__COLUMNAR_BYTES__", str(metrics.columnar_json_bytes))
        .replace("__GZIP_BYTES__", str(metrics.gzip_bytes))
        .replace("__BASE64_BYTES__", str(metrics.base64_bytes))
        .replace("__FINGERPRINT__", metrics.fingerprint)
    )
    destination.write_text(template, encoding="utf-8")
    return destination


def build_gallery_with_metrics(
    out_dir: Path,
    title: str | None = None,
    subtitle: str | None = None,
) -> GalleryBuild:
    """Generate a report and retain payload measurements for the CLI."""
    if not out_dir.is_dir():
        raise GalleryInputError(f"output directory does not exist: {out_dir}")
    document = _read_scores_document(out_dir / "scores.csv")
    payload = build_payload(out_dir, document.rows, document.columns)
    output = write_gallery(out_dir, payload, title, subtitle)
    _, metrics = encode_payload(payload)
    return GalleryBuild(output, len(document.rows), output.stat().st_size, metrics)


def build_gallery(
    out_dir: Path,
    title: str | None = None,
    subtitle: str | None = None,
) -> Path:
    """Generate gallery.html for one pipeline output directory."""
    return build_gallery_with_metrics(out_dir, title, subtitle).path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the offline report command-line surface."""
    parser = argparse.ArgumentParser(description="Build an offline Chinese image review studio.")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Pipeline output directory containing scores.csv and optional families.json",
    )
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Report title shown in the studio")
    parser.add_argument(
        "--subtitle",
        default=DEFAULT_SUBTITLE,
        help="Report subtitle shown below the title",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and report contract and payload errors without a traceback."""
    args = parse_args(argv)
    try:
        result = build_gallery_with_metrics(args.out, args.title, args.subtitle)
    except (GalleryInputError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    metrics = result.metrics
    reduction = 1 - metrics.base64_bytes / max(metrics.legacy_json_bytes, 1)
    print(f"Wrote {result.path}")
    print(
        "rows={rows} html={html}B payload legacy={legacy}B columnar={columnar}B "
        "gzip={gzip}B base64={base64}B reduction={reduction:.1%} fingerprint={fingerprint}".format(
            rows=result.rows,
            html=result.html_bytes,
            legacy=metrics.legacy_json_bytes,
            columnar=metrics.columnar_json_bytes,
            gzip=metrics.gzip_bytes,
            base64=metrics.base64_bytes,
            reduction=reduction,
            fingerprint=metrics.fingerprint,
        )
    )
    return 0


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="离线图片审查工作台">
<link rel="icon" type="image/gif" href="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">
<title>__REPORT_TITLE__</title>
<style>
:where([hidden]){display:none!important}
:root{
  --color-canvas:#07080a;--color-canvas-deep:#050608;--color-surface:#101111;--color-surface-elevated:#17191b;--color-surface-active:#202326;
  --color-text-primary:#f4f5f5;--color-text-secondary:#c4c7c9;--color-text-muted:#878c91;--color-border:#25292c;--color-border-subtle:rgba(255,255,255,.07);
  --color-info:#55b3ff;--color-info-soft:rgba(85,179,255,.14);--color-danger:#ff6363;--color-danger-soft:rgba(255,99,99,.14);--color-warning:#ffbc33;--color-warning-soft:rgba(255,188,51,.14);--color-success:#5fc992;--color-success-soft:rgba(95,201,146,.14);--color-character:#b8a1ff;--color-character-soft:rgba(184,161,255,.16);--color-focus:#8bd0ff;--color-scrim:rgba(5,6,8,.76);--color-canvas-glow:rgba(85,179,255,.07);
  --font-sans:system-ui,"Microsoft YaHei","PingFang SC","Noto Sans CJK SC","Segoe UI",sans-serif;--font-mono:ui-monospace,"Cascadia Mono","SFMono-Regular",Consolas,monospace;
  --space-1:4px;--space-2:8px;--space-3:12px;--space-4:16px;--space-5:20px;--space-6:24px;--space-8:32px;--space-10:40px;
  --radius-micro:3px;--radius-control:6px;--radius-panel:10px;--border-width:1px;--drawer-width:420px;--character-drawer-width:460px;--table-min-width:1540px;--table-row-height:88px;
  --shadow-ring:0 0 0 1px #1b1c1e,0 0 0 1px inset #07080a;--shadow-float:0 20px 60px rgba(0,0,0,.5),0 0 0 1px #25292c,0 1px 0 rgba(255,255,255,.08) inset;
  --motion-micro:120ms;--motion-standard:200ms;--ease-standard:cubic-bezier(.16,1,.3,1);--z-header:20;--z-drawer:50;--z-modal:60;
}
*{box-sizing:border-box}html,body{width:100%;height:100%;min-width:320px;overflow:hidden}html{background:var(--color-canvas);color:var(--color-text-primary);font-family:var(--font-sans);font-synthesis:none;text-rendering:optimizeLegibility}body{margin:0;background:radial-gradient(circle at 12% 0%,var(--color-canvas-glow),transparent 34%),linear-gradient(180deg,var(--color-canvas) 0%,var(--color-canvas-deep) 100%);font-size:14px;font-weight:500;letter-spacing:.01em;line-height:1.45}button,input{font:inherit}button{color:inherit;cursor:pointer}button,a{-webkit-tap-highlight-color:transparent}button:focus-visible,a:focus-visible,input:focus-visible,[tabindex="0"]:focus-visible{outline:2px solid var(--color-focus);outline-offset:2px}.skip-link{position:fixed;z-index:100;inset-inline-start:var(--space-4);inset-block-start:var(--space-4);padding:var(--space-2) var(--space-3);border-radius:var(--radius-control);background:var(--color-info);color:var(--color-canvas);font-weight:700;transform:translateY(-160%);transition:transform var(--motion-micro) ease-out}.skip-link:focus{transform:translateY(0)}
.app-shell{height:100dvh;min-height:100dvh;min-width:0;display:grid;grid-template-rows:auto auto minmax(0,1fr);overflow:hidden;contain:layout paint}.topbar{position:relative;z-index:var(--z-header);min-width:0;display:flex;align-items:center;justify-content:space-between;gap:var(--space-6);padding:var(--space-4) var(--space-6) var(--space-3);border-block-end:var(--border-width) solid var(--color-border);background:rgba(7,8,10,.94);backdrop-filter:blur(12px)}.topbar:after{content:"";position:absolute;inset-inline-start:var(--space-6);inset-block-end:-1px;width:96px;height:1px;background:var(--color-info)}.brand{min-width:0;display:flex;align-items:flex-start;gap:var(--space-3)}.brand-mark{flex:none;width:12px;height:42px;border-radius:var(--radius-micro);background:linear-gradient(180deg,var(--color-info) 0 42%,var(--color-danger) 42% 56%,var(--color-warning) 56%);box-shadow:0 0 0 1px rgba(255,255,255,.08),0 1px 0 rgba(255,255,255,.22) inset}.brand-copy{min-width:0}.eyebrow{margin:0;color:var(--color-info);font:600 11px/1.3 var(--font-mono);letter-spacing:.08em}.brand h1{margin:var(--space-1) 0 0;font-size:clamp(23px,2.6vw,36px);font-weight:650;letter-spacing:-.04em;line-height:1.08;text-wrap:balance}.subtitle{max-width:46ch;margin:var(--space-2) 0 0;color:var(--color-text-muted);font-size:12px;line-height:1.35;overflow-wrap:anywhere}.run-meta{max-width:52ch;margin:var(--space-2) 0 0;color:var(--color-text-muted);font:600 10px/1.35 var(--font-mono);text-align:left;overflow-wrap:anywhere}.header-stats{min-width:0;display:grid;grid-template-columns:repeat(4,minmax(100px,1fr));gap:var(--space-2)}.header-stat{min-width:0;padding:var(--space-3);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:linear-gradient(145deg,rgba(255,255,255,.045),rgba(255,255,255,.012));box-shadow:var(--shadow-ring)}.header-stat[data-tone="info"]{border-color:rgba(85,179,255,.38)}.header-stat[data-tone="danger"]{border-color:rgba(255,99,99,.38)}.header-stat label{display:block;color:var(--color-text-muted);font-size:11px;line-height:1.25}.header-stat strong{display:block;margin-top:var(--space-1);font:650 19px/1.1 var(--font-mono);font-variant-numeric:tabular-nums;white-space:nowrap}.header-stat small{display:block;margin-top:var(--space-1);color:var(--color-text-muted);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.controls-row{position:relative;z-index:10;min-width:0;padding:var(--space-3) var(--space-6);border-block-end:var(--border-width) solid var(--color-border);background:rgba(16,17,17,.96);backdrop-filter:blur(12px);contain:layout}.controls-head{display:flex;align-items:end;gap:var(--space-3);min-width:0}.search-wrap{min-width:0;flex:1}.control-label,.filter-label{display:block;margin-bottom:var(--space-1);color:var(--color-text-muted);font-size:11px;font-weight:650}.search-input{width:100%;min-width:0;height:36px;padding:0 var(--space-3);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas);color:var(--color-text-primary);box-shadow:var(--shadow-ring)}.search-input::placeholder{color:var(--color-text-muted)}.search-input:hover{border-color:var(--color-text-muted)}.search-input:focus{border-color:var(--color-info);box-shadow:0 0 0 3px var(--color-info-soft),var(--shadow-ring)}.control-buttons,.toggle-cluster{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-2)}.control-button,.legend-button,.clear-button,.close-button,.copy-button,.original-link,.journal-button{min-height:34px;padding:0 var(--space-3);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface-elevated);color:var(--color-text-secondary);font-size:12px;font-weight:650;transition:transform var(--motion-micro) ease-out,background-color var(--motion-micro) ease-out,border-color var(--motion-micro) ease-out,color var(--motion-micro) ease-out}.control-button:hover,.legend-button:hover,.clear-button:hover,.close-button:hover,.copy-button:hover,.journal-button:hover{border-color:var(--color-info);background:var(--color-info-soft);color:var(--color-text-primary)}.control-button:active,.legend-button:active,.clear-button:active,.close-button:active,.copy-button:active,.journal-button:active{transform:translateY(1px)}.mode-switch{display:flex;gap:2px;padding:2px;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas)}.mode-button{min-height:32px;padding:0 var(--space-3);border:0;border-radius:var(--radius-micro);background:transparent;color:var(--color-text-muted);font-size:12px;font-weight:700}.mode-button[aria-pressed="true"]{background:var(--color-info-soft);color:var(--color-info);box-shadow:inset 0 -1px 0 var(--color-info)}.filter-line{display:flex;align-items:flex-end;gap:var(--space-3);min-width:0;margin-top:var(--space-3)}.tier-board{min-width:0;display:flex;flex:1 1 560px;flex-wrap:wrap;gap:var(--space-2)}.tier-card{min-width:112px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:0 var(--space-2);padding:var(--space-2) var(--space-3);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-text-secondary);text-align:left;transition:background-color var(--motion-micro) ease-out,border-color var(--motion-micro) ease-out,transform var(--motion-micro) ease-out}.tier-card:hover{border-color:var(--color-text-muted);background:var(--color-surface-active)}.tier-card:active{transform:translateY(1px)}.tier-card[aria-pressed="true"]{border-color:var(--color-info);background:var(--color-info-soft);color:var(--color-text-primary)}.tier-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;font-weight:700}.tier-card strong{font:650 15px/1 var(--font-mono);font-variant-numeric:tabular-nums}.tier-hint{grid-column:1/-1;margin-top:var(--space-1);color:var(--color-text-muted);font-size:9px}.flag-filter-wrap{min-width:0;flex:0 1 430px}.flag-filters{display:flex;flex-wrap:wrap;gap:var(--space-1)}.chip,.active-filter{min-height:28px;padding:0 var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:transparent;color:var(--color-text-muted);font-size:11px;font-weight:650;transition:background-color var(--motion-micro) ease-out,border-color var(--motion-micro) ease-out,color var(--motion-micro) ease-out}.chip:hover,.chip[aria-pressed="true"]{border-color:var(--color-info);background:var(--color-info-soft);color:var(--color-info)}.active-filter-row{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-1);min-height:28px;margin-top:var(--space-2);color:var(--color-text-muted);font-size:11px}.active-filter{border-color:rgba(85,179,255,.36);background:rgba(85,179,255,.08);color:var(--color-info)}.active-filter-title{color:var(--color-text-muted)}.toggle-label{display:inline-flex;align-items:center;gap:var(--space-1);min-height:28px;color:var(--color-text-secondary);font-size:11px;white-space:nowrap}.toggle-label input{accent-color:var(--color-info)}
.main-region{min-width:0;min-height:0;overflow:hidden}.studio-view,.table-view{height:100%;min-width:0;min-height:0}.studio-view{display:grid;grid-template-rows:minmax(0,1fr) auto;gap:var(--space-2);padding:var(--space-3) var(--space-6) var(--space-4)}.studio-body{min-width:0;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,360px);gap:var(--space-3)}.preview-column{min-width:0;min-height:0;display:grid;grid-template-rows:minmax(0,1fr) auto;gap:var(--space-2)}.preview-stage{position:relative;min-width:0;min-height:0;display:grid;place-items:center;overflow:hidden;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:radial-gradient(circle at 50% 36%,rgba(255,255,255,.045),transparent 48%),linear-gradient(145deg,#0d1012,#060708);box-shadow:var(--shadow-ring);contain:strict}.preview-stage:before{content:"";position:absolute;inset:var(--space-4);border:1px solid rgba(255,255,255,.045);border-radius:var(--radius-control);pointer-events:none}.preview-canvas{position:relative;z-index:1;display:grid;place-items:center;width:100%;height:100%;overflow:hidden;touch-action:none}.studio-image{max-width:calc(100% - var(--space-8));max-height:calc(100% - var(--space-8));object-fit:contain;user-select:none;opacity:1;filter:none;transition:opacity var(--motion-standard) var(--ease-standard),filter var(--motion-standard) ease-out;will-change:transform}.studio-image.is-private{filter:blur(28px) brightness(.62) saturate(.6)}.preview-canvas.is-zoomed .studio-image{max-width:none;max-height:none;cursor:grab}.preview-canvas.is-zoomed .studio-image:active{cursor:grabbing}.preview-placeholder{display:grid;place-items:center;min-width:min(260px,70%);min-height:140px;padding:var(--space-6);border:1px dashed var(--color-border);border-radius:var(--radius-control);color:var(--color-text-muted);font:650 12px/1.4 var(--font-mono);text-align:center}.stage-loading{position:absolute;z-index:3;inset-block-end:var(--space-4);inset-inline-start:50%;padding:var(--space-1) var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:rgba(7,8,10,.82);color:var(--color-text-muted);font-size:10px;transform:translateX(-50%)}.stage-topline,.stage-controls{position:absolute;z-index:4;display:flex;align-items:center;gap:var(--space-2)}.stage-topline{inset-block-start:var(--space-4);inset-inline:var(--space-4);justify-content:space-between;pointer-events:none}.stage-topline>*{pointer-events:auto}.stage-controls{inset-block-start:var(--space-4);inset-inline-end:var(--space-4)}.stage-label{min-width:0;max-width:52%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--color-text-secondary);font:600 11px/1.2 var(--font-mono)}.stage-index,.zoom-button,.fullscreen-button{min-height:28px;padding:0 var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:rgba(7,8,10,.82);color:var(--color-text-secondary);font-size:10px;font-weight:700}.stage-index{font-family:var(--font-mono);font-variant-numeric:tabular-nums}.zoom-button:hover,.fullscreen-button:hover{border-color:var(--color-info);color:var(--color-info)}.privacy-reveal{position:absolute;z-index:5;inset:50% auto auto 50%;min-height:38px;padding:0 var(--space-4);border:var(--border-width) solid rgba(255,99,99,.56);border-radius:var(--radius-control);background:var(--color-danger-soft);color:var(--color-text-primary);font-size:12px;font-weight:700;transform:translate(-50%,-50%);box-shadow:0 8px 30px rgba(0,0,0,.34)}.privacy-reveal:hover{background:rgba(255,99,99,.26)}.stage-badge-stack{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-1)}.manual-badge,.tier-badge,.badge{display:inline-flex;align-items:center;min-height:22px;padding:0 var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);font-size:10px;font-weight:700;white-space:nowrap}.manual-badge{border-color:rgba(95,201,146,.54);background:var(--color-success-soft);color:var(--color-success)}.tier-badge{border-color:rgba(85,179,255,.38);background:var(--color-info-soft);color:var(--color-info)}.action-belt{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-1);padding:var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:rgba(16,17,17,.95);box-shadow:var(--shadow-ring)}.action-button{min-height:38px;display:inline-flex;align-items:center;gap:var(--space-2);padding:0 var(--space-3);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-text-secondary);font-size:12px;font-weight:700;transition:transform var(--motion-micro) ease-out,background-color var(--motion-micro) ease-out,border-color var(--motion-micro) ease-out,color var(--motion-micro) ease-out}.action-button:hover{border-color:var(--color-info);background:var(--color-info-soft);color:var(--color-text-primary)}.action-button:active{transform:translateY(1px)}.action-button[aria-pressed="true"]{border-color:var(--color-success);background:var(--color-success-soft);color:var(--color-success)}.action-button[data-action="nsfw_confirm"]{border-color:rgba(255,99,99,.32)}.action-button[data-action="nsfw_confirm"]:hover{border-color:var(--color-danger);background:var(--color-danger-soft);color:var(--color-danger)}.action-button[data-action="identity_doubt"]{border-color:rgba(255,188,51,.32)}.action-button[data-action="identity_doubt"]:hover{border-color:var(--color-warning);background:var(--color-warning-soft);color:var(--color-warning)}.keycap{display:inline-grid;place-items:center;min-width:20px;height:20px;padding:0 4px;border:var(--border-width) solid currentColor;border-radius:var(--radius-micro);font:700 10px/1 var(--font-mono);opacity:.82}.belt-status{margin-inline-start:auto;color:var(--color-text-muted);font-size:10px;white-space:nowrap}.inspector{min-width:0;min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface);box-shadow:var(--shadow-ring)}.inspector-head{min-width:0;padding:var(--space-4);border-block-end:var(--border-width) solid var(--color-border);background:linear-gradient(145deg,rgba(255,255,255,.04),transparent)}.inspector-kicker{margin:0;color:var(--color-info);font:600 10px/1.2 var(--font-mono);letter-spacing:.06em}.inspector-head h2{margin:var(--space-1) 0 0;font-size:16px;line-height:1.25;overflow-wrap:anywhere}.inspector-head p{margin:var(--space-1) 0 0;color:var(--color-text-muted);font:600 10px/1.35 var(--font-mono);overflow-wrap:anywhere}.inspector-actions{display:flex;flex-wrap:wrap;gap:var(--space-1);margin-top:var(--space-3)}.inspector-scroll{min-height:0;overflow:auto;padding:var(--space-4);scrollbar-color:var(--color-border) var(--color-surface)}.inspector-section{margin:0 0 var(--space-4)}.inspector-section:last-child{margin-bottom:0}.inspector-section h3{margin:0 0 var(--space-2);color:var(--color-text-primary);font-size:12px;line-height:1.25}.score-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-1)}.score-card{min-width:0;padding:var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas-deep)}.score-card label{display:block;color:var(--color-text-muted);font-size:9px;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.score-card strong{display:block;margin-top:2px;color:var(--color-text-primary);font:650 13px/1.2 var(--font-mono);font-variant-numeric:tabular-nums}.score-card strong.empty{color:var(--color-text-muted)}.flag-list{display:flex;flex-wrap:wrap;gap:var(--space-1)}.badge{border-color:rgba(255,188,51,.34);background:var(--color-warning-soft);color:var(--color-warning)}.badge[data-flag="nsfw"]{border-color:rgba(255,99,99,.42);background:var(--color-danger-soft);color:var(--color-danger)}.badge[data-flag="none"]{border-color:var(--color-border);background:var(--color-surface-elevated);color:var(--color-text-muted)}.proposal-row{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-2)}.proposal-note,.journal-note{color:var(--color-text-muted);font-size:10px;line-height:1.45}.family-button{max-width:100%;min-height:30px;padding:0 var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface-elevated);color:var(--color-info);font:600 11px/1 var(--font-mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.family-button:hover{border-color:var(--color-info);background:var(--color-info-soft)}.raw-fields{margin:0;border-top:var(--border-width) solid var(--color-border)}.raw-field{display:grid;grid-template-columns:minmax(78px,.6fr) minmax(0,1fr);gap:var(--space-2);padding:var(--space-2) 0;border-bottom:var(--border-width) solid var(--color-border-subtle)}.raw-field dt{color:var(--color-text-muted);font-size:10px}.raw-field dd{min-width:0;margin:0;color:var(--color-text-secondary);font:600 10px/1.4 var(--font-mono);overflow-wrap:anywhere}.journal-list{display:grid;gap:var(--space-1);max-height:112px;overflow:auto}.journal-entry{display:flex;justify-content:space-between;gap:var(--space-2);padding:var(--space-1) 0;border-bottom:var(--border-width) solid var(--color-border-subtle);color:var(--color-text-muted);font-size:10px}.journal-entry strong{color:var(--color-text-secondary);font-weight:700}.filmstrip{min-width:0;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:var(--space-2);padding:var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:rgba(16,17,17,.95);box-shadow:var(--shadow-ring)}.filmstrip-title{min-width:72px;color:var(--color-text-muted);font-size:10px;font-weight:700}.filmstrip-list{min-width:0;display:flex;gap:var(--space-1);overflow:auto;scrollbar-color:var(--color-border) var(--color-surface);contain:content}.film-card{position:relative;flex:0 0 74px;height:58px;padding:0;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas-deep);overflow:hidden;transition:border-color var(--motion-micro) ease-out,transform var(--motion-micro) ease-out}.film-card:hover{border-color:var(--color-info);transform:translateY(-1px)}.film-card[aria-current="true"]{border-color:var(--color-info);box-shadow:inset 0 -2px 0 var(--color-info)}.film-card img{width:100%;height:100%;display:block;object-fit:cover;filter:none}.film-card.is-private img{filter:blur(12px) brightness(.55)}.film-placeholder{display:grid;place-items:center;width:100%;height:100%;color:var(--color-text-muted);font:600 9px/1 var(--font-mono)}.film-decision{position:absolute;inset-block-end:2px;inset-inline-start:2px;max-width:calc(100% - 4px);padding:2px 4px;border-radius:var(--radius-micro);background:rgba(5,6,8,.86);color:var(--color-success);font-size:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.film-count{flex:none;color:var(--color-info);font:650 11px/1 var(--font-mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.table-view{display:grid;grid-template-rows:minmax(0,1fr) auto;gap:var(--space-2);padding:var(--space-3) var(--space-6) var(--space-4)}.table-region{min-width:0;min-height:0;display:flex;flex-direction:column;overflow:hidden;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface);box-shadow:var(--shadow-ring)}.table-toolbar{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3);min-width:0;padding:var(--space-3) var(--space-4);border-block-end:var(--border-width) solid var(--color-border)}.table-heading{min-width:0}.table-heading h2{margin:0;font-size:16px;line-height:1.2}.table-heading p{margin:var(--space-1) 0 0;color:var(--color-text-muted);font-size:10px}.visible-count{flex:none;color:var(--color-info);font:650 11px/1.2 var(--font-mono);font-variant-numeric:tabular-nums}.table-frame{position:relative;min-width:0;min-height:0;flex:1;overflow:hidden}.table-scroll{width:100%;height:100%;overflow:auto;overscroll-behavior:contain;scrollbar-color:var(--color-border) var(--color-canvas-deep);contain:strict}.score-table{width:100%;min-width:var(--table-min-width);border-collapse:separate;border-spacing:0;font-size:11px;table-layout:fixed}.score-table caption{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.score-table th{position:sticky;top:0;z-index:3;height:44px;padding:var(--space-2) var(--space-3);border-block-end:var(--border-width) solid var(--color-border);background:var(--color-surface-elevated);color:var(--color-text-muted);font-size:10px;font-weight:650;text-align:start;white-space:nowrap}.score-table th.is-active{background:var(--color-info-soft);color:var(--color-info)}.sort-button{display:inline-flex;align-items:center;gap:var(--space-1);padding:var(--space-1) 0;border:0;background:transparent;color:inherit;font-size:inherit;font-weight:inherit}.sort-indicator{color:var(--color-info);font-family:var(--font-mono)}.score-table td{height:var(--table-row-height);padding:var(--space-2) var(--space-3);border-block-end:var(--border-width) solid var(--color-border-subtle);background:var(--color-surface);vertical-align:middle}.score-table tbody tr.data-row:hover td{background:var(--color-surface-active)}.score-table tbody tr.data-row.is-current td{box-shadow:inset 0 1px 0 rgba(85,179,255,.45),inset 0 -1px 0 rgba(85,179,255,.45)}.score-table .col-thumb{width:92px}.score-table .col-filename{width:250px}.score-table .col-family{width:150px}.score-table .col-score{width:112px}.score-table .col-flags{width:190px}.score-table .col-tier{width:125px}.table-thumb{position:relative;width:72px;height:68px;display:grid;place-items:center;padding:0;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas-deep);overflow:hidden}.table-thumb:hover{border-color:var(--color-info)}.table-thumb img{width:100%;height:100%;display:block;object-fit:cover;filter:none}.table-thumb.is-private img{filter:blur(11px) brightness(.55)}.table-placeholder{color:var(--color-text-muted);font:600 8px/1 var(--font-mono)}.filename-button,.table-family-button{display:block;max-width:100%;padding:0;border:0;background:transparent;color:var(--color-text-secondary);font-size:11px;font-weight:700;text-align:start;text-overflow:ellipsis;white-space:nowrap;overflow:hidden}.filename-button:hover,.table-family-button:hover{color:var(--color-info);text-decoration:underline;text-underline-offset:3px}.table-sha{display:block;margin-top:var(--space-1);color:var(--color-text-muted);font:600 9px/1.2 var(--font-mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.number{font:600 10px/1.2 var(--font-mono);font-variant-numeric:tabular-nums}.number.empty{color:var(--color-text-muted)}.table-badges{display:flex;flex-wrap:wrap;gap:var(--space-1)}.table-badges .badge,.table-badges .tier-badge,.table-badges .manual-badge{font-size:9px;min-height:20px}.virtual-spacer td{height:0;padding:0;border:0;background:transparent}.empty-state{display:grid;place-items:center;min-height:120px;padding:var(--space-6);color:var(--color-text-muted);font-size:12px;text-align:center}.spotlights{min-width:0;min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--space-2)}.spotlight{min-width:0;max-height:190px;overflow:hidden;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface);box-shadow:var(--shadow-ring);content-visibility:auto;contain-intrinsic-size:190px}.spotlight summary{display:flex;align-items:center;justify-content:space-between;gap:var(--space-2);padding:var(--space-3);cursor:pointer;color:var(--color-text-primary);font-size:12px;font-weight:650;list-style:none}.spotlight summary::-webkit-details-marker{display:none}.spotlight summary:after{content:"＋";color:var(--color-info);font:600 15px/1 var(--font-mono)}.spotlight[open] summary:after{content:"－"}.section-kicker{color:var(--color-info);font:600 9px/1.2 var(--font-mono);white-space:nowrap}.spotlight-list{display:grid;gap:var(--space-1);max-height:134px;overflow:auto;padding:0 var(--space-3) var(--space-3)}.spotlight-item{min-width:0;padding-top:var(--space-1);border-top:var(--border-width) solid var(--color-border-subtle)}.spotlight-head{display:flex;align-items:center;justify-content:space-between;gap:var(--space-2)}.jump-button{min-width:0;padding:0;border:0;background:transparent;color:var(--color-text-secondary);font-size:10px;font-weight:650;text-align:start;text-overflow:ellipsis;white-space:nowrap;overflow:hidden}.jump-button:hover{color:var(--color-info);text-decoration:underline;text-underline-offset:3px}.spotlight-value{flex:none;color:var(--color-warning);font:600 9px/1.2 var(--font-mono)}.mini-bars{display:grid;gap:var(--space-1);margin-top:var(--space-1)}.mini-bar{display:grid;grid-template-columns:28px minmax(0,1fr) 40px;align-items:center;gap:var(--space-1);color:var(--color-text-muted);font:600 8px/1 var(--font-mono)}.bar-track{height:3px;overflow:hidden;border-radius:999px;background:var(--color-border)}.bar-fill{display:block;height:100%;border-radius:inherit;background:var(--color-info)}.bar-fill.iaa{background:var(--color-success)}.bar-fill.nr{background:var(--color-warning)}
.family-panel{position:fixed;z-index:var(--z-drawer);inset-block:0;inset-inline-end:0;width:min(var(--drawer-width),100vw);display:flex;flex-direction:column;min-width:0;overflow:hidden;border-inline-start:var(--border-width) solid var(--color-border);background:var(--color-surface-elevated);box-shadow:var(--shadow-float);transform:translateX(100%);transition:transform var(--motion-standard) var(--ease-standard)}.family-panel.is-open{transform:translateX(0)}.drawer-backdrop,.modal-backdrop{position:fixed;inset:0;background:var(--color-scrim);backdrop-filter:blur(4px)}.drawer-backdrop{z-index:calc(var(--z-drawer) - 1)}.panel-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);padding:var(--space-5);border-block-end:var(--border-width) solid var(--color-border)}.panel-kicker{margin:0;color:var(--color-info);font:600 10px/1.2 var(--font-mono)}.panel-header h2{max-width:300px;margin:var(--space-1) 0 0;font-size:18px;line-height:1.2;overflow-wrap:anywhere}.panel-header p{margin:var(--space-2) 0 0;color:var(--color-text-muted);font-size:11px;line-height:1.45;overflow-wrap:anywhere}.drawer-scroll{min-height:0;flex:1;overflow:auto;padding:var(--space-5)}.drawer-preview{display:grid;place-items:center;min-height:220px;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas-deep);overflow:hidden}.drawer-preview img{max-width:100%;max-height:280px;object-fit:contain}.drawer-actions{display:flex;flex-wrap:wrap;gap:var(--space-2);margin-top:var(--space-3)}.original-link{display:inline-flex;align-items:center;justify-content:center;border-color:rgba(85,179,255,.55);background:var(--color-info-soft);color:var(--color-info);text-decoration:none}.original-link:hover{border-color:var(--color-info);color:var(--color-text-primary)}.copy-button{min-height:28px;padding-inline:var(--space-2);font-size:10px}.drawer-note{margin-top:var(--space-4);padding:var(--space-3);border-inline-start:3px solid var(--color-warning);background:var(--color-warning-soft);color:var(--color-text-secondary);font-size:10px;line-height:1.55}.family-strip{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-2)}.family-strip[data-state="singleton"]{grid-template-columns:1fr}.family-card{min-width:0;padding:var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface)}.family-card.champion{border-color:rgba(95,201,146,.5)}.family-card img{width:100%;height:110px;object-fit:cover;border-radius:var(--radius-micro)}.family-card strong{display:block;margin-top:var(--space-1);color:var(--color-text-secondary);font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mini-badge{display:inline-flex;margin-top:var(--space-1);color:var(--color-success);font:600 9px/1.2 var(--font-mono)}.detail-section{margin-top:var(--space-5)}.detail-section h3{margin:0 0 var(--space-2);font-size:12px}.detail-fields{margin:0;border-top:var(--border-width) solid var(--color-border)}.detail-field{display:grid;grid-template-columns:minmax(90px,.55fr) minmax(0,1fr);gap:var(--space-2);padding:var(--space-2) 0;border-bottom:var(--border-width) solid var(--color-border-subtle)}.detail-field dt{color:var(--color-text-muted);font-size:10px}.detail-field dd{min-width:0;margin:0;color:var(--color-text-secondary);font:600 10px/1.45 var(--font-mono);overflow-wrap:anywhere}.lightbox,.legend-modal,.help-modal,.journal-modal{position:fixed;z-index:var(--z-modal);inset:0;display:grid;place-items:center;padding:var(--space-6)}.lightbox[hidden],.legend-modal[hidden],.help-modal[hidden],.journal-modal[hidden]{display:none}.modal-backdrop{z-index:-1}.lightbox-panel,.legend-panel,.help-panel,.journal-panel{position:relative;width:min(820px,100%);max-height:min(90dvh,900px);overflow:auto;padding:var(--space-6);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface-elevated);box-shadow:var(--shadow-float)}.modal-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);margin-bottom:var(--space-4)}.modal-heading h2{margin:0;font-size:19px;line-height:1.2}.modal-heading p{margin:var(--space-1) 0 0;color:var(--color-text-muted);font-size:11px;overflow-wrap:anywhere}.lightbox-preview{min-height:320px;display:grid;place-items:center;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas-deep);overflow:hidden}.lightbox-preview img{max-width:100%;max-height:58dvh;object-fit:contain}.lightbox-actions{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-2);margin-top:var(--space-3)}.privacy-note{flex:1 1 240px;color:var(--color-text-muted);font-size:11px}.legend-intro{margin:0 0 var(--space-4);color:var(--color-text-secondary);font-size:12px;line-height:1.6}.legend-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-2) var(--space-4);margin:0}.legend-item{min-width:0;padding:var(--space-3);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface)}.legend-item dt{color:var(--color-text-primary);font-size:12px;font-weight:700}.legend-item dd{margin:var(--space-1) 0 0;color:var(--color-text-secondary);font-size:11px;line-height:1.55}.legend-direction{display:block;margin-top:var(--space-1);color:var(--color-info);font-size:10px}.shortcut-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-2);margin:0}.shortcut-item{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3);padding:var(--space-3);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface)}.shortcut-item span{color:var(--color-text-secondary);font-size:11px}.shortcut-item kbd{padding:var(--space-1) var(--space-2);border:var(--border-width) solid var(--color-info);border-radius:var(--radius-micro);color:var(--color-info);font:700 11px/1 var(--font-mono)}.journal-toolbar{display:flex;flex-wrap:wrap;gap:var(--space-2);margin-bottom:var(--space-3)}.journal-summary{margin:0 0 var(--space-3);color:var(--color-text-muted);font-size:11px}.journal-export{display:grid;gap:var(--space-1);max-height:260px;overflow:auto}.journal-export-row{display:grid;grid-template-columns:150px minmax(0,1fr) 150px;gap:var(--space-2);padding:var(--space-2);border-bottom:var(--border-width) solid var(--color-border-subtle);font:600 10px/1.3 var(--font-mono)}.fatal{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:var(--space-6);background:var(--color-canvas)}.fatal-card{width:min(640px,100%);padding:var(--space-6);border:var(--border-width) solid rgba(255,99,99,.48);border-radius:var(--radius-panel);background:var(--color-surface);box-shadow:var(--shadow-float)}.fatal-card h1{margin:0;color:var(--color-danger);font-size:20px}.fatal-card p{color:var(--color-text-secondary);font-size:13px;line-height:1.65}.fatal-card code{display:block;margin-top:var(--space-3);padding:var(--space-3);border-radius:var(--radius-control);background:var(--color-canvas-deep);color:var(--color-info);font:600 11px/1.5 var(--font-mono);overflow-wrap:anywhere}
 .face-overlay{position:absolute;z-index:2;inset:0;overflow:hidden;pointer-events:none}.face-overlay[hidden]{display:none}.face-box{position:absolute;display:block;min-width:18px;min-height:18px;padding:0;border:2px solid var(--color-character);border-radius:var(--radius-micro);background:var(--color-character-soft);box-shadow:0 0 0 1px rgba(7,8,10,.72),0 0 16px rgba(184,161,255,.16);pointer-events:auto;transition:background-color var(--motion-micro) ease-out,border-color var(--motion-micro) ease-out,opacity var(--motion-micro) ease-out}.face-box:hover,.face-box:focus-visible,.face-box.is-selected{border-color:var(--color-focus);background:var(--color-info-soft)}.face-box.is-uncertain{border-color:var(--color-warning);background:var(--color-warning-soft)}.face-box.is-outlier{border-style:dashed;border-color:var(--color-text-muted)}.face-box.is-private{opacity:.86}.face-label-chip{position:absolute;inset-block-start:-1px;inset-inline-start:-1px;max-width:calc(100% - var(--space-1));padding:2px var(--space-1);border-radius:var(--radius-micro);background:var(--color-character);color:var(--color-canvas);font-size:10px;font-weight:700;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;transform:translateY(-100%)}.face-tooltip{position:absolute;z-index:4;inset-inline-start:0;inset-block-start:calc(100% + var(--space-1));display:block;min-width:max-content;max-width:240px;padding:var(--space-1) var(--space-2);border:var(--border-width) solid var(--color-character);border-radius:var(--radius-control);background:var(--color-surface-elevated);color:var(--color-text-primary);font:600 10px/1.3 var(--font-mono);text-align:start;opacity:0;pointer-events:none;transform:translateY(-2px);transition:opacity var(--motion-micro) ease-out,transform var(--motion-micro) ease-out}.face-box:hover .face-tooltip,.face-box:focus-visible .face-tooltip{opacity:1;transform:none}.face-popover{position:fixed;z-index:var(--z-modal);width:min(360px,calc(100vw - var(--space-6)));padding:var(--space-4);border:var(--border-width) solid var(--color-character);border-radius:var(--radius-panel);background:var(--color-surface-elevated);box-shadow:var(--shadow-float);transform-origin:top left}.face-popover[hidden]{display:none}.face-popover h3{margin:0;font-size:14px;line-height:1.3}.face-popover-meta{margin:var(--space-1) 0 var(--space-3);color:var(--color-text-muted);font:600 10px/1.35 var(--font-mono)}.face-popover label{display:block;margin-block-end:var(--space-1);color:var(--color-text-muted);font-size:11px;font-weight:650}.face-popover select,.face-popover input,.cluster-name-input{width:100%;min-height:34px;padding:0 var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas);color:var(--color-text-primary)}.face-popover select:focus,.face-popover input:focus,.cluster-name-input:focus{border-color:var(--color-character);box-shadow:0 0 0 3px var(--color-character-soft)}.face-popover-actions,.character-toolbar,.cluster-actions{display:flex;flex-wrap:wrap;gap:var(--space-2);align-items:center}.face-popover-actions{margin-block-start:var(--space-3)}.face-popover-button,.character-action,.cluster-action{min-height:32px;padding:0 var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-text-secondary);font-size:11px;font-weight:650}.face-popover-button:hover,.character-action:hover,.cluster-action:hover{border-color:var(--color-character);background:var(--color-character-soft);color:var(--color-text-primary)}.face-popover-button[data-tone="danger"],.cluster-action[data-tone="danger"]{border-color:rgba(255,99,99,.55);color:var(--color-danger)}.face-popover-button[data-tone="warning"]{border-color:rgba(255,188,51,.55);color:var(--color-warning)}.face-popover-close{position:absolute;inset-block-start:var(--space-2);inset-inline-end:var(--space-2);min-height:28px}.face-popover-status{min-height:18px;margin:var(--space-2) 0 0;color:var(--color-success);font-size:11px}.character-panel{position:fixed;z-index:var(--z-drawer);inset-block:0;inset-inline-end:0;width:min(var(--character-drawer-width),100vw);display:flex;flex-direction:column;min-width:0;overflow:hidden;border-inline-start:var(--border-width) solid var(--color-character);background:var(--color-surface-elevated);box-shadow:var(--shadow-float);transform:translateX(100%);transition:transform var(--motion-standard) var(--ease-standard)}.character-panel.is-open{transform:translateX(0)}.character-panel[hidden]{display:none}.character-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);padding:var(--space-5);border-block-end:var(--border-width) solid var(--color-border)}.character-header h2{margin:var(--space-1) 0 0;font-size:18px;line-height:1.2}.character-header p{margin:var(--space-2) 0 0;color:var(--color-text-muted);font-size:11px;line-height:1.4}.character-scroll{min-height:0;flex:1;overflow:auto;padding:var(--space-4);overscroll-behavior:contain;contain:strict}.character-toolbar{padding:var(--space-3) var(--space-4);border-block-end:var(--border-width) solid var(--color-border);background:var(--color-surface)}.character-toggle{display:inline-flex;align-items:center;gap:var(--space-1);min-height:32px;color:var(--color-text-secondary);font-size:11px}.character-progress{margin-inline-start:auto;color:var(--color-character);font:650 11px/1.3 var(--font-mono);font-variant-numeric:tabular-nums}.character-queue-note{flex-basis:100%;margin:0;color:var(--color-text-muted);font-size:10px}.character-virtual{position:relative}.character-spacer{width:1px;opacity:0}.cluster-card{position:absolute;inset-inline:0;min-height:140px;padding:var(--space-3);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:linear-gradient(145deg,rgba(255,255,255,.04),rgba(255,255,255,.012));box-shadow:var(--shadow-ring);content-visibility:auto}.cluster-card.is-selected{border-color:var(--color-character);background:var(--color-character-soft)}.cluster-card h3{margin:0;font-size:13px;line-height:1.25;overflow-wrap:anywhere}.cluster-meta{display:flex;flex-wrap:wrap;gap:var(--space-2);margin-block-start:var(--space-1);color:var(--color-text-muted);font:600 10px/1.3 var(--font-mono)}.cluster-name{color:var(--color-character)}.cluster-suggested{color:var(--color-warning)}.cluster-crops{display:flex;gap:var(--space-2);min-height:58px;margin-block-start:var(--space-2);overflow:hidden}.cluster-crop{position:relative;flex:0 0 58px;width:58px;height:58px;padding:0;border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas-deep);overflow:hidden}.cluster-crop:hover,.cluster-crop:focus-visible,.cluster-crop.is-selected{border-color:var(--color-character)}.cluster-crop img{display:block;width:100%;height:100%;object-fit:cover}.cluster-crop img.is-private{filter:blur(12px) brightness(.65)}.cluster-crop-label{position:absolute;inset-inline:0;inset-block-end:0;padding:2px;background:rgba(5,6,8,.78);color:var(--color-text-primary);font-size:8px;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cluster-action{min-height:28px;font-size:10px}.cluster-actions{margin-block-start:var(--space-2)}.cluster-merge-target{min-height:28px;max-width:120px;padding:0 var(--space-1);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas);color:var(--color-text-secondary);font-size:10px}.character-empty{padding:var(--space-6) var(--space-3);border:1px dashed var(--color-border);border-radius:var(--radius-control);color:var(--color-text-muted);font-size:12px;text-align:center}.character-section{display:grid;gap:var(--space-2)}.character-summary{display:flex;align-items:center;justify-content:space-between;gap:var(--space-2);color:var(--color-text-muted);font-size:11px}.character-open-button{width:100%;min-height:34px;padding:0 var(--space-3);border:var(--border-width) solid rgba(184,161,255,.55);border-radius:var(--radius-control);background:var(--color-character-soft);color:var(--color-character);font-size:12px;font-weight:700}.character-open-button:hover{border-color:var(--color-character);color:var(--color-text-primary)}.name-modal{position:fixed;z-index:var(--z-modal);inset:0;display:grid;place-items:center;padding:var(--space-4)}.name-modal[hidden]{display:none}.name-panel{width:min(400px,100%);padding:var(--space-5);border:var(--border-width) solid var(--color-character);border-radius:var(--radius-panel);background:var(--color-surface-elevated);box-shadow:var(--shadow-float)}.name-panel h2{margin:0;font-size:18px}.name-panel p{margin:var(--space-2) 0 var(--space-4);color:var(--color-text-muted);font-size:11px}.name-panel label{display:block;margin-block-end:var(--space-1);color:var(--color-text-muted);font-size:11px;font-weight:650}.name-panel input{width:100%;min-height:36px;padding:0 var(--space-3);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-canvas);color:var(--color-text-primary)}.name-panel-actions{display:flex;justify-content:flex-end;gap:var(--space-2);margin-block-start:var(--space-4)}.import-input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.journal-import-status{margin:var(--space-2) 0 0;color:var(--color-success);font-size:11px}.face-popover .select-hint{margin:var(--space-1) 0 0;color:var(--color-text-muted);font-size:10px}
 @media(max-width:1199px){.header-stats{grid-template-columns:repeat(2,minmax(100px,1fr))}.studio-body{grid-template-columns:minmax(0,1fr) minmax(280px,320px)}.spotlights{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:900px){.topbar{align-items:flex-start}.header-stats{flex:0 0 280px}.studio-body{grid-template-columns:1fr;grid-template-rows:minmax(300px,1fr) minmax(220px,34%)}.inspector{min-height:220px}.table-view,.studio-view{padding-inline:var(--space-4)}}
@media(max-width:760px){.topbar{flex-direction:column;gap:var(--space-3);padding-inline:var(--space-4)}.topbar:after{inset-inline-start:var(--space-4)}.header-stats{width:100%;flex:0 1 auto}.controls-row{padding-inline:var(--space-4)}.controls-head{align-items:stretch;flex-direction:column}.control-buttons{justify-content:space-between}.filter-line{display:block}.flag-filter-wrap{margin-top:var(--space-3)}.studio-view,.table-view{padding-inline:var(--space-3)}.studio-body{grid-template-rows:minmax(260px,44dvh) minmax(230px,1fr)}.action-belt{flex-wrap:nowrap;overflow:auto}.action-button{flex:0 0 auto}.belt-status{display:none}.filmstrip{grid-template-columns:1fr auto}.filmstrip-title{display:none}.filmstrip-list{grid-column:1/-1;grid-row:1}.film-count{grid-column:2;grid-row:1;align-self:center}.spotlights{grid-template-columns:repeat(3,minmax(220px,1fr));overflow:auto}.table-view{grid-template-rows:minmax(0,1fr) 104px}.legend-list,.shortcut-list{grid-template-columns:1fr}.lightbox,.legend-modal,.help-modal,.journal-modal{padding:var(--space-2)}.lightbox-panel,.legend-panel,.help-panel,.journal-panel{padding:var(--space-4);max-height:94dvh}}
 @media(max-width:520px){.brand h1{font-size:26px}.subtitle{font-size:11px}.header-stat{padding:var(--space-2)}.header-stat strong{font-size:16px}.header-stat small{font-size:9px}.mode-button{padding-inline:var(--space-2)}.tier-card{min-width:calc(50% - 4px);flex:1 1 112px}.score-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.main-region{overflow:auto;overscroll-behavior:contain}.studio-view,.table-view{height:auto;min-height:calc(100dvh - 300px);overflow:visible}.studio-body{grid-template-rows:minmax(230px,39dvh) auto}.inspector{max-height:none;min-height:300px}.preview-stage:before{inset:var(--space-2)}.stage-topline{inset:var(--space-2)}.stage-controls{inset-block-start:var(--space-2);inset-inline-end:var(--space-2)}.table-toolbar{padding:var(--space-2) var(--space-3)}.table-heading p{display:none}.visible-count{font-size:10px}.table-view{padding-inline:var(--space-2)}.spotlights{grid-template-columns:repeat(3,minmax(220px,1fr))}.journal-export-row{grid-template-columns:1fr;gap:2px}.character-panel{width:100%}.face-popover{width:min(340px,calc(100vw - var(--space-4)));padding:var(--space-3)}}
 @media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition-duration:0ms!important;animation-duration:1ms!important;animation-iteration-count:1!important}.skip-link{transition:none}.family-panel,.character-panel{transform:none;opacity:0}.family-panel.is-open,.character-panel.is-open{opacity:1}.studio-image,.face-box,.face-tooltip{transition:none}.action-button:hover,.film-card:hover{transform:none}}
 .character-grouping-view{height:100%;min-width:0;min-height:0;overflow:hidden;padding:var(--space-4) var(--space-6);background:linear-gradient(145deg,rgba(184,161,255,.045),transparent 42%)}.grouping-scroll{height:100%;min-height:0;overflow:auto;overscroll-behavior:contain}.grouping-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-5);padding:var(--space-2) 0 var(--space-5)}.grouping-heading{min-width:0}.grouping-kicker{margin:0;color:var(--color-character);font:600 10px/1.2 var(--font-mono);letter-spacing:.08em}.grouping-heading h2{margin:var(--space-1) 0 0;font-size:clamp(20px,2.5vw,30px);line-height:1.1}.grouping-heading p{max-width:78ch;margin:var(--space-2) 0 0;color:var(--color-text-muted);font-size:12px;line-height:1.5;overflow-wrap:anywhere}.grouping-provenance{flex:0 1 420px;min-width:min(420px,100%);padding:var(--space-3);border:var(--border-width) solid rgba(184,161,255,.38);border-radius:var(--radius-panel);background:var(--color-character-soft);color:var(--color-text-secondary);font-size:11px;line-height:1.5}.grouping-provenance strong{display:block;color:var(--color-text-primary);font-size:12px}.grouping-provenance span{display:block;margin-top:var(--space-1);overflow-wrap:anywhere}.grouping-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:var(--space-3);padding-bottom:var(--space-5)}.grouping-card{min-width:0;padding:var(--space-4);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:linear-gradient(145deg,rgba(255,255,255,.045),rgba(255,255,255,.012));box-shadow:var(--shadow-ring);text-align:start;transition:transform var(--motion-micro) ease-out,background-color var(--motion-micro) ease-out,border-color var(--motion-micro) ease-out}.grouping-card:hover,.grouping-card:focus-visible{border-color:var(--color-character);background:var(--color-character-soft)}.grouping-card:active{transform:translateY(1px)}.grouping-card.is-selected{border-color:var(--color-focus);background:linear-gradient(145deg,var(--color-character-soft),var(--color-info-soft));box-shadow:0 0 0 2px var(--color-info-soft),var(--shadow-ring)}.grouping-card.is-unassigned{border-color:rgba(255,188,51,.45)}.grouping-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-2)}.grouping-card h3{min-width:0;margin:0;font-size:15px;line-height:1.25;overflow-wrap:anywhere}.grouping-card-count{flex:none;color:var(--color-character);font:700 22px/1 var(--font-mono);font-variant-numeric:tabular-nums}.grouping-card-meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-2);margin-top:var(--space-4)}.grouping-metric{min-width:0;padding:var(--space-2);border:var(--border-width) solid var(--color-border-subtle);border-radius:var(--radius-control);background:rgba(0,0,0,.12)}.grouping-metric small{display:block;color:var(--color-text-muted);font-size:10px}.grouping-metric strong{display:block;margin-top:2px;color:var(--color-text-primary);font:650 12px/1.25 var(--font-mono);overflow-wrap:anywhere}.grouping-card-note{display:block;margin-top:var(--space-3);color:var(--color-text-muted);font-size:11px;line-height:1.35}.grouping-actions{display:flex;flex-wrap:wrap;gap:var(--space-2);margin-top:var(--space-3)}.grouping-action{min-height:30px;padding:0 var(--space-2);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface-elevated);color:var(--color-text-secondary);font-size:11px;font-weight:650}.grouping-action:hover{border-color:var(--color-info);background:var(--color-info-soft);color:var(--color-text-primary)}.grouping-status{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3);padding:var(--space-3) var(--space-4);border:var(--border-width) solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface);box-shadow:var(--shadow-ring);color:var(--color-text-muted);font-size:11px}.grouping-status strong{color:var(--color-info);font-family:var(--font-mono)}.grouping-toggle{display:inline-flex;align-items:center;gap:var(--space-2);color:var(--color-text-secondary);font-weight:650;white-space:nowrap}.grouping-toggle input{accent-color:var(--color-character)}.character-badge-stack{position:absolute;z-index:3;inset-block-end:var(--space-3);inset-inline-start:var(--space-3);display:flex;flex-wrap:wrap;gap:var(--space-1);max-width:calc(100% - var(--space-6));pointer-events:none}.character-image-badge{display:inline-flex;max-width:220px;padding:var(--space-1) var(--space-2);border:var(--border-width) solid var(--color-character);border-radius:var(--radius-control);background:rgba(23,25,27,.92);color:var(--color-character);font-size:11px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.character-image-badge.is-unassigned{border-color:var(--color-warning);color:var(--color-warning)}@media(max-width:760px){.character-grouping-view{padding-inline:var(--space-3)}.grouping-header{display:block}.grouping-provenance{min-width:0;margin-top:var(--space-3)}.grouping-status{align-items:flex-start;flex-direction:column}}@media(prefers-reduced-motion:reduce){.grouping-card{transition:none}.grouping-card:active{transform:none}}
 </style>
</head>
<body>
<a class="skip-link" href="#studio-view">跳转到审查工作台</a>
<div class="app-shell" id="app-shell">
  <header class="topbar">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"></span>
      <div class="brand-copy">
        <p class="eyebrow">离线 · 只读 · 图片审查</p>
        <h1 id="brand-title">__REPORT_TITLE__</h1>
        <p class="subtitle" id="brand-subtitle">__REPORT_SUBTITLE__</p>
        <p class="run-meta" id="run-meta">正在读取压缩数据…</p>
      </div>
    </div>
    <div class="header-stats" aria-label="语料统计">
      <article class="header-stat" data-tone="info"><label>图片总数</label><strong id="stat-total">—</strong><small>已嵌入当前报告</small></article>
      <article class="header-stat"><label>共识 Z 中位</label><strong id="stat-consensus">—</strong><small>可用值的中位数</small></article>
      <article class="header-stat"><label>待人工复核</label><strong id="stat-review">—</strong><small>处置提案为人工复核</small></article>
      <article class="header-stat" data-tone="danger"><label>风险标记</label><strong id="stat-risk">—</strong><small>NSFW / 身份 / 刷分</small></article>
    </div>
  </header>
  <section class="controls-row" aria-label="筛选、模式和说明控制">
    <div class="controls-head">
      <div class="search-wrap"><label class="control-label" for="search-input">搜索：文件名、SHA、家族</label><input class="search-input" id="search-input" type="search" placeholder="搜索：文件名、SHA、家族" autocomplete="off" spellcheck="false"></div>
       <div class="control-buttons">
         <div class="mode-switch" role="tablist" aria-label="报告模式"><button class="mode-button" id="studio-mode" role="tab" aria-selected="true" aria-pressed="true" type="button">审查工作台</button><button class="mode-button" id="table-mode" role="tab" aria-selected="false" aria-pressed="false" type="button">审计表格</button><button class="mode-button" id="grouping-mode" role="tab" aria-selected="false" aria-pressed="false" type="button" hidden>人物分组</button></div>
        <button class="journal-button" id="journal-open" type="button">动作日志 <span id="journal-count">0</span></button><button class="legend-button" id="legend-open" type="button">指标说明</button><button class="control-button" id="help-open" type="button">快捷键 ?</button>
      </div>
    </div>
    <div class="filter-line">
      <div class="tier-board" id="tier-board" aria-label="处置筛选"></div>
      <div class="flag-filter-wrap"><span class="filter-label">标记筛选</span><div class="flag-filters" id="flag-filters" aria-label="标记筛选"></div></div>
      <div class="toggle-cluster"><label class="toggle-label"><input id="only-unreviewed" type="checkbox">仅看未审</label><label class="toggle-label"><input id="show-nsfw" type="checkbox">显示 NSFW</label></div>
    </div>
    <div class="active-filter-row" id="active-filters" aria-live="polite"></div>
  </section>
  <main class="main-region" id="main-region">
    <section class="studio-view" id="studio-view" aria-labelledby="studio-title">
      <div class="studio-body">
        <section class="preview-column" aria-labelledby="studio-title">
          <div class="preview-stage" id="preview-stage" tabindex="0" aria-label="大图审查区域">
            <div class="stage-topline"><span class="stage-label" id="stage-label">—</span><span class="stage-badge-stack"><span class="tier-badge" id="stage-tier">—</span><span class="manual-badge" id="stage-manual" hidden>—</span></span><span class="stage-index" id="stage-index">—</span></div>
            <div class="stage-controls"><button class="zoom-button" id="zoom-toggle" type="button" aria-label="切换适合窗口和 100% 缩放">适合窗口</button><button class="fullscreen-button" id="fullscreen-toggle" type="button">全屏</button></div>
             <div class="preview-canvas" id="preview-canvas"><img class="studio-image" id="studio-image" alt="" draggable="false"><div class="face-overlay" id="face-overlay" aria-label="当前图片的人脸框" hidden></div><div class="character-badge-stack" id="preview-character-badges" aria-label="当前图片的人物分组" hidden></div><div class="preview-placeholder" id="studio-placeholder" hidden>暂无可用预览</div><button class="privacy-reveal" id="privacy-reveal" type="button" hidden>点击显示 NSFW</button></div>
            <div class="stage-loading" id="stage-loading" hidden>正在读取预览…</div>
          </div>
          <div class="action-belt" id="action-belt" aria-label="人工决定动作"></div>
        </section>
        <aside class="inspector" aria-labelledby="studio-title">
          <div class="inspector-head"><p class="inspector-kicker">当前图片 · 人工复核</p><h2 id="studio-title">选择一张图片开始</h2><p id="studio-meta">—</p><div class="inspector-actions"><a class="original-link" id="original-link" href="#" target="_blank" rel="noreferrer">打开原图</a><button class="copy-button" id="copy-path" type="button">复制路径</button><button class="copy-button" id="copy-sha" type="button">复制 SHA</button></div></div>
          <div class="inspector-scroll">
            <section class="inspector-section"><h3>全部评分</h3><div class="score-grid" id="score-grid"></div></section>
            <section class="inspector-section"><h3>标记</h3><div class="flag-list" id="studio-flags"></div></section>
            <section class="inspector-section"><h3>处置状态</h3><div class="proposal-row"><span class="tier-badge" id="studio-proposal">—</span><span class="manual-badge" id="studio-decision" hidden>—</span></div><p class="proposal-note">处置提案来自管线；人工决定只保存在本地浏览器，不会改写 scores.csv。</p></section>
             <section class="inspector-section"><h3>家族</h3><button class="family-button" id="studio-family" type="button">—</button></section>
             <section class="inspector-section character-section" id="character-section" hidden><h3>人物层</h3><div class="character-summary"><span id="character-summary">—</span><span class="cluster-name" id="character-current-name"></span></div><button class="character-open-button" id="character-panel-open" type="button">打开人物面板</button></section>
            <section class="inspector-section"><h3>最近动作 <span class="journal-note" id="journal-note">按当前语料指纹保存</span></h3><div class="journal-list" id="journal-list"></div></section>
            <details class="inspector-section"><summary><strong>全部原始字段</strong></summary><dl class="raw-fields" id="raw-fields"></dl></details>
          </div>
        </aside>
      </div>
      <nav class="filmstrip" aria-label="当前筛选顺序的邻近图片"><span class="filmstrip-title">邻近图片</span><div class="filmstrip-list" id="filmstrip-list"></div><span class="film-count" id="studio-progress">0 / 0</span></nav>
    </section>
    <section class="table-view" id="table-view" aria-labelledby="table-title" hidden>
      <section class="table-region"><div class="table-toolbar"><div class="table-heading"><h2 id="table-title">审计表格</h2><p>固定表头 · 仅渲染可见行 · 图片使用懒加载和异步解码</p></div><p class="visible-count" id="visible-count" aria-live="polite">—</p></div><div class="table-frame"><div class="table-scroll" id="table-scroll"><table class="score-table" id="score-table"><caption>可排序的图片审计表格</caption><thead><tr><th class="col-thumb" scope="col">缩略图</th><th class="col-filename" data-sort-column="filename" scope="col"><button class="sort-button" data-sort="filename" type="button">文件名 <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-family" data-sort-column="family_id" scope="col"><button class="sort-button" data-sort="family_id" type="button">家族 <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="aes_v25" scope="col"><button class="sort-button" data-sort="aes_v25" type="button">美学 v2.5 <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="topiq_iaa" scope="col"><button class="sort-button" data-sort="topiq_iaa" type="button">TOPIQ-IAA <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="topiq_nr" scope="col"><button class="sort-button" data-sort="topiq_nr" type="button">TOPIQ-NR <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="qrealign" data-optional-column="qrealign" scope="col" hidden><button class="sort-button" data-sort="qrealign" type="button">Q-ReAlign <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="nsfw_prob" scope="col"><button class="sort-button" data-sort="nsfw_prob" type="button">NSFW 概率 <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="identity_sim" scope="col"><button class="sort-button" data-sort="identity_sim" type="button">身份相似度 <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="confusable_margin" scope="col"><button class="sort-button" data-sort="confusable_margin" type="button">混淆边际 <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="novelty" scope="col"><button class="sort-button" data-sort="novelty" type="button">新颖度 <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="consensus_z" scope="col"><button class="sort-button" data-sort="consensus_z" type="button">共识 Z <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="disagreement" scope="col"><button class="sort-button" data-sort="disagreement" type="button">分歧度 <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-score" data-sort-column="gaming_delta" scope="col"><button class="sort-button" data-sort="gaming_delta" type="button">刷分差值 <span class="sort-indicator" aria-hidden="true">↕</span></button></th><th class="col-flags" scope="col">标记</th><th class="col-tier" scope="col">处置</th></tr></thead><tbody id="score-rows"></tbody></table></div><div class="empty-state" id="empty-state" hidden>当前筛选没有匹配的图片</div></div></section>
      <aside class="spotlights" id="spotlights" aria-label="审计焦点"><details class="spotlight" open><summary>分歧焦点 <span class="section-kicker">前 12</span></summary><div class="spotlight-list" id="disagreement-list"></div></details><details class="spotlight" open><summary>刷分审计 <span class="section-kicker">差值 &gt; 0</span></summary><div class="spotlight-list" id="gaming-list"></div></details><details class="spotlight" open><summary>不确定队列 <span class="section-kicker">已标记</span></summary><div class="spotlight-list" id="uncertain-list"></div></details></aside>
     </section>
     <section class="character-grouping-view" id="character-grouping-view" aria-labelledby="grouping-title" hidden>
       <div class="grouping-scroll">
         <header class="grouping-header"><div class="grouping-heading"><p class="grouping-kicker">离线 · 像素检索提案</p><h2 id="grouping-title">人物分组</h2><p>按每张图片的角色集合筛选审计表与审阅台。未定包含空角色集合和放弃命名的人脸，可直接进入命名循环。</p></div><div class="grouping-provenance" id="grouping-provenance"><strong>实验性、未校准的检索建议</strong><span id="grouping-thresholds">阈值：min_sim — · min_margin —</span><span>文件夹名称 = 人工提供的标签；每张图的决策仅使用像素。不是身份认证或准确率证明。</span></div></header>
         <div class="grouping-cards" id="grouping-cards" aria-label="人物分组卡片"></div>
         <div class="grouping-status"><span id="grouping-status-text">—</span><label class="grouping-toggle"><input id="grouping-unassigned-toggle" type="checkbox">仅看未定</label><div class="grouping-actions"><button class="grouping-action" id="grouping-open-studio" type="button">回到审阅台</button><button class="grouping-action" id="grouping-start-naming" type="button">开始命名未定人脸</button></div></div>
       </div>
     </section>
   </main>
</div>

 <div class="drawer-backdrop" id="drawer-backdrop" hidden></div>
 <aside class="family-panel" id="family-panel" role="dialog" aria-modal="true" aria-labelledby="family-title" aria-hidden="true" hidden><div class="panel-header"><div><p class="panel-kicker" id="panel-kicker">详情抽屉</p><h2 id="family-title">详情</h2><p id="family-meta">—</p></div><button class="close-button" id="family-close" type="button" aria-label="关闭详情">关闭</button></div><div class="drawer-scroll" id="drawer-scroll"></div></aside>
 <div class="drawer-backdrop" id="character-backdrop" hidden></div>
 <aside class="character-panel" id="character-panel" role="dialog" aria-modal="true" aria-labelledby="character-title" aria-hidden="true" hidden><div class="character-header"><div><p class="panel-kicker">人物聚类 · 离线决定</p><h2 id="character-title">人物面板</h2><p>只记录本地人工决定，管线在 identity-apply 阶段执行。</p></div><button class="close-button" id="character-close" type="button" aria-label="关闭人物面板">关闭</button></div><div class="character-toolbar"><label class="character-toggle"><input id="uncertainty-mode" type="checkbox">待确认优先</label><span class="character-progress" id="character-progress">已命名 0 / 0</span><p class="character-queue-note" id="character-queue-note">按聚类置信度、边际、单成员和检测分数排序。</p></div><div class="character-scroll" id="character-scroll"><div class="character-virtual" id="character-virtual"></div></div></aside>
 <div class="face-popover" id="face-popover" role="dialog" aria-modal="false" aria-labelledby="face-popover-title" hidden><button class="face-popover-button face-popover-close" id="face-popover-close" type="button" aria-label="关闭人物命名">关闭</button><h3 id="face-popover-title">标注人脸</h3><p class="face-popover-meta" id="face-popover-meta">—</p><label for="face-character-select">已有人物</label><select id="face-character-select"><option value="">选择已有名字…</option></select><p class="select-hint">选择已有名字后确认，或在下方输入新名字。</p><label for="face-character-name">新建人物</label><input id="face-character-name" type="text" maxlength="80" autocomplete="off" placeholder="输入人物名称"><div class="face-popover-actions"><button class="face-popover-button" id="face-confirm" type="button">确认命名</button><button class="face-popover-button" id="face-new" type="button">新建人物</button><button class="face-popover-button" id="face-ignore" data-tone="danger" type="button">忽略此人脸</button><button class="face-popover-button" id="face-wrong-box" data-tone="warning" type="button">框选有误</button></div><p class="face-popover-status" id="face-popover-status" aria-live="polite"></p></div>
 <div class="name-modal" id="cluster-name-modal" role="dialog" aria-modal="true" aria-labelledby="cluster-name-title" hidden><div class="modal-backdrop" data-close="cluster-name-modal"></div><div class="name-panel"><h2 id="cluster-name-title">命名聚类</h2><p id="cluster-name-meta">—</p><label for="cluster-name-input">人物名称</label><input class="cluster-name-input" id="cluster-name-input" type="text" maxlength="80" autocomplete="off"><div class="name-panel-actions"><button class="close-button" id="cluster-name-close" type="button">取消</button><button class="character-open-button" id="cluster-name-confirm" type="button">保存名称</button></div></div></div>
<div class="lightbox" id="lightbox" role="dialog" aria-modal="true" aria-labelledby="lightbox-title" aria-hidden="true" hidden><div class="modal-backdrop" data-close="lightbox"></div><div class="lightbox-panel"><div class="modal-heading"><div><h2 id="lightbox-title">图片预览</h2><p id="lightbox-meta">—</p></div><button class="close-button" id="lightbox-close" type="button">关闭</button></div><div class="lightbox-preview" id="lightbox-preview"></div><div class="lightbox-actions"><span class="privacy-note" id="privacy-note"></span><a class="original-link" id="lightbox-original" href="#" target="_blank" rel="noreferrer">打开原图</a></div></div></div>
<div class="legend-modal" id="legend-modal" role="dialog" aria-modal="true" aria-labelledby="legend-title" aria-hidden="true" hidden><div class="modal-backdrop" data-close="legend"></div><div class="legend-panel"><div class="modal-heading"><div><h2 id="legend-title">指标说明</h2><p>读数来自冻结的离线管线，不会联网或修改文件</p></div><button class="close-button" id="legend-close" type="button">关闭</button></div><p class="legend-intro">方向只表示用于审计排序时的相对解释。所有处置都是未校准的建议；空值统一表示“未计算 / 不适用”。</p><dl class="legend-list">
<div class="legend-item"><dt>HPSv3 μ</dt><dd>HPSv3 原始偏好均值，参与所请求评分配置的共识计算；空值表示信号不可用。<span class="legend-direction">方向：越高通常越好 · 仅作相对参考，非校准质量概率</span></dd></div>
<div class="legend-item"><dt>HPSv3 σ</dt><dd>HPSv3 原始标准差（exp 输出通道），不是第六个评分器；空值不等于零。<span class="legend-direction">方向：越高表示模型原生不确定性越大 · 不是校准置信区间或安全保证</span></dd></div>
<div class="legend-item"><dt>美学 v2.5</dt><dd>美学预测模型的分数，用于比较画面审美信号。<span class="legend-direction">方向：越高通常越好 · 仅作相对排序</span></dd></div><div class="legend-item"><dt>TOPIQ-IAA</dt><dd>TOPIQ 图像质量信号之一，反映模型对画面质量的评估。<span class="legend-direction">方向：越高通常越好 · 非绝对质量保证</span></dd></div><div class="legend-item"><dt>TOPIQ-NR</dt><dd>无参考图像质量信号之一，不依赖成对参考图进行表格展示。<span class="legend-direction">方向：越高通常越好 · 受模型域偏差影响</span></dd></div><div class="legend-item" data-optional-column="qrealign" hidden><dt>Q-ReAlign</dt><dd>第 4 个评分器，AIGC 数据集训练的 MLLM 评分。<span class="legend-direction">方向：越高越好 · 未校准时仅作相对参考</span></dd></div><div class="legend-item"><dt>NSFW 概率</dt><dd>安全模型判断为 NSFW 的概率；达到 0.65 或处置为 NSFW 复核时默认模糊。<span class="legend-direction">方向：越低风险越小 · 不是安全认证</span></dd></div><div class="legend-item"><dt>身份相似度</dt><dd>与参考图的嵌入相似度，可能受服装、背景和构图影响。<span class="legend-direction">方向：越高越接近参考 · 不是身份验证</span></dd></div><div class="legend-item"><dt>身份混淆边际</dt><dd>身份相似度与其他参考最高相似度的差值；没有其他参考时为空。<span class="legend-direction">方向：越高分离越明显 · 空值为未计算 / 不适用</span></dd></div><div class="legend-item"><dt>新颖度</dt><dd>由与已发帖图像的相似度推导的相对新颖信号；管线没有为它发明阈值。<span class="legend-direction">方向：越高越不相似 · 仅供人工查看</span></dd></div><div class="legend-item"><dt>共识 Z</dt><dd>质量信号先在本语料内标准化，再汇总得到的总体相对位置。<span class="legend-direction">方向：越高相对共识越好 · 不是绝对分数</span></dd></div><div class="legend-item"><dt>分歧度</dt><dd>所请求质量信号的标准化分歧，含适用的 HPSv3 原生方差项；缺少必要信号时不可用。<span class="legend-direction">方向：越低越一致 · 高值进入人工关注，非校准置信度</span></dd></div><div class="legend-item"><dt>刷分差值</dt><dd>变体审计造成的美学分数最大下降，带符号；空值表示未抽审。<span class="legend-direction">方向：越低越稳定 · 正值越大越可疑</span></dd></div><div class="legend-item"><dt>审计抽样</dt><dd>随机低档审计样本，用于发现被漏掉的好图；不是缺陷标记。<span class="legend-direction">方向：无高低优劣 · 仅用于人工审计</span></dd></div><div class="legend-item"><dt>标记与处置</dt><dd>评分分歧、刷分嫌疑、NSFW、身份低分、家族备选、审计抽样和五类处置都是规则生成的人工复核提案。<span class="legend-direction">方向：无高低优劣 · 处置未校准</span></dd></div><div class="legend-item"><dt>空值（—）</dt><dd>原始 CSV 中没有可用数值，或该指标对当前语料不适用。<span class="legend-direction">解释：未计算 / 不适用 · 不应当作 0</span></dd></div></dl></div></div>
<div class="help-modal" id="help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title" aria-hidden="true" hidden><div class="modal-backdrop" data-close="help"></div><div class="help-panel"><div class="modal-heading"><div><h2 id="help-title">快捷键</h2><p>焦点不在输入框时可用</p></div><button class="close-button" id="help-close" type="button">关闭</button></div><div class="shortcut-list"><div class="shortcut-item"><span>上一张 / 下一张</span><kbd>← → / J K</kbd></div><div class="shortcut-item"><span>人工动作 1–6</span><kbd>1 2 3 4 5 6</kbd></div><div class="shortcut-item"><span>撤销当前图片动作</span><kbd>U</kbd></div><div class="shortcut-item"><span>适合窗口 / 100% 缩放</span><kbd>Space</kbd></div><div class="shortcut-item"><span>拖动 100% 预览</span><kbd>鼠标 / 触控</kbd></div><div class="shortcut-item"><span>切换全屏</span><kbd>F</kbd></div><div class="shortcut-item"><span>打开快捷键</span><kbd>?</kbd></div><div class="shortcut-item"><span>关闭面板 / 弹窗</span><kbd>Esc</kbd></div></div></div></div>
 <div class="journal-modal" id="journal-modal" role="dialog" aria-modal="true" aria-labelledby="journal-title" aria-hidden="true" hidden><div class="modal-backdrop" data-close="journal"></div><div class="journal-panel"><div class="modal-heading"><div><h2 id="journal-title">动作日志</h2><p>按当前语料指纹保存，作为未来人工标签的导出入口</p></div><button class="close-button" id="journal-close" type="button">关闭</button></div><div class="journal-toolbar"><button class="journal-button" id="export-json" type="button">导出 JSON</button><button class="journal-button" id="export-csv" type="button">导出 CSV</button><button class="journal-button" id="export-character-labels" type="button">导出人物标签</button><button class="journal-button" id="import-character-labels" type="button">导入人物标签</button><input class="import-input" id="character-labels-file" type="file" accept="application/json,.json" aria-label="导入人物标签 JSON 文件"><button class="journal-button" id="undo-character" type="button">撤销最近人物动作</button></div><p class="journal-summary" id="journal-summary">—</p><p class="journal-import-status" id="journal-import-status" aria-live="polite"></p><div class="journal-export" id="journal-export"></div></div></div>
<div class="fatal" id="fatal" hidden><div class="fatal-card"><h1>无法读取离线报告</h1><p id="fatal-message">当前浏览器不支持原生 gzip 解压，报告没有加载任何数据。</p><code>请使用最新 Chrome / Edge，或在本地只读服务器中打开 gallery.html。报告不需要网络、CDN 或框架。</code></div></div>

<script id="gallery-payload" type="application/octet-stream">__PAYLOAD_B64__</script>
<script>
(() => {
"use strict";
const encoded=document.getElementById("gallery-payload")?.textContent?.trim()||"";
const fatal=(message)=>{const node=document.getElementById("fatal");const text=document.getElementById("fatal-message");if(text)text.textContent=message;if(node)node.hidden=false;};
const decodePayload=async()=>{
  if(typeof globalThis.DecompressionStream!=="function")throw new Error("当前浏览器不支持原生 gzip 解压，请升级 Chrome / Edge。");
  const binary=atob(encoded);const bytes=Uint8Array.from(binary,(char)=>char.charCodeAt(0));
  const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return JSON.parse(await new Response(stream).text());
};
const start=performance.now();
decodePayload().then((compact)=>boot(compact,start)).catch((error)=>fatal(error instanceof Error?error.message:"报告数据解压失败，请重新生成 gallery.html。"));

 function boot(compact,decodeStart){
   const groupingUnassigned=(row)=>{const sha16=String(row?.sha16||"");const roles=groupingImageRoles.get(sha16)||[];const faceRows=groupingFacesByImage.get(sha16)||[];return !roles.some((role)=>groupingAssignedNames.has(role))||faceRows.some((face)=>face.decision!=="assigned");};const groupingMatches=(row)=>{if(!groupingEnabled||!state.groupCharacter)return true;const roles=groupingImageRoles.get(String(row?.sha16||""))||[];if(state.groupCharacter==="未定")return groupingUnassigned(row);return roles.includes(state.groupCharacter);};
   const finiteNumber=(value)=>{if(value===null||value===undefined||value==="")return null;const parsed=Number(value);return Number.isFinite(parsed)?parsed:null;};const compactGrouping=compact&&compact.r&&typeof compact.r==="object"?compact.r:null;const groupingEnabled=Boolean(compactGrouping);const groupingThresholds=compactGrouping?.t&&typeof compactGrouping.t==="object"?compactGrouping.t:{};const groupingCharacters=Array.isArray(compactGrouping?.c)?compactGrouping.c.map((entry)=>Array.isArray(entry)?{name:String(entry[0]||"未命名"),imageCount:Number(entry[1]||0),faceCount:Number(entry[2]||0),images:Array.isArray(entry[3])?entry[3].map(String):[],meanSim:finiteNumber(entry[4]),minMargin:finiteNumber(entry[5])}:null).filter(Boolean):[];const groupingImageRoles=new Map();const groupingFacesByImage=new Map();const groupingFaceById=new Map();const groupingAssignedNames=new Set(groupingCharacters.map((entry)=>entry.name));const addGroupingFace=(entry)=>{const face={character:String(entry?.[0]||""),sha16:String(entry?.[1]||""),filename:String(entry?.[2]||""),faceId:String(entry?.[3]||""),sim:finiteNumber(entry?.[4]),margin:finiteNumber(entry?.[5]),decision:String(entry?.[6]||"")};if(!face.sha16&&!face.faceId)return;if(face.faceId)groupingFaceById.set(face.faceId,face);const current=groupingFacesByImage.get(face.sha16)||[];current.push(face);groupingFacesByImage.set(face.sha16,current);if(face.decision==="assigned"&&face.character)groupingAssignedNames.add(face.character);};(Array.isArray(compactGrouping?.f)?compactGrouping.f:[]).forEach(addGroupingFace);(Array.isArray(compactGrouping?.i)?compactGrouping.i:[]).forEach((entry)=>{if(!Array.isArray(entry))return;const sha16=String(entry[0]||"");const roles=Array.isArray(entry[2])?entry[2].map(String).filter(Boolean):[];if(sha16)groupingImageRoles.set(sha16,[...new Set(roles)]);});groupingCharacters.forEach((entry)=>{entry.images.forEach((sha16)=>{const roles=groupingImageRoles.get(sha16)||[];if(!roles.includes(entry.name))roles.push(entry.name);groupingImageRoles.set(sha16,roles);});});
   const columnar=compact&&typeof compact==="object"?compact:{};const columns=columnar.c&&typeof columnar.c==="object"?columnar.c:{};const count=Number(columnar.n||0);const flagValues=Array.isArray(columnar.g)?columnar.g:[];const tierValues=Array.isArray(columnar.l)?columnar.l:[];
  const column=(key,index)=>Array.isArray(columns[key])?columns[key][index]??null:null;
  const rows=Array.from({length:count},(_,index)=>{const flagCodes=Array.isArray(column("fl",index))?column("fl",index):[];const tierCode=Number(column("pt",index));const row={sha16:String(column("s",index)||""),abs_path:String(column("a",index)||""),path_rel:String(column("p",index)||""),filename:String(column("n",index)||""),width:column("w",index),height:column("h",index),filesize:column("b",index),phash:String(column("x",index)||""),family_id:String(column("f",index)||"unassigned"),aes_v25:column("ae",index),topiq_iaa:column("ia",index),topiq_nr:column("nr",index),qrealign:column("qr",index),hpsv3_mu:column("hm",index),hpsv3_sigma:column("hs",index),nsfw_prob:column("ns",index),identity_sim:column("id",index),confusable_margin:column("cm",index),novelty:column("nv",index),consensus_z:column("cz",index),disagreement:column("dg",index),gaming_delta:column("gd",index),flags:flagCodes.map((code)=>flagValues[Number(code)]).filter(Boolean),proposed_tier:tierValues[tierCode]||"review",thumb_rel:String(column("th",index)||""),preview_available:Boolean(column("pr",index)),thumb_available:Boolean(column("tb",index))};row.__index=index;row.__key=row.sha16||row.filename||`row-${index}`;return row;});
  const compactFamilies=columnar.f&&typeof columnar.f==="object"?columnar.f:{};const families={};Object.entries(compactFamilies).forEach(([familyId,value])=>{const entry=Array.isArray(value)?value:[];families[familyId]={members:Array.isArray(entry[0])?entry[0]:[],champion:String(entry[1]||""),runner_up:String(entry[2]||"")};});
   const compactStats=columnar.z&&typeof columnar.z==="object"?columnar.z:{};const stats={total:Number(compactStats.n||count),tier_counts:compactStats.t||{},flag_counts:compactStats.f||{},consensus_z_median:compactStats.m,average_consensus_z:compactStats.a,pass_rate:Number(compactStats.p||0)};const hasQrealign=Array.isArray(columnar.d)&&columnar.d.includes("qrealign");const fingerprint=String(columnar.i||"__FINGERPRINT__");
   const identityDocument=columnar.y&&typeof columnar.y==="object"?columnar.y:null;const characterDocument=columnar.q??null;const identityEnabled=Boolean(identityDocument);const identityFaces=identityEnabled&&Array.isArray(identityDocument.faces)?identityDocument.faces.map((raw,index)=>{const entry=raw&&typeof raw==="object"?{...raw}:{};const faceId=String(entry.face_id||`face-${index+1}`);const bbox=Array.isArray(entry.bbox)?entry.bbox.slice(0,4).map((value)=>Number.isFinite(Number(value))?Number(value):0):[0,0,0,0];while(bbox.length<4)bbox.push(0);return {...entry,face_id:faceId,image_sha16:String(entry.image_sha16||""),bbox,det_score:Number.isFinite(Number(entry.det_score))?Number(entry.det_score):null,crop_rel:String(entry.crop_rel||"").replaceAll("\\","/"),cluster_id:entry.cluster_id??null,cluster_prob:Number.isFinite(Number(entry.cluster_prob))?Number(entry.cluster_prob):null,is_outlier:entry.is_outlier===true,cluster_margin:Number.isFinite(Number(entry.cluster_margin))?Number(entry.cluster_margin):null};}):[];const identityClusters=identityEnabled&&Array.isArray(identityDocument.clusters)?identityDocument.clusters.map((raw,index)=>{const entry=raw&&typeof raw==="object"?{...raw}:{};return {...entry,cluster_id:entry.cluster_id??`cluster-${index+1}`,size:Number.isFinite(Number(entry.size))?Number(entry.size):0,confidence:Number.isFinite(Number(entry.confidence))?Number(entry.confidence):null,suggested_character:typeof entry.suggested_character==="string"?entry.suggested_character:null,confirmed_character:typeof entry.confirmed_character==="string"?entry.confirmed_character:null,representative_faces:Array.isArray(entry.representative_faces)?entry.representative_faces.filter((value)=>typeof value==="string"):[]};}):[];const faceById=new Map(identityFaces.map((face)=>[face.face_id,face]));const facesByImage=new Map();const addImageFace=(sha,faceId)=>{if(!sha||!faceId)return;const current=facesByImage.get(sha)||[];if(!current.includes(faceId))current.push(faceId);facesByImage.set(sha,current);};identityFaces.forEach((face)=>addImageFace(face.image_sha16,face.face_id));if(identityEnabled&&Array.isArray(identityDocument.images))identityDocument.images.forEach((raw)=>{if(!raw||typeof raw!=="object")return;const sha=String(raw.sha16||"");if(Array.isArray(raw.faces))raw.faces.forEach((faceId)=>addImageFace(sha,String(faceId||"")));});const clusterById=new Map(identityClusters.map((cluster)=>[String(cluster.cluster_id),cluster]));const clusterFaces=new Map();identityFaces.forEach((face)=>{const key=String(face.cluster_id??"outlier");const current=clusterFaces.get(key)||[];current.push(face.face_id);clusterFaces.set(key,current);});const knownNames=new Set();const catalogByFace=new Map();const catalogByCluster=new Map();const addCharacterName=(value)=>{if(typeof value==="string"&&value.trim())knownNames.add(value.trim());};const collectCharacterSource=(value)=>{if(Array.isArray(value)){value.forEach((item)=>collectCharacterSource(item));return;}if(!value||typeof value!=="object")return;const entry=value;const name=typeof entry.character==="string"?entry.character:typeof entry.name==="string"?entry.name:typeof entry.confirmed_character==="string"?entry.confirmed_character:"";addCharacterName(name);const faceId=typeof entry.face_id==="string"?entry.face_id:"";const clusterId=entry.cluster_id===undefined||entry.cluster_id===null?"":String(entry.cluster_id);if(name&&faceId)catalogByFace.set(faceId,name);if(name&&clusterId)catalogByCluster.set(clusterId,name);Object.entries(entry).forEach(([key,item])=>{if(["character","name","confirmed_character","face_id","cluster_id"].includes(key))return;if(typeof item==="string"){addCharacterName(item);if(key.startsWith("f_"))catalogByFace.set(key,item);else if(key.startsWith("c_")||/^[-]?\d+$/.test(key))catalogByCluster.set(key,item);}else if(Array.isArray(item)||item&&typeof item==="object")collectCharacterSource(item);});};collectCharacterSource(characterDocument);identityClusters.forEach((cluster)=>{addCharacterName(cluster.confirmed_character);addCharacterName(cluster.suggested_character);if(cluster.confirmed_character)catalogByCluster.set(String(cluster.cluster_id),cluster.confirmed_character);});
  const els=(id)=>document.getElementById(id);const finite=(value)=>typeof value==="number"&&Number.isFinite(value);const numberText=(value)=>finite(value)?Number(value).toFixed(3):"—";const percentText=(value)=>finite(value)?`${(Number(value)*100).toFixed(1)}%`:"—";const formatBytes=(value)=>`${(Number(value)/1024).toFixed(1)} KB`;const rowKey=(row)=>String(row.__key);const privateRow=(row)=>finite(row.nsfw_prob)&&Number(row.nsfw_prob)>=.65||row.proposed_tier==="route_nsfw";
  const tierLabels={queue:"入队候选",review:"人工复核",archive_candidate:"归档候选",route_nsfw:"NSFW 复核",route_identity:"身份复核"};const flagLabels={uncertain:"评分分歧",gaming_suspect:"刷分嫌疑",nsfw:"NSFW",id_low:"身份低分",near_dup_runnerup:"家族备选",audit_sample:"审计抽样"};const fieldLabels={sha16:"SHA16",abs_path:"原始路径",path_rel:"相对路径",filename:"文件名",width:"宽度",height:"高度",filesize:"文件大小",phash:"感知哈希",family_id:"家族",aes_v25:"美学 v2.5",topiq_iaa:"TOPIQ-IAA",topiq_nr:"TOPIQ-NR",qrealign:"Q-ReAlign",hpsv3_mu:"HPSv3 μ",hpsv3_sigma:"HPSv3 σ",nsfw_prob:"NSFW 概率",identity_sim:"身份相似度",confusable_margin:"身份混淆边际",novelty:"新颖度",consensus_z:"共识 Z",disagreement:"分歧度",gaming_delta:"刷分差值",flags:"标记",proposed_tier:"处置提案",thumb_rel:"缩略图路径"};const actionDefs=[{id:"select",label:"精选",key:"1"},{id:"queue",label:"入队通过",key:"2"},{id:"archive",label:"归档",key:"3"},{id:"nsfw_confirm",label:"NSFW 确认",key:"4"},{id:"identity_doubt",label:"身份存疑",key:"5"},{id:"skip",label:"跳过",key:"6"}];const scoreFields=["aes_v25","topiq_iaa","topiq_nr",...(hasQrealign?["qrealign"]:[]),"hpsv3_mu","hpsv3_sigma","nsfw_prob","identity_sim","confusable_margin","novelty","consensus_z","disagreement","gaming_delta"];const numericFields=new Set(scoreFields);
  for (const field of ["hpsv3_mu", "hpsv3_sigma"]) {
    const header = document.createElement("th");
    header.className = "col-score"; header.scope = "col"; header.dataset.sortColumn = field;
    const button = document.createElement("button");
    button.type = "button"; button.className = "sort-button"; button.dataset.sort = field;
    button.textContent = fieldLabels[field] + " ";
    const indicator = document.createElement("span");
    indicator.className = "sort-indicator"; indicator.setAttribute("aria-hidden", "true"); indicator.textContent = "↕";
    button.append(indicator); header.append(button);
    document.querySelector('th[data-sort-column="nsfw_prob"]').before(header);
  }
   const PREFETCH_K=Math.max(1,Number(columnar.k||6));const PREFETCH_CONCURRENCY=4;const IDENTITY_CROP_CONCURRENCY=4;const LABEL_ACTIONS=new Set(["confirm","new","ignore","wrong_box"]);const state={mode:"studio",search:"",tier:null,flags:new Set(),onlyUnreviewed:false,showNsfw:false,uncertaintyFirst:false,sortField:"consensus_z",sortDirection:-1,currentKey:rows[0]?rowKey(rows[0]):null,visible:[],zoomed:false,panX:0,panY:0,revealed:new Set(),selectedFaces:new Set(),openFaceId:null,openClusterId:null};let journal={decisions:{},entries:[],history:[],faceLabels:{},faceHistory:[],clusterDecisions:[]};let lastFocus=null;let tableRaf=0;let mediaGeneration=0;let stageKey="";let stageCandidates=[];let stageCandidateIndex=0;let faceResizeObserver=null;let cropObserver=null;const cropQueue=[];const activeCropLoads=new Set();const prefetch={generation:0,queue:[],active:new Set(),handles:new Set()};
   const storageKey=`image-review-studio:${fingerprint}`;const loadJournal=()=>{try{const raw=localStorage.getItem(storageKey);if(!raw)return;const parsed=JSON.parse(raw);if(parsed&&typeof parsed==="object"){journal={decisions:parsed.decisions&&typeof parsed.decisions==="object"?parsed.decisions:{},entries:Array.isArray(parsed.entries)?parsed.entries:[],history:Array.isArray(parsed.history)?parsed.history:[],faceLabels:parsed.faceLabels&&typeof parsed.faceLabels==="object"?parsed.faceLabels:{},faceHistory:Array.isArray(parsed.faceHistory)?parsed.faceHistory:[],clusterDecisions:Array.isArray(parsed.clusterDecisions)?parsed.clusterDecisions:[]};}}catch(_error){journal={decisions:{},entries:[],history:[],faceLabels:{},faceHistory:[],clusterDecisions:[]};}};const saveJournal=()=>{try{localStorage.setItem(storageKey,JSON.stringify(journal));}catch(_error){els("journal-note").textContent="本次会话可用 · 浏览器未允许持久化";}};loadJournal();
  const assetCandidates=(row)=>{const thumb=String(row.thumb_rel||`thumbs/${row.sha16}.jpg`).replaceAll("\\","/");const preview=thumb.replace(/(^|\/)thumbs\//,"$1previews/");const candidates=[];if(row.preview_available)candidates.push(preview);if(row.thumb_available)candidates.push(thumb);return candidates;};const thumbAsset=(row)=>assetCandidates(row).at(-1)||"";const fileUrl=(path)=>{const normalized=String(path||"").replaceAll("\\","/");if(!normalized)return"";const parts=normalized.split("/");if(/^[A-Za-z]:$/.test(parts[0]))return`file:///${parts[0]}/${parts.slice(1).map(encodeURIComponent).join("/")}`;if(normalized.startsWith("/"))return`file://${parts.map(encodeURIComponent).join("/")}`;return`file:${parts.map(encodeURIComponent).join("/")}`;};const rawValue=(value)=>{if(value===null||value===undefined||value==="")return"空值 · 未计算 / 不适用";if(Array.isArray(value))return value.length?value.join("|"):"空值 · 未计算 / 不适用";return String(value);};const formatField=(field,value)=>{if(field==="nsfw_prob"||field==="identity_sim")return percentText(value);if(field==="flags")return Array.isArray(value)&&value.length?value.map((flag)=>flagLabels[flag]||flag).join("、"):"—";if(field==="proposed_tier")return tierLabels[value]||value||"—";if(numericFields.has(field))return numberText(value);return rawValue(value).replace("空值 · 未计算 / 不适用","—");};
   const manualFor=(row)=>String(journal.decisions[rowKey(row)]||"");const actionLabel=(action)=>actionDefs.find((item)=>item.id===action)?.label||"撤销";const facesForRow=(row)=>{const ids=facesByImage.get(String(row?.sha16||""))||[];return ids.map((id)=>faceById.get(id)).filter(Boolean);};const faceCluster=(face)=>clusterById.get(String(face.cluster_id))||null;const faceLabel=(face)=>{const stored=journal.faceLabels[face.face_id];if(stored&&typeof stored==="object")return stored;const catalogName=catalogByFace.get(face.face_id)||catalogByCluster.get(String(face.cluster_id));const cluster=faceCluster(face);const fallback=catalogName||cluster?.confirmed_character||"";return fallback?{face_id:face.face_id,image_sha16:face.image_sha16,character:fallback,action:"confirm"}:null;};const faceIsNamed=(face)=>{const label=faceLabel(face);return Boolean(label&&String(label.character||"").trim()&&(label.action==="confirm"||label.action==="new"));};const faceActionLabel=(action)=>({confirm:"确认",new:"新建",ignore:"忽略",wrong_box:"框选有误"}[action]||"未标注");const faceMeta=(face)=>{const cluster=faceCluster(face);const clusterText=face.cluster_id===null||face.cluster_id===undefined?"离群":`聚类 ${String(face.cluster_id)}`;const confidence=finite(face.cluster_prob)?`置信度 ${percentText(face.cluster_prob)}`:"置信度 —";const detection=finite(face.det_score)?`检测 ${percentText(face.det_score)}`:"检测 —";return `${face.face_id} · ${clusterText} · ${confidence} · ${detection}${cluster?.confidence!==null&&finite(cluster?.confidence)?` · 聚类均值 ${percentText(cluster.confidence)}`:""}`;};const uncertaintyScore=(face)=>{const probabilityRisk=finite(face.cluster_prob)?1-Math.max(0,Math.min(1,Number(face.cluster_prob))):.55;const marginRisk=finite(face.cluster_margin)?1-Math.min(1,Math.abs(Number(face.cluster_margin))/.5):.5;const cluster=faceCluster(face);const singleton=cluster&&Number(cluster.size)<=1?1:cluster?0:1;const detectionRisk=finite(face.det_score)?1-Math.max(0,Math.min(1,Number(face.det_score))):.5;return probabilityRisk*.4+marginRisk*.3+singleton*.2+detectionRisk*.1;};const orderedReviewFaces=()=>{const all=identityFaces.slice();if(!state.uncertaintyFirst)return all;return all.sort((left,right)=>uncertaintyScore(right)-uncertaintyScore(left)||left.face_id.localeCompare(right.face_id,"zh-CN"));};const namedFaceCount=()=>identityFaces.filter(faceIsNamed).length;const selectedFaceCount=()=>state.selectedFaces.size;const rowForFace=(face)=>rows.find((row)=>String(row.sha16)===String(face.image_sha16))||null;const recordClusterDecision=(clusterId,action,extra={})=>{const entry={kind:"cluster",cluster_id:clusterId,action,...extra,timestamp:new Date().toISOString()};journal.clusterDecisions.push(entry);journal.entries.push(entry);saveJournal();renderCharacterClusters();renderJournalPreview();renderJournalExport();};const recordFaceLabel=(face,action,character="")=>{if(!LABEL_ACTIONS.has(action))return;const previous=journal.faceLabels[face.face_id]||null;const next={face_id:face.face_id,image_sha16:String(face.image_sha16||""),character:String(character||""),action};journal.faceLabels[face.face_id]=next;journal.faceHistory.push({face_id:face.face_id,previous,next,undone:false});journal.entries.push({kind:"face",face_id:face.face_id,image_sha16:next.image_sha16,character:next.character,action,filename:rowForFace(face)?.filename||"",timestamp:new Date().toISOString()});if(next.character)knownNames.add(next.character);saveJournal();state.selectedFaces.delete(face.face_id);renderFaceOverlay();renderCharacterPanel();renderJournalPreview();renderJournalExport();updateCharacterSummary();};const undoFaceLabel=(faceId)=>{let target=null;for(let index=journal.faceHistory.length-1;index>=0;index-=1){const entry=journal.faceHistory[index];if(entry.face_id===faceId&&!entry.undone){target=entry;entry.undone=true;break;}}if(!target)return false;if(target.previous)journal.faceLabels[faceId]=target.previous;else delete journal.faceLabels[faceId];journal.entries.push({kind:"face",face_id:faceId,action:"undo",timestamp:new Date().toISOString()});saveJournal();renderFaceOverlay();renderCharacterPanel();renderJournalPreview();renderJournalExport();updateCharacterSummary();return true;};const characterLabelsPayload=()=>({version:1,source:"review-studio",corpus_fingerprint:fingerprint,labels:Object.values(journal.faceLabels).filter((label)=>label&&LABEL_ACTIONS.has(label.action)).map((label)=>({face_id:String(label.face_id||""),image_sha16:String(label.image_sha16||""),character:String(label.character||""),action:label.action}))});const sortKeys={};const sortFields=["filename","family_id",...scoreFields];sortFields.forEach((field)=>{sortKeys[field]=rows.map((row)=>numericFields.has(field)?(finite(row[field])?Number(row[field]):null):String(row[field]||"").toLocaleLowerCase("zh-CN"));});
  const compareIndices=(leftIndex,rightIndex)=>{const field=state.sortField;const left=sortKeys[field]?.[leftIndex];const right=sortKeys[field]?.[rightIndex];if(left===null&&right===null)return leftIndex-rightIndex;if(left===null)return 1;if(right===null)return-1;const result=typeof left==="number"?left-right:String(left).localeCompare(String(right),"zh-CN",{numeric:true,sensitivity:"base"});return result*state.sortDirection||leftIndex-rightIndex;};const matches=(row)=>{const search=state.search.toLocaleLowerCase("zh-CN");const haystack=[row.filename,row.sha16,row.family_id].map((value)=>String(value||"").toLocaleLowerCase("zh-CN")).join(" ");const flagMatch=!state.flags.size||row.flags.some((flag)=>state.flags.has(flag));const reviewMatch=!state.onlyUnreviewed||!manualFor(row);return(!search||haystack.includes(search))&&(!state.tier||row.proposed_tier===state.tier)&&flagMatch&&reviewMatch;};
  function recomputeVisible(preferredKey=state.currentKey){const previousPosition=state.visible.findIndex((index)=>rowKey(rows[index])===preferredKey);state.visible=rows.map((_,index)=>index).filter((index)=>matches(rows[index])).sort(compareIndices);const found=state.visible.find((index)=>rowKey(rows[index])===preferredKey);if(found!==undefined)state.currentKey=rowKey(rows[found]);else if(state.visible.length)state.currentKey=rowKey(rows[state.visible[Math.min(Math.max(previousPosition,0),state.visible.length-1)]]);else state.currentKey=null;}
  const setText=(id,value)=>{const node=els(id);if(node)node.textContent=String(value);};const currentIndex=()=>state.visible.findIndex((index)=>rowKey(rows[index])===state.currentKey);const currentRow=()=>{const index=currentIndex();return index>=0?rows[state.visible[index]]:null;};
  function renderStats(){const tierCounts=stats.tier_counts||{};const flagCounts=stats.flag_counts||{};setText("stat-total",Number(stats.total||rows.length).toLocaleString("zh-CN"));setText("stat-consensus",numberText(stats.consensus_z_median));setText("stat-review",Number(tierCounts.review||0).toLocaleString("zh-CN"));const risk=Number(flagCounts.nsfw||0)+Number(flagCounts.id_low||0)+Number(flagCounts.gaming_suspect||0);setText("stat-risk",risk.toLocaleString("zh-CN"));const payloadText=`${rows.length.toLocaleString("zh-CN")} 条 · gzip ${formatBytes(__GZIP_BYTES__)} · 解码 ${(performance.now()-decodeStart).toFixed(0)}ms · 无网络访问`;setText("run-meta",payloadText);document.title=document.getElementById("brand-title")?.textContent||document.title;}
  function renderTierBoard(){const board=els("tier-board");const fragment=document.createDocumentFragment();["queue","review","archive_candidate","route_nsfw","route_identity"].forEach((tier)=>{const button=document.createElement("button");button.type="button";button.className="tier-card";button.setAttribute("aria-pressed",String(state.tier===tier));button.dataset.tier=tier;const name=document.createElement("span");name.className="tier-name";name.textContent=tierLabels[tier];const count=document.createElement("strong");count.textContent=Number(stats.tier_counts?.[tier]||0).toLocaleString("zh-CN");const hint=document.createElement("span");hint.className="tier-hint";hint.textContent=state.tier===tier?"已筛选":"点击筛选";button.append(name,count,hint);fragment.append(button);});board.replaceChildren(fragment);}
  function renderFlagFilters(){const group=els("flag-filters");const fragment=document.createDocumentFragment();["uncertain","gaming_suspect","nsfw","id_low","near_dup_runnerup","audit_sample"].forEach((flag)=>{const button=document.createElement("button");button.type="button";button.className="chip";button.textContent=flagLabels[flag];button.dataset.flag=flag;button.setAttribute("aria-pressed",String(state.flags.has(flag)));fragment.append(button);});group.replaceChildren(fragment);}
  function renderActiveFilters(){const container=els("active-filters");const fragment=document.createDocumentFragment();const hasFilters=Boolean(state.search||state.tier||state.flags.size||state.onlyUnreviewed);const label=document.createElement("span");label.className="active-filter-title";label.textContent=hasFilters?"当前筛选：":"筛选状态：未启用";fragment.append(label);if(state.search){const chip=document.createElement("button");chip.type="button";chip.className="active-filter";chip.dataset.clear="search";chip.textContent=`搜索“${state.search}” ×`;fragment.append(chip);}if(state.tier){const chip=document.createElement("button");chip.type="button";chip.className="active-filter";chip.dataset.clear="tier";chip.textContent=`处置：${tierLabels[state.tier]} ×`;fragment.append(chip);}state.flags.forEach((flag)=>{const chip=document.createElement("button");chip.type="button";chip.className="active-filter";chip.dataset.clear=`flag:${flag}`;chip.textContent=`${flagLabels[flag]} ×`;fragment.append(chip);});if(state.onlyUnreviewed){const chip=document.createElement("button");chip.type="button";chip.className="active-filter";chip.dataset.clear="unreviewed";chip.textContent="仅看未审 ×";fragment.append(chip);}if(hasFilters){const clear=document.createElement("button");clear.type="button";clear.className="clear-button";clear.dataset.clear="all";clear.textContent="清除筛选";fragment.append(clear);}container.replaceChildren(fragment);}
   function refreshView(preferredKey=state.currentKey){recomputeVisible(preferredKey);if(groupingEnabled&&state.groupCharacter)state.visible=state.visible.filter((index)=>groupingMatches(rows[index]));renderTierBoard();renderFlagFilters();renderActiveFilters();renderStudio();renderSpotlights();scheduleTableRender();if(state.mode==="grouping")renderGroupingView();}
  function renderDecisionBadge(node,action){node.hidden=!action;node.textContent=action?`人工：${actionLabel(action)}`:"";}
  function renderScoreGrid(row){const grid=els("score-grid");const fragment=document.createDocumentFragment();scoreFields.forEach((field)=>{const card=document.createElement("div");card.className="score-card";const label=document.createElement("label");label.textContent=fieldLabels[field];const value=document.createElement("strong");const raw=row[field];value.textContent=formatField(field,raw);if(!finite(raw)&&numericFields.has(field))value.classList.add("empty");value.title=`原始值：${rawValue(raw)}`;card.append(label,value);fragment.append(card);});grid.replaceChildren(fragment);}
  function renderFlags(container,row){const fragment=document.createDocumentFragment();if(!row){container.replaceChildren();return;}if(!row.flags.length){const badge=document.createElement("span");badge.className="badge";badge.dataset.flag="none";badge.textContent="无";fragment.append(badge);}else row.flags.forEach((flag)=>{const badge=document.createElement("span");badge.className="badge";badge.dataset.flag=flag;badge.textContent=flagLabels[flag]||flag;fragment.append(badge);});container.replaceChildren(fragment);}
  function renderRawFields(row){const fields=["sha16","abs_path","path_rel","filename","width","height","filesize","phash","family_id",...scoreFields,"flags","proposed_tier","thumb_rel"];const fragment=document.createDocumentFragment();fields.forEach((field)=>{const wrapper=document.createElement("div");wrapper.className="raw-field";const label=document.createElement("dt");label.textContent=fieldLabels[field]||field;const value=document.createElement("dd");value.textContent=formatField(field,row[field]);value.title=`原始值：${rawValue(row[field])}`;wrapper.append(label,value);fragment.append(wrapper);});els("raw-fields").replaceChildren(fragment);}
   function journalEntryLabel(entry){if(entry.action==="undo")return"撤销";if(entry.kind==="face")return`人脸 · ${faceActionLabel(entry.action)}${entry.character?` · ${entry.character}`:""}`;if(entry.kind==="cluster")return`聚类 · ${entry.action==="name"?"命名":entry.action==="merge"?"合并":entry.action==="split"?"拆分":entry.action==="outlier"?"离群":entry.action}`;return actionLabel(entry.action);}function renderJournalPreview(){const list=els("journal-list");const entries=journal.entries.slice(-6).reverse();const fragment=document.createDocumentFragment();if(!entries.length){const empty=document.createElement("span");empty.className="journal-note";empty.textContent="暂无人工动作";fragment.append(empty);}else entries.forEach((entry)=>{const line=document.createElement("div");line.className="journal-entry";const name=document.createElement("strong");name.textContent=entry.kind==="face"?entry.face_id:entry.kind==="cluster"?`聚类 ${entry.cluster_id}`:entry.sha16||"当前图片";const action=document.createElement("span");action.textContent=journalEntryLabel(entry);line.append(name,action);fragment.append(line);});list.replaceChildren(fragment);setText("journal-count",journal.entries.filter((entry)=>entry.action!=="undo").length.toLocaleString("zh-CN"));setText("journal-summary",`语料指纹 ${fingerprint} · ${journal.entries.length.toLocaleString("zh-CN")} 条日志 · ${Object.keys(journal.decisions).length.toLocaleString("zh-CN")} 张图片 · ${Object.keys(journal.faceLabels).length.toLocaleString("zh-CN")} 张人脸`);}
  function renderActionBelt(row){const belt=els("action-belt");const fragment=document.createDocumentFragment();actionDefs.forEach((item)=>{const button=document.createElement("button");button.type="button";button.className="action-button";button.dataset.action=item.id;button.setAttribute("aria-pressed",String(manualFor(row)===item.id));button.setAttribute("aria-keyshortcuts",item.key);const key=document.createElement("span");key.className="keycap";key.textContent=item.key;const label=document.createElement("span");label.textContent=item.label;button.append(key,label);fragment.append(button);});const undo=document.createElement("button");undo.type="button";undo.className="action-button";undo.dataset.action="undo";undo.setAttribute("aria-keyshortcuts","U");const undoKey=document.createElement("span");undoKey.className="keycap";undoKey.textContent="U";const undoLabel=document.createElement("span");undoLabel.textContent="撤销";undo.append(undoKey,undoLabel);fragment.append(undo);const status=document.createElement("span");status.className="belt-status";status.id="belt-status";status.textContent=manualFor(row)?"已保存到本地":"选择动作后保存在本地";fragment.append(status);belt.replaceChildren(fragment);}
   function faceOverlayRect(face){const image=els("studio-image");const canvas=els("preview-canvas");if(!image||image.hidden||!image.naturalWidth||!image.naturalHeight)return null;const imageRect=image.getBoundingClientRect();const canvasRect=canvas.getBoundingClientRect();const scaleX=imageRect.width/image.naturalWidth;const scaleY=imageRect.height/image.naturalHeight;const box=Array.isArray(face.bbox)?face.bbox:[0,0,0,0];const left=Number(box[0])||0;const top=Number(box[1])||0;const width=Math.max(0,Number(box[2])||0);const height=Math.max(0,Number(box[3])||0);if(width<=0||height<=0||scaleX<=0||scaleY<=0)return null;return {left:imageRect.left-canvasRect.left+left*scaleX,top:imageRect.top-canvasRect.top+top*scaleY,width:width*scaleX,height:height*scaleY};}
    function renderFaceOverlay(){const layer=els("face-overlay");const row=currentRow();if(!layer||!identityEnabled||!row){if(layer){layer.hidden=true;layer.replaceChildren();}return;}const faces=facesForRow(row);const fragment=document.createDocumentFragment();faces.forEach((face)=>{const rect=faceOverlayRect(face);if(!rect)return;const grouped=groupingFaceById.get(face.face_id);const localLabel=faceLabel(face);const clusterFallback=face.cluster_id===null||face.cluster_id===undefined?"未定":`聚类 ${String(face.cluster_id)}`;const displayName=grouped?.decision==="assigned"&&grouped.character?grouped.character:localLabel?.character||clusterFallback;const groupedMeta=grouped?` · 相似度 ${numberText(grouped.sim)} · 间隔 ${numberText(grouped.margin)} · 决策 ${grouped.decision||"未提供"}`:"";const button=document.createElement("button");button.type="button";button.className="face-box";button.dataset.faceId=face.face_id;button.setAttribute("aria-label",`${faceMeta(face)} · ${displayName}${groupedMeta} · 点击命名`);button.title=button.getAttribute("aria-label");button.style.left=`${rect.left}px`;button.style.top=`${rect.top}px`;button.style.width=`${rect.width}px`;button.style.height=`${rect.height}px`;button.classList.toggle("is-selected",state.openFaceId===face.face_id);button.classList.toggle("is-uncertain",uncertaintyScore(face)>=.55);button.classList.toggle("is-outlier",face.is_outlier===true);button.classList.toggle("is-private",privateRow(row));const chip=document.createElement("span");chip.className="face-label-chip";chip.textContent=displayName;button.append(chip);const tooltip=document.createElement("span");tooltip.className="face-tooltip";tooltip.textContent=`${faceMeta(face)} · ${displayName}${groupedMeta}`;button.append(tooltip);fragment.append(button);});layer.replaceChildren(fragment);layer.hidden=!faces.length;}
   function renderFaceNameOptions(face){const select=els("face-character-select");if(!select)return;const current=faceLabel(face)?.character||"";const names=[...knownNames].filter(Boolean).sort((left,right)=>left.localeCompare(right,"zh-CN"));select.replaceChildren();const empty=document.createElement("option");empty.value="";empty.textContent="选择已有名字…";select.append(empty);names.forEach((name)=>{const option=document.createElement("option");option.value=name;option.textContent=name;if(name===current)option.selected=true;select.append(option);});const input=els("face-character-name");if(input)input.value=current&&!names.includes(current)?current:"";}
   function positionFacePopover(anchor){const popover=els("face-popover");if(!popover||popover.hidden||!anchor)return;const rect=anchor.getBoundingClientRect();const margin=12;const width=popover.offsetWidth;const height=popover.offsetHeight;const left=Math.max(margin,Math.min(window.innerWidth-width-margin,rect.left));const top=rect.bottom+margin+height<=window.innerHeight?rect.bottom+margin:Math.max(margin,rect.top-height-margin);popover.style.left=`${left}px`;popover.style.top=`${top}px`;}
   function openFacePopover(faceId){const face=faceById.get(faceId);const anchor=els("face-overlay")?.querySelector(`[data-face-id="${CSS.escape(faceId)}"]`);const popover=els("face-popover");if(!face||!popover||!anchor)return;state.openFaceId=faceId;renderFaceNameOptions(face);setText("face-popover-title",faceLabel(face)?.character?"修改人物标注":"标注人脸");setText("face-popover-meta",faceMeta(face));setText("face-popover-status","");popover.hidden=false;positionFacePopover(anchor);renderFaceOverlay();els("face-character-select")?.focus();}
    function closeFacePopover(){const popover=els("face-popover");if(!popover||popover.hidden)return;const faceId=state.openFaceId;popover.hidden=true;state.openFaceId=null;renderFaceOverlay();const target=faceId?els("face-overlay")?.querySelector(`[data-face-id="${CSS.escape(faceId)}"]`):null;target?.focus();}
   function activeFace(){return state.openFaceId?faceById.get(state.openFaceId)||null:null;}
   function facePopoverAction(action){const face=activeFace();if(!face)return;const select=els("face-character-select");const input=els("face-character-name");const selected=select?.value||"";const typed=input?.value.trim()||"";const character=action==="confirm"?(selected||typed):action==="new"?typed:"";if((action==="confirm"||action==="new")&&!character){setText("face-popover-status","请选择已有名字或输入新名字");(input||select)?.focus();return;}recordFaceLabel(face,action,character);closeFacePopover();}
    function updatePrivacy(row){const canvas=els("preview-canvas");const privateHidden=privateRow(row)&&!state.showNsfw&&!state.revealed.has(rowKey(row));els("studio-image").classList.toggle("is-private",privateHidden);const reveal=els("privacy-reveal");reveal.hidden=!privateHidden;reveal.textContent=privateHidden?"点击显示 NSFW":"";canvas.setAttribute("aria-label",privateHidden?"NSFW 图片，当前已模糊，点击显示":"大图审查区域");renderGroupingBadges(row);renderFaceOverlay();}
   function showStudioPlaceholder(text){const image=els("studio-image");image.hidden=true;const placeholder=els("studio-placeholder");placeholder.hidden=false;placeholder.textContent=text;els("stage-loading").hidden=true;const layer=els("face-overlay");if(layer){layer.hidden=true;layer.replaceChildren();}}
   function mountStudioAsset(row){const generation=++mediaGeneration;const image=els("studio-image");const placeholder=els("studio-placeholder");stageCandidates=assetCandidates(row);stageCandidateIndex=0;if(!stageCandidates.length){showStudioPlaceholder("无缩略图 · 暂无可用预览");return;}els("stage-loading").hidden=false;placeholder.hidden=true;image.hidden=false;image.style.opacity=".35";const tryNext=()=>{if(generation!==mediaGeneration)return;if(stageCandidateIndex>=stageCandidates.length){showStudioPlaceholder("文件缺失 · 暂无可用预览");return;}const probe=new Image();const source=stageCandidates[stageCandidateIndex];probe.decoding="async";probe.onload=async()=>{if(typeof probe.decode==="function"){try{await probe.decode();}catch(_error){}}if(generation!==mediaGeneration)return;image.src=source;image.alt=row.filename||"图片预览";image.dataset.source=source;image.style.opacity="1";image.hidden=false;placeholder.hidden=true;els("stage-loading").hidden=true;requestAnimationFrame(renderFaceOverlay);};probe.onerror=()=>{stageCandidateIndex+=1;tryNext();};probe.src=source;};tryNext();}
   function applyZoom(){const canvas=els("preview-canvas");canvas.classList.toggle("is-zoomed",state.zoomed);const image=els("studio-image");image.style.transform=state.zoomed?`translate3d(${state.panX}px,${state.panY}px,0)`:"";setText("zoom-toggle",state.zoomed?"适合窗口":"100% 原图");requestAnimationFrame(renderFaceOverlay);}
  function renderFilmstrip(){const list=els("filmstrip-list");const position=currentIndex();if(position<0){list.replaceChildren();setText("studio-progress","0 / 0");return;}const start=Math.max(0,position-5);const end=Math.min(state.visible.length,position+6);const fragment=document.createDocumentFragment();for(let order=start;order<end;order+=1){const index=state.visible[order];const row=rows[index];const button=document.createElement("button");button.type="button";button.className="film-card";button.dataset.action="jump";button.dataset.index=String(index);button.setAttribute("aria-current",String(index===state.visible[position]));button.setAttribute("aria-label",`${order+1}：${row.filename||row.sha16||"图片"}`);const source=thumbAsset(row);if(source){const image=document.createElement("img");image.loading="lazy";image.decoding="async";image.src=source;image.alt="";image.dataset.media="film";image.dataset.fallback="";button.append(image);}else{const placeholder=document.createElement("span");placeholder.className="film-placeholder";placeholder.textContent="无图";button.append(placeholder);}button.classList.toggle("is-private",privateRow(row)&&!state.showNsfw&&!state.revealed.has(rowKey(row)));const decision=manualFor(row);if(decision){const badge=document.createElement("span");badge.className="film-decision";badge.textContent=actionLabel(decision);button.append(badge);}fragment.append(button);}list.replaceChildren(fragment);setText("studio-progress",`${position+1} / ${state.visible.length}`);}
   function effectiveClusters(){if(!identityEnabled)return[];const clusters=identityClusters.slice();const known=new Set(clusters.map((cluster)=>String(cluster.cluster_id)));clusterFaces.forEach((faceIds,key)=>{if(!known.has(key)){clusters.push({cluster_id:key,size:faceIds.length,centroid_face_id:faceIds[0]||"",confidence:null,suggested_character:null,confirmed_character:null,representative_faces:faceIds.slice(0,3)});}});return clusters.sort((left,right)=>Number(right.size||0)-Number(left.size||0)||String(left.cluster_id).localeCompare(String(right.cluster_id),"zh-CN",{numeric:true}));}
   function clusterFaceList(cluster){const ids=clusterFaces.get(String(cluster.cluster_id))||[];const selected=Array.isArray(cluster.representative_faces)?cluster.representative_faces.filter((id)=>faceById.has(id)):[];const order=[...selected,...ids.filter((id)=>!selected.includes(id))];const faces=order.map((id)=>faceById.get(id)).filter(Boolean);return state.uncertaintyFirst?faces.sort((left,right)=>uncertaintyScore(right)-uncertaintyScore(left)||left.face_id.localeCompare(right.face_id,"zh-CN")):faces;}
   function clusterConfidence(cluster){if(finite(cluster.confidence))return Number(cluster.confidence);const values=clusterFaceList(cluster).map((face)=>face.cluster_prob).filter(finite);return values.length?values.reduce((sum,value)=>sum+Number(value),0)/values.length:null;}
   function clusterName(cluster){const decision=journal.clusterDecisions.slice().reverse().find((entry)=>String(entry.cluster_id)===String(cluster.cluster_id)&&entry.action==="name"&&!entry.undone);return decision?.character||cluster.confirmed_character||"";}
   function makeCropButton(face,row){const button=document.createElement("button");button.type="button";button.className="cluster-crop";button.dataset.panelFaceId=face.face_id;button.setAttribute("aria-label",`选择 ${face.face_id} · ${faceMeta(face)}`);button.classList.toggle("is-selected",state.selectedFaces.has(face.face_id));const source=String(face.crop_rel||"").replaceAll("\\","/");if(source){const image=document.createElement("img");image.loading="lazy";image.decoding="async";image.alt="";image.dataset.cropSource=source;image.dataset.cropPending="true";if(row&&privateRow(row)&&!state.showNsfw&&!state.revealed.has(rowKey(row)))image.classList.add("is-private");button.append(image);}else{const placeholder=document.createElement("span");placeholder.className="film-placeholder";placeholder.textContent="无裁剪";button.append(placeholder);}const label=document.createElement("span");label.className="cluster-crop-label";label.textContent=faceLabel(face)?.character||face.face_id;button.append(label);return button;}
   function renderClusterCard(cluster,index,top,allClusters){const card=document.createElement("article");card.className="cluster-card";card.style.top=`${top}px`;card.dataset.clusterId=String(cluster.cluster_id);const clusterFacesForCard=clusterFaceList(cluster);const selectedInCluster=clusterFacesForCard.filter((face)=>state.selectedFaces.has(face.face_id)).length;const name=clusterName(cluster);const heading=document.createElement("h3");heading.textContent=`${String(cluster.cluster_id)==="outlier"?"离群 / 未知":`聚类 ${cluster.cluster_id}`}${name?` · ${name}`:""}`;card.append(heading);const meta=document.createElement("div");meta.className="cluster-meta";const size=document.createElement("span");size.textContent=`${Number(cluster.size||clusterFacesForCard.length)} 张`;const confidence=document.createElement("span");confidence.textContent=`均值 ${percentText(clusterConfidence(cluster))}`;meta.append(size,confidence);if(cluster.suggested_character&&!name){const suggested=document.createElement("span");suggested.className="cluster-suggested";suggested.textContent=`建议：${cluster.suggested_character}`;meta.append(suggested);}const decision=journal.clusterDecisions.slice().reverse().find((entry)=>String(entry.cluster_id)===String(cluster.cluster_id)&&!entry.undone);if(decision){const stateText=document.createElement("span");stateText.textContent=decision.action==="outlier"?"已标记离群":decision.action==="merge"?`已合并到 ${decision.target_cluster_id}`:decision.action==="split"?"已拆分":"已决定";meta.append(stateText);}card.append(meta);const crops=document.createElement("div");crops.className="cluster-crops";clusterFacesForCard.slice(0,3).forEach((face)=>crops.append(makeCropButton(face,rowForFace(face))));if(!crops.children.length){const empty=document.createElement("span");empty.className="character-empty";empty.textContent="暂无代表人脸";crops.append(empty);}card.append(crops);const actions=document.createElement("div");actions.className="cluster-actions";const nameButton=document.createElement("button");nameButton.type="button";nameButton.className="cluster-action";nameButton.dataset.clusterAction="name";nameButton.dataset.clusterId=String(cluster.cluster_id);nameButton.textContent="命名";actions.append(nameButton);const mergeSelect=document.createElement("select");mergeSelect.className="cluster-merge-target";mergeSelect.dataset.clusterMergeSelect=String(cluster.cluster_id);mergeSelect.setAttribute("aria-label",`选择 ${String(cluster.cluster_id)} 的合并目标`);const emptyOption=document.createElement("option");emptyOption.value="";emptyOption.textContent="选择目标…";mergeSelect.append(emptyOption);allClusters.filter((other)=>String(other.cluster_id)!==String(cluster.cluster_id)).forEach((other)=>{const option=document.createElement("option");option.value=String(other.cluster_id);option.textContent=`聚类 ${other.cluster_id}`;mergeSelect.append(option);});actions.append(mergeSelect);const mergeButton=document.createElement("button");mergeButton.type="button";mergeButton.className="cluster-action";mergeButton.dataset.clusterAction="merge";mergeButton.dataset.clusterId=String(cluster.cluster_id);mergeButton.textContent="合并到…";actions.append(mergeButton);const splitButton=document.createElement("button");splitButton.type="button";splitButton.className="cluster-action";splitButton.dataset.clusterAction="split";splitButton.dataset.clusterId=String(cluster.cluster_id);splitButton.textContent=`拆分${selectedInCluster?` · ${selectedInCluster}`:""}`;splitButton.disabled=!selectedInCluster;actions.append(splitButton);const outlierButton=document.createElement("button");outlierButton.type="button";outlierButton.className="cluster-action";outlierButton.dataset.clusterAction="outlier";outlierButton.dataset.clusterId=String(cluster.cluster_id);outlierButton.dataset.tone="danger";outlierButton.textContent="标记为离群";actions.append(outlierButton);card.append(actions);return card;}
   function renderCharacterClusters(){const scroll=els("character-scroll");const virtual=els("character-virtual");if(!scroll||!virtual)return;const clusters=effectiveClusters();const rowHeight=176;const viewport=Math.max(scroll.clientHeight,260);const start=Math.max(0,Math.floor(scroll.scrollTop/rowHeight)-2);const end=Math.min(clusters.length,start+Math.ceil(viewport/rowHeight)+5);virtual.style.height=`${clusters.length*rowHeight}px`;const fragment=document.createDocumentFragment();for(let index=start;index<end;index+=1)fragment.append(renderClusterCard(clusters[index],index,index*rowHeight,clusters));if(!clusters.length){const empty=document.createElement("div");empty.className="character-empty";empty.textContent=identityFaces.length?"暂无可显示的聚类":"当前报告没有人脸元数据";fragment.append(empty);}virtual.replaceChildren(fragment);observeCharacterCrops();}
   function pumpCharacterCrops(){while(activeCropLoads.size<IDENTITY_CROP_CONCURRENCY&&cropQueue.length){const image=cropQueue.shift();if(!image||image.dataset.cropLoaded||image.dataset.cropLoading)continue;const source=image.dataset.cropSource;if(!source)continue;image.dataset.cropLoading="true";activeCropLoads.add(image);const done=()=>{activeCropLoads.delete(image);image.dataset.cropLoaded="true";delete image.dataset.cropLoading;pumpCharacterCrops();};image.onload=done;image.onerror=done;image.src=source;}}
   function queueCharacterCrop(image){if(image.dataset.cropLoaded||image.dataset.cropLoading||image.dataset.cropQueued)return;image.dataset.cropQueued="true";cropQueue.push(image);pumpCharacterCrops();}
   function observeCharacterCrops(){if(cropObserver)cropObserver.disconnect();const images=[...document.querySelectorAll("#character-virtual img[data-crop-source]")];if(typeof IntersectionObserver!=="function"){images.forEach(queueCharacterCrop);return;}cropObserver=new IntersectionObserver((entries)=>{entries.forEach((entry)=>{if(entry.isIntersecting)queueCharacterCrop(entry.target);});},{root:els("character-scroll"),rootMargin:"120px"});images.forEach((image)=>cropObserver.observe(image));}
   function updateCharacterSummary(){const section=els("character-section");if(!section)return;section.hidden=!identityEnabled;const row=currentRow();const faces=facesForRow(row);const named=faces.filter(faceIsNamed).length;setText("character-summary",`${named} / ${faces.length} 张已命名`);const labels=faces.map((face)=>faceLabel(face)?.character).filter(Boolean);setText("character-current-name",labels.join("、"));setText("character-progress",`已命名 ${namedFaceCount()} / ${identityFaces.length}`);}
   function renderCharacterPanel(){if(!identityEnabled)return;updateCharacterSummary();renderCharacterClusters();}
   function openCharacterPanel(){if(!identityEnabled)return;lastFocus=document.activeElement;const panel=els("character-panel");const backdrop=els("character-backdrop");panel.hidden=false;backdrop.hidden=false;panel.setAttribute("aria-hidden","false");requestAnimationFrame(()=>panel.classList.add("is-open"));renderCharacterPanel();els("uncertainty-mode").focus();}
   function closeCharacterPanel(){const panel=els("character-panel");if(!panel||panel.hidden)return;const target=lastFocus instanceof HTMLElement?lastFocus:els("character-panel-open");target?.focus();panel.classList.remove("is-open");panel.hidden=true;els("character-backdrop").hidden=true;panel.setAttribute("aria-hidden","true");}
   function renderStudio(){const row=currentRow();const empty=!row;els("studio-title").textContent=row?(row.filename||row.sha16||"未命名图片"):"当前筛选没有图片";els("studio-meta").textContent=row?[row.sha16&&`SHA ${row.sha16}`,row.family_id&&`家族 ${row.family_id}`,row.width&&row.height?`${row.width} × ${row.height}`:null].filter(Boolean).join(" · "):"调整筛选条件或关闭仅看未审";if(!row){showStudioPlaceholder("当前筛选没有匹配的图片");els("action-belt").replaceChildren();els("score-grid").replaceChildren();els("studio-flags").replaceChildren();els("raw-fields").replaceChildren();els("original-link").hidden=true;els("copy-path").disabled=true;els("copy-sha").disabled=true;els("studio-family").disabled=true;updateCharacterSummary();setText("stage-label","无匹配图片");setText("stage-tier","—");renderDecisionBadge(els("stage-manual"),"");renderFilmstrip();return;}els("original-link").hidden=!fileUrl(row.abs_path);els("original-link").href=fileUrl(row.abs_path);els("copy-path").disabled=!row.abs_path;els("copy-sha").disabled=!row.sha16;els("studio-family").disabled=!row.family_id;els("studio-family").textContent=row.family_id||"未分配家族";setText("stage-label",row.filename||row.sha16||"图片");setText("stage-index",`${currentIndex()+1} / ${state.visible.length}`);setText("stage-tier",tierLabels[row.proposed_tier]||row.proposed_tier);renderDecisionBadge(els("stage-manual"),manualFor(row));renderScoreGrid(row);renderFlags(els("studio-flags"),row);setText("studio-proposal",tierLabels[row.proposed_tier]||row.proposed_tier);renderDecisionBadge(els("studio-decision"),manualFor(row));renderRawFields(row);renderActionBelt(row);updatePrivacy(row);updateCharacterSummary();if(stageKey!==rowKey(row)){stageKey=rowKey(row);mountStudioAsset(row);state.zoomed=false;state.panX=0;state.panY=0;applyZoom();}else applyZoom();renderFilmstrip();renderJournalPreview();schedulePrefetch();}
   let nameModalFocus=null;function openClusterNameModal(clusterId){const cluster=effectiveClusters().find((item)=>String(item.cluster_id)===String(clusterId));const modal=els("cluster-name-modal");const input=els("cluster-name-input");if(!cluster||!modal||!input)return;state.openClusterId=String(clusterId);nameModalFocus=document.activeElement;setText("cluster-name-meta",`${String(clusterId)==="outlier"?"离群 / 未知":`聚类 ${clusterId}`} · ${clusterFaceList(cluster).length} 张人脸`);input.value=clusterName(cluster);modal.hidden=false;input.focus();input.select();}
   function closeClusterNameModal(){const modal=els("cluster-name-modal");if(!modal||modal.hidden)return;modal.hidden=true;state.openClusterId=null;const target=nameModalFocus instanceof HTMLElement?nameModalFocus:els("character-panel-open");target?.focus();nameModalFocus=null;}
   function confirmClusterName(){if(state.openClusterId===null)return;const input=els("cluster-name-input");const name=input?.value.trim()||"";if(!name){input?.focus();return;}const cluster=effectiveClusters().find((item)=>String(item.cluster_id)===String(state.openClusterId));if(!cluster)return;const action=knownNames.has(name)?"confirm":"new";clusterFaceList(cluster).forEach((face)=>recordFaceLabel(face,action,name));recordClusterDecision(state.openClusterId,"name",{character:name,face_ids:clusterFaceList(cluster).map((face)=>face.face_id)});closeClusterNameModal();renderCharacterPanel();}
   function handleClusterAction(event){const target=event.target instanceof Element?event.target.closest("[data-cluster-action]"):null;if(!target)return;const clusterId=target.dataset.clusterId||"";const cluster=effectiveClusters().find((item)=>String(item.cluster_id)===String(clusterId));if(!cluster)return;const action=target.dataset.clusterAction;if(action==="name"){openClusterNameModal(clusterId);return;}if(action==="merge"){const card=target.closest(".cluster-card");const select=card?.querySelector(`[data-cluster-merge-select="${CSS.escape(clusterId)}"]`);const targetId=select?.value||"";if(!targetId){setText("character-queue-note","请先选择合并目标");select?.focus();return;}recordClusterDecision(clusterId,"merge",{target_cluster_id:targetId,face_ids:clusterFaceList(cluster).map((face)=>face.face_id)});renderCharacterPanel();return;}if(action==="split"){const selected=clusterFaceList(cluster).filter((face)=>state.selectedFaces.has(face.face_id));if(!selected.length)return;const newClusterId=`local-split-${Date.now().toString(36)}`;recordClusterDecision(clusterId,"split",{new_cluster_id:newClusterId,face_ids:selected.map((face)=>face.face_id)});selected.forEach((face)=>state.selectedFaces.delete(face.face_id));renderCharacterPanel();return;}if(action==="outlier"){recordClusterDecision(clusterId,"outlier",{face_ids:clusterFaceList(cluster).map((face)=>face.face_id)});renderCharacterPanel();}}
   function handleCharacterPanelClick(event){const target=event.target instanceof Element?event.target.closest("[data-panel-face-id]"):null;if(target){const faceId=target.dataset.panelFaceId||"";if(state.selectedFaces.has(faceId))state.selectedFaces.delete(faceId);else state.selectedFaces.add(faceId);renderCharacterClusters();return;}handleClusterAction(event);}
   function cycleFaces(direction){const row=currentRow();const faces=facesForRow(row);if(!faces.length)return;const active=document.activeElement instanceof HTMLElement?document.activeElement.dataset.faceId||"":"";const currentId=state.openFaceId||active;const currentIndex=faces.findIndex((face)=>face.face_id===currentId);const next=faces[(currentIndex+direction+faces.length)%faces.length];const button=els("face-overlay")?.querySelector(`[data-face-id="${CSS.escape(next.face_id)}"]`);button?.focus();}
   function jumpToIndex(index){if(!rows[index])return;state.currentKey=rowKey(rows[index]);state.mode="studio";els("studio-mode").setAttribute("aria-pressed","true");els("studio-mode").setAttribute("aria-selected","true");els("table-mode").setAttribute("aria-pressed","false");els("table-mode").setAttribute("aria-selected","false");els("studio-view").hidden=false;els("table-view").hidden=true;renderStudio();}
  function navigate(delta){if(!state.visible.length)return;const position=currentIndex();const next=Math.min(state.visible.length-1,Math.max(0,position+delta));if(next!==position){state.currentKey=rowKey(rows[state.visible[next]]);renderStudio();}}
  function actionForCurrent(action){const row=currentRow();if(!row)return;if(action==="undo"){undoCurrent(row);return;}const key=rowKey(row);const previous=journal.decisions[key]||null;journal.decisions[key]=action;journal.history.push({sha16:key,previous,action});journal.entries.push({sha16:key,filename:row.filename,action,manual_decision:action,proposed_tier:row.proposed_tier,timestamp:new Date().toISOString()});saveJournal();refreshView(key);setText("belt-status","已保存到本地");}
  function undoCurrent(row){const key=rowKey(row);let target=null;for(let index=journal.history.length-1;index>=0;index-=1){const entry=journal.history[index];if(entry.sha16===key&&!entry.undone){target=entry;entry.undone=true;break;}}if(!target){setText("belt-status","当前图片没有可撤销动作");return;}if(target.previous)journal.decisions[key]=target.previous;else delete journal.decisions[key];journal.entries.push({sha16:key,filename:row.filename,action:"undo",manual_decision:target.previous||"",proposed_tier:row.proposed_tier,timestamp:new Date().toISOString()});saveJournal();refreshView(key);}
  function renderTableRow(index){const row=rows[index];const tr=document.createElement("tr");tr.className="data-row";tr.dataset.index=String(index);tr.dataset.key=rowKey(row);if(rowKey(row)===state.currentKey)tr.classList.add("is-current");const thumbCell=document.createElement("td");const thumbButton=document.createElement("button");thumbButton.type="button";thumbButton.className="table-thumb";thumbButton.dataset.action="preview";thumbButton.dataset.index=String(index);thumbButton.setAttribute("aria-label",`预览：${row.filename||row.sha16||"图片"}`);const source=thumbAsset(row);if(source){const image=document.createElement("img");image.loading="lazy";image.decoding="async";image.src=source;image.alt=row.filename||"图片缩略图";image.dataset.media="table";image.dataset.fallback="";thumbButton.append(image);}else{const placeholder=document.createElement("span");placeholder.className="table-placeholder";placeholder.textContent="无缩略图";thumbButton.append(placeholder);}thumbButton.classList.toggle("is-private",privateRow(row)&&!state.showNsfw&&!state.revealed.has(rowKey(row)));thumbCell.append(thumbButton);tr.append(thumbCell);const nameCell=document.createElement("td");const name=document.createElement("button");name.type="button";name.className="filename-button";name.dataset.action="open";name.dataset.index=String(index);name.textContent=row.filename||"未命名";name.title=row.filename||"";const sha=document.createElement("span");sha.className="table-sha";sha.textContent=row.sha16||"—";nameCell.append(name,sha);tr.append(nameCell);const familyCell=document.createElement("td");const family=document.createElement("button");family.type="button";family.className="table-family-button";family.dataset.action="family";family.dataset.family=row.family_id;family.textContent=row.family_id||"未分配";familyCell.append(family);tr.append(familyCell);scoreFields.forEach((field)=>{const cell=document.createElement("td");cell.className="col-score";const value=document.createElement("span");value.className="number";value.textContent=formatField(field,row[field]);if(!finite(row[field])&&numericFields.has(field))value.classList.add("empty");cell.append(value);tr.append(cell);});const flagsCell=document.createElement("td");flagsCell.className="col-flags";const flags=document.createElement("div");flags.className="table-badges";row.flags.forEach((flag)=>{const badge=document.createElement("span");badge.className="badge";badge.dataset.flag=flag;badge.textContent=flagLabels[flag]||flag;flags.append(badge);});if(!row.flags.length){const badge=document.createElement("span");badge.className="badge";badge.dataset.flag="none";badge.textContent="无";flags.append(badge);}flagsCell.append(flags);tr.append(flagsCell);const tierCell=document.createElement("td");tierCell.className="col-tier";const tiers=document.createElement("div");tiers.className="table-badges";const tier=document.createElement("span");tier.className="tier-badge";tier.textContent=tierLabels[row.proposed_tier]||row.proposed_tier;tiers.append(tier);const manual=manualFor(row);if(manual){const manualBadge=document.createElement("span");manualBadge.className="manual-badge";manualBadge.textContent=`人工：${actionLabel(manual)}`;tiers.append(manualBadge);}tierCell.append(tiers);tr.append(tierCell);return tr;}
  function scheduleTableRender(){if(tableRaf)return;tableRaf=requestAnimationFrame(()=>{tableRaf=0;renderVirtualTable();});}
  function renderVirtualTable(){const scroll=els("table-scroll");const body=els("score-rows");const list=state.visible;const rowHeight=88;const viewport=Math.max(scroll.clientHeight,300);const start=Math.max(0,Math.floor(Math.max(0,scroll.scrollTop-44)/rowHeight)-8);const end=Math.min(list.length,start+Math.ceil(viewport/rowHeight)+16);const fragment=document.createDocumentFragment();const top=document.createElement("tr");top.className="virtual-spacer";const topCell=document.createElement("td");topCell.colSpan=scoreFields.length+5;topCell.style.height=`${start*rowHeight}px`;top.append(topCell);fragment.append(top);for(let cursor=start;cursor<end;cursor+=1)fragment.append(renderTableRow(list[cursor]));const bottom=document.createElement("tr");bottom.className="virtual-spacer";const bottomCell=document.createElement("td");bottomCell.colSpan=scoreFields.length+5;bottomCell.style.height=`${Math.max(0,(list.length-end)*rowHeight)}px`;bottom.append(bottomCell);fragment.append(bottom);body.replaceChildren(fragment);els("empty-state").hidden=list.length!==0;setText("visible-count",`显示 ${list.length.toLocaleString("zh-CN")} / ${rows.length.toLocaleString("zh-CN")} 条 · 窗口 ${start + 1}–${end}`);document.querySelectorAll("th[data-sort-column]").forEach((header)=>{const field=header.dataset.sortColumn;const active=field===state.sortField;header.classList.toggle("is-active",active);header.setAttribute("aria-sort",active?(state.sortDirection===1?"ascending":"descending"):"none");const indicator=header.querySelector(".sort-indicator");if(indicator)indicator.textContent=active?(state.sortDirection===1?"▲":"▼"):"↕";});}
  function familyRows(familyId){const family=families[familyId];const ids=family&&Array.isArray(family.members)?family.members:rows.filter((row)=>row.family_id===familyId).map((row)=>row.sha16);return ids.map((id)=>rows.find((row)=>row.sha16===id)).filter(Boolean);}
  function openFamily(familyId){lastFocus=document.activeElement;const panel=els("family-panel");const family=families[familyId]||{};const members=familyRows(familyId);setText("panel-kicker","家族详情");setText("family-title",familyId||"未分配家族");setText("family-meta",`${members.length===1?"单成员家族":members.length?"多成员家族":"空家族"} · ${members.length} 个成员 · 冠军 ${family.champion||"未提供"} · 备选 ${family.runner_up||"未提供"}`);const scroll=els("drawer-scroll");const strip=document.createElement("div");strip.className="family-strip";strip.dataset.state=members.length===1?"singleton":members.length?"populated":"empty";members.forEach((row)=>{const card=document.createElement("article");card.className="family-card";if(row.sha16===family.champion)card.classList.add("champion");const button=document.createElement("button");button.type="button";button.className="table-thumb";button.dataset.action="family-jump";button.dataset.index=String(row.__index);const source=thumbAsset(row);if(source){const image=document.createElement("img");image.src=source;image.alt=row.filename||"家族成员";image.dataset.media="drawer";image.dataset.fallback="";button.append(image);}else{const placeholder=document.createElement("span");placeholder.className="table-placeholder";placeholder.textContent="无图";button.append(placeholder);}card.append(button);const name=document.createElement("strong");name.textContent=row.filename||row.sha16||"未命名";card.append(name);if(row.sha16===family.champion){const tag=document.createElement("span");tag.className="mini-badge";tag.textContent="冠军";card.append(tag);}else if(row.sha16===family.runner_up){const tag=document.createElement("span");tag.className="mini-badge";tag.textContent="家族备选";card.append(tag);}strip.append(card);});if(!members.length){const empty=document.createElement("p");empty.className="empty-state";empty.textContent="当前报告没有家族成员";strip.append(empty);}const note=document.createElement("p");note.className="drawer-note";note.textContent="家族信息来自离线管线；单成员家族仍保留用于审计。";scroll.replaceChildren(strip,note);panel.hidden=false;panel.setAttribute("aria-hidden","false");requestAnimationFrame(()=>panel.classList.add("is-open"));els("family-close").focus();}
  function openDetail(row){
    const panel=els("family-panel");
    lastFocus=document.activeElement;setText("panel-kicker","图片详情");setText("family-title",row.filename||row.sha16||"图片详情");setText("family-meta",[row.family_id&&`家族 ${row.family_id}`,`处置：${tierLabels[row.proposed_tier]||row.proposed_tier}`,row.flags.length?`标记 ${row.flags.map((flag)=>flagLabels[flag]||flag).join("、")}`:"无标记"].join(" · "));
    const scroll=els("drawer-scroll");const preview=document.createElement("div");preview.className="drawer-preview";const source=thumbAsset(row);
    if(source){const image=document.createElement("img");image.src=source;image.alt=row.filename||"图片预览";image.dataset.media="drawer";image.dataset.fallback="";preview.append(image);}else preview.textContent="无缩略图";
    const actions=document.createElement("div");actions.className="drawer-actions";const link=document.createElement("a");link.className="original-link";link.textContent="打开原图";link.href=fileUrl(row.abs_path);link.target="_blank";link.rel="noreferrer";actions.append(link);
    ["abs_path","sha16"].forEach((field)=>{const button=document.createElement("button");button.type="button";button.className="copy-button";button.dataset.action=`copy:${field}`;button.dataset.value=String(row[field]||"");button.textContent=`复制 ${field==="abs_path"?"路径":"SHA"}`;actions.append(button);});
    const note=document.createElement("p");note.className="drawer-note";note.textContent="处置字段只是未校准的人工复核提案；模型分数仅适合在当前语料内相对比较。";
    const section=document.createElement("section");section.className="detail-section";
    const rawFields=["sha16","abs_path","path_rel","filename","width","height","filesize","phash","family_id",...scoreFields,"flags","proposed_tier","thumb_rel"];
    const heading=document.createElement("h3");heading.textContent=`全部原始字段（${rawFields.length} 项）`;
    const fields=document.createElement("dl");fields.className="detail-fields";
    rawFields.forEach((field)=>{const wrapper=document.createElement("div");wrapper.className="detail-field";const label=document.createElement("dt");label.textContent=fieldLabels[field]||field;const value=document.createElement("dd");value.textContent=formatField(field,row[field]);value.title=`原始值：${rawValue(row[field])}`;wrapper.append(label,value);fields.append(wrapper);});
    section.append(heading,fields);scroll.replaceChildren(preview,actions,note,section);panel.hidden=false;panel.setAttribute("aria-hidden","false");requestAnimationFrame(()=>panel.classList.add("is-open"));els("family-close").focus();
  }
  function closeFamily(){const panel=els("family-panel");if(panel.hidden)return;const target=lastFocus instanceof HTMLElement?lastFocus:els("search-input");target?.focus();panel.classList.remove("is-open");panel.hidden=true;panel.setAttribute("aria-hidden","true");lastFocus=null;}
  function openLightbox(row){lastFocus=document.activeElement;setText("lightbox-title",row.filename||"图片预览");setText("lightbox-meta",[row.family_id&&`家族 ${row.family_id}`,row.sha16&&`SHA ${row.sha16}`,row.width&&row.height?`${row.width} × ${row.height}`:null].filter(Boolean).join(" · ")||"无元数据");const preview=els("lightbox-preview");preview.replaceChildren();const source=thumbAsset(row);if(source){const image=document.createElement("img");image.src=source;image.alt=row.filename||"图片预览";image.dataset.media="lightbox";image.dataset.fallback="";image.classList.toggle("is-private",privateRow(row)&&!state.showNsfw&&!state.revealed.has(rowKey(row)));preview.append(image);}else preview.textContent="无预览";setText("privacy-note",privateRow(row)&&!state.showNsfw&&!state.revealed.has(rowKey(row))?"NSFW 内容默认模糊，点击工作台中的“点击显示”后查看。":"");const link=els("lightbox-original");link.hidden=!fileUrl(row.abs_path);link.href=fileUrl(row.abs_path);els("lightbox").hidden=false;els("lightbox").setAttribute("aria-hidden","false");els("lightbox-close").focus();}
   function closeModal(id){const modal=els(id);if(!modal||modal.hidden)return;const target=lastFocus instanceof HTMLElement&&lastFocus!==document.body&&!modal.contains(lastFocus)?lastFocus:els("search-input");target?.focus();modal.hidden=true;modal.setAttribute("aria-hidden","true");lastFocus=null;}
  function openModal(id){lastFocus=document.activeElement;const modal=els(id);modal.hidden=false;modal.setAttribute("aria-hidden","false");const close=modal.querySelector(".close-button");close?.focus();}
  function renderSpotlightEmpty(container,label){const empty=document.createElement("div");empty.className="empty-state";empty.textContent=`暂无${label}图片`;container.replaceChildren(empty);}
  function spotlightButton(row,label){const button=document.createElement("button");button.type="button";button.className="jump-button";button.dataset.action="spotlight-jump";button.dataset.index=String(row.__index);button.textContent=row.filename||row.sha16||"未命名";button.title=`跳转到${label}`;return button;}
  function renderSpotlights(){const disagreement=rows.filter((row)=>finite(row.disagreement)).sort((a,b)=>Number(b.disagreement)-Number(a.disagreement)).slice(0,12);const gaming=rows.filter((row)=>finite(row.gaming_delta)&&Number(row.gaming_delta)>0).sort((a,b)=>Number(b.gaming_delta)-Number(a.gaming_delta)).slice(0,12);const uncertain=rows.filter((row)=>row.flags.includes("uncertain")).sort((a,b)=>(finite(b.consensus_z)?Number(b.consensus_z):-Infinity)-(finite(a.consensus_z)?Number(a.consensus_z):-Infinity)).slice(0,12);const renderList=(id,items,label,metric)=>{const list=els(id);if(!items.length){renderSpotlightEmpty(list,label);return;}const fragment=document.createDocumentFragment();items.forEach((row)=>{const item=document.createElement("article");item.className="spotlight-item";const head=document.createElement("div");head.className="spotlight-head";head.append(spotlightButton(row,label));const value=document.createElement("span");value.className="spotlight-value";value.textContent=metric(row);head.append(value);item.append(head);fragment.append(item);});list.replaceChildren(fragment);};renderList("disagreement-list",disagreement,"分歧",(row)=>`Δ ${numberText(row.disagreement)}`);renderList("gaming-list",gaming,"刷分审计",(row)=>`+${numberText(row.gaming_delta)}`);renderList("uncertain-list",uncertain,"不确定",(row)=>`Z ${numberText(row.consensus_z)}`);}
  function copyText(value,button){const text=String(value||"");const finish=(success)=>{const previous=button.textContent;button.textContent=success?"已复制":"复制失败";window.setTimeout(()=>{button.textContent=previous;},1000);};if(navigator.clipboard&&typeof navigator.clipboard.writeText==="function"){navigator.clipboard.writeText(text).then(()=>finish(true)).catch(()=>fallbackCopy(text,finish));}else fallbackCopy(text,finish);}
  function fallbackCopy(text,finish){const textarea=document.createElement("textarea");textarea.value=text;textarea.readOnly=true;textarea.style.position="fixed";textarea.style.opacity="0";document.body.append(textarea);textarea.select();let copied=false;try{copied=document.execCommand("copy");}catch(_error){copied=false;}textarea.remove();finish(copied);}
  function download(name,content,type){const blob=new Blob([content],{type});const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=name;document.body.append(link);link.click();link.remove();window.setTimeout(()=>URL.revokeObjectURL(url),0);}
   const csvCell=(value)=>`"${String(value??"").replaceAll('"','""')}"`;function exportJson(){download(`image-review-${fingerprint}.json`,JSON.stringify({version:1,fingerprint,title:document.getElementById("brand-title")?.textContent||"",exported_at:new Date().toISOString(),decisions:journal.decisions,entries:journal.entries},null,2),"application/json");}function exportCsv(){const header=["sha16","filename","action","manual_decision","proposed_tier","timestamp"];const lines=[header.map(csvCell).join(",")];journal.entries.forEach((entry)=>lines.push([entry.sha16,entry.filename,entry.action,entry.manual_decision,entry.proposed_tier,entry.timestamp].map(csvCell).join(",")));download(`image-review-${fingerprint}.csv`,lines.join("\r\n"),"text/csv;charset=utf-8");}function exportCharacterLabels(){download("character_labels.json",JSON.stringify(characterLabelsPayload(),null,2),"application/json");setText("journal-import-status","人物标签已导出");}function importCharacterLabels(file){if(!file)return;const reader=new FileReader();reader.onload=()=>{try{const parsed=JSON.parse(String(reader.result||""));if(!parsed||typeof parsed!=="object"||parsed.version!==1||parsed.source!=="review-studio"||String(parsed.corpus_fingerprint)!==fingerprint||!Array.isArray(parsed.labels))throw new Error("标签文件与当前语料不匹配");let imported=0;parsed.labels.forEach((raw)=>{if(!raw||typeof raw!=="object"||!LABEL_ACTIONS.has(raw.action))return;const face=faceById.get(String(raw.face_id||""));if(!face)return;const label={face_id:face.face_id,image_sha16:String(raw.image_sha16||face.image_sha16||""),character:String(raw.character||""),action:raw.action};journal.faceLabels[face.face_id]=label;if(label.character)knownNames.add(label.character);imported+=1;});journal.entries.push({kind:"face",action:"import",count:imported,timestamp:new Date().toISOString()});saveJournal();renderFaceOverlay();renderCharacterPanel();renderJournalPreview();renderJournalExport();setText("journal-import-status",`已导入 ${imported} 张人脸标签`);}catch(error){setText("journal-import-status",error instanceof Error?error.message:"标签文件无法读取");}};reader.onerror=()=>setText("journal-import-status","标签文件无法读取");reader.readAsText(file,"utf-8");}function undoRecentCharacter(){for(let index=journal.faceHistory.length-1;index>=0;index-=1){const entry=journal.faceHistory[index];if(!entry.undone){if(undoFaceLabel(entry.face_id)){setText("journal-import-status","已撤销最近人物动作");return;}}}setText("journal-import-status","暂无可撤销的人物动作");}
  function schedulePrefetch(){const position=currentIndex();if(position<0)return;const generation=++prefetch.generation;prefetch.queue=[];prefetch.handles.forEach((image)=>{image.onload=null;image.onerror=null;image.src="";});prefetch.handles.clear();for(let distance=1;distance<=PREFETCH_K;distance+=1){[position+distance,position-distance].forEach((order)=>{if(order>=0&&order<state.visible.length){assetCandidates(rows[state.visible[order]]).forEach((source)=>prefetch.queue.push({source,generation}));}});}const pump=()=>{if(generation!==prefetch.generation)return;while(prefetch.active.size<PREFETCH_CONCURRENCY&&prefetch.queue.length){const item=prefetch.queue.shift();if(!item||item.generation!==generation)continue;const image=new Image();prefetch.active.add(image);prefetch.handles.add(image);const done=()=>{prefetch.active.delete(image);prefetch.handles.delete(image);pump();};image.onload=async()=>{if(typeof image.decode==="function"){try{await image.decode();}catch(_error){}}done();};image.onerror=done;image.src=item.source;}};pump();const idle=window.requestIdleCallback||((callback)=>window.setTimeout(callback,120));idle(()=>warmViewport(generation),{timeout:500});}
  function warmViewport(generation){if(generation!==prefetch.generation)return;const scroll=els("table-scroll");const center=Math.floor(Math.max(0,scroll.scrollTop-44)/88);for(let offset=-8;offset<=8;offset+=1){const index=state.visible[center+offset];if(index!==undefined)assetCandidates(rows[index]).slice(-1).forEach((source)=>{const image=new Image();image.decoding="async";image.src=source;});}}
   function setMode(mode){state.mode=mode;const studio=mode==="studio";const table=mode==="table";const grouping=mode==="grouping"&&groupingEnabled;els("studio-view").hidden=!studio;els("table-view").hidden=!table;els("character-grouping-view").hidden=!grouping;els("studio-mode").setAttribute("aria-pressed",String(studio));els("studio-mode").setAttribute("aria-selected",String(studio));els("table-mode").setAttribute("aria-pressed",String(table));els("table-mode").setAttribute("aria-selected",String(table));els("grouping-mode").setAttribute("aria-pressed",String(grouping));els("grouping-mode").setAttribute("aria-selected",String(grouping));if(table)scheduleTableRender();else if(studio)renderStudio();else renderGroupingView();}
   function clearFilters(){state.search="";state.tier=null;state.flags.clear();state.onlyUnreviewed=false;state.groupCharacter=null;els("search-input").value="";els("only-unreviewed").checked=false;refreshView();}
  function toggleFullscreen(){if(document.fullscreenElement){document.exitFullscreen?.();}else els("preview-stage").requestFullscreen?.();}
  function handleTableClick(event){const target=event.target instanceof Element?event.target.closest("[data-action],.sort-button,.active-filter,.clear-button"):null;if(!target)return;if(target.classList.contains("sort-button")){const field=target.dataset.sort||"consensus_z";if(state.sortField===field)state.sortDirection*=-1;else{state.sortField=field;state.sortDirection=field==="consensus_z"?-1:1;}refreshView();return;}const action=target.dataset.action;const index=Number(target.dataset.index);if(action==="preview"){jumpToIndex(index);return;}if(action==="open"){jumpToIndex(index);return;}if(action==="family"){openFamily(target.dataset.family||"");return;}if(action==="family-jump"||action==="spotlight-jump"){jumpToIndex(index);closeFamily();return;}if(action&&action.startsWith("copy:")){copyText(target.dataset.value||"",target);return;}if(target.dataset.clear){const clear=target.dataset.clear;if(clear==="all")clearFilters();else if(clear==="search"){state.search="";els("search-input").value="";refreshView();}else if(clear==="tier"){state.tier=null;refreshView();}else if(clear==="unreviewed"){state.onlyUnreviewed=false;els("only-unreviewed").checked=false;refreshView();}else if(clear.startsWith("flag:")){state.flags.delete(clear.slice(5));refreshView();}}}
  function handleMediaError(event){const image=event.target instanceof HTMLImageElement?event.target:null;if(!image||!image.dataset.media)return;const fallback=image.dataset.fallback;if(fallback&&!image.dataset.fellBack){image.dataset.fellBack="true";image.src=fallback;return;}const parent=image.parentElement;if(parent){const placeholder=document.createElement("span");placeholder.className=parent.classList.contains("table-thumb")?"table-placeholder":"film-placeholder";placeholder.textContent="文件缺失";parent.replaceChildren(placeholder);}}
  function revealCurrent(){const row=currentRow();if(!row)return;state.revealed.add(rowKey(row));updatePrivacy(row);renderFilmstrip();scheduleTableRender();}
  function handleStagePointerDown(event){if(!state.zoomed||event.button!==0)return;const canvas=els("preview-canvas");const startX=event.clientX;const startY=event.clientY;const baseX=state.panX;const baseY=state.panY;canvas.setPointerCapture?.(event.pointerId);const move=(moveEvent)=>{state.panX=baseX+moveEvent.clientX-startX;state.panY=baseY+moveEvent.clientY-startY;applyZoom();};const up=()=>{canvas.removeEventListener("pointermove",move);canvas.removeEventListener("pointerup",up);canvas.removeEventListener("pointercancel",up);};canvas.addEventListener("pointermove",move);canvas.addEventListener("pointerup",up);canvas.addEventListener("pointercancel",up);}
  function toggleZoom(){state.zoomed=!state.zoomed;if(!state.zoomed){state.panX=0;state.panY=0;}applyZoom();}
   function handleKey(event){const tag=event.target instanceof HTMLElement?event.target.tagName.toLowerCase():"";if(event.key==="Escape"){if(!els("face-popover").hidden){closeFacePopover();return;}if(!els("cluster-name-modal").hidden){closeClusterNameModal();return;}if(!els("help-modal").hidden)closeModal("help-modal");else if(!els("journal-modal").hidden)closeModal("journal-modal");else if(!els("legend-modal").hidden)closeModal("legend-modal");else if(!els("lightbox").hidden)closeModal("lightbox");else if(!els("family-panel").hidden)closeFamily();else if(!els("character-panel").hidden)closeCharacterPanel();return;}if(tag==="input"||tag==="textarea"||tag==="select"||event.target?.isContentEditable)return;if(event.key==="?"){event.preventDefault();openModal("help-modal");return;}if(state.mode!=="studio")return;if(identityEnabled&&event.key==="Tab"&&els("face-popover").hidden){event.preventDefault();cycleFaces(event.shiftKey?-1:1);return;}if(identityEnabled&&event.key.toLowerCase()==="n"){const face=facesForRow(currentRow()).find((item)=>!faceIsNamed(item));if(face){event.preventDefault();openFacePopover(face.face_id);}return;}if(event.key==="ArrowLeft"||event.key.toLowerCase()==="j"){event.preventDefault();navigate(-1);return;}if(event.key==="ArrowRight"||event.key.toLowerCase()==="k"){event.preventDefault();navigate(1);return;}const action=actionDefs.find((item)=>item.key===event.key);if(action){event.preventDefault();actionForCurrent(action.id);return;}if(event.key.toLowerCase()==="u"){event.preventDefault();actionForCurrent("undo");return;}if(event.key===" "){event.preventDefault();toggleZoom();return;}if(event.key.toLowerCase()==="f"){event.preventDefault();toggleFullscreen();}}
  function handleActionClick(event){const target=event.target instanceof Element?event.target.closest("[data-action]"):null;if(!target)return;const action=target.dataset.action;if(action==="jump"){jumpToIndex(Number(target.dataset.index));return;}if(action==="undo"||actionDefs.some((item)=>item.id===action)){actionForCurrent(action);return;}}
   function init(){document.querySelectorAll('[data-optional-column="qrealign"]').forEach((node)=>{node.hidden=!hasQrealign;});els("show-nsfw").addEventListener("change",(event)=>{state.showNsfw=event.target.checked;const row=currentRow();if(row)updatePrivacy(row);renderFilmstrip();scheduleTableRender();});els("only-unreviewed").addEventListener("change",(event)=>{state.onlyUnreviewed=event.target.checked;refreshView();});els("search-input").addEventListener("input",(event)=>{state.search=event.target.value.trim();refreshView();});els("tier-board").addEventListener("click",(event)=>{const button=event.target.closest("[data-tier]");if(!button)return;state.tier=state.tier===button.dataset.tier?null:button.dataset.tier;refreshView();});els("flag-filters").addEventListener("click",(event)=>{const button=event.target.closest("[data-flag]");if(!button)return;const flag=button.dataset.flag;if(state.flags.has(flag))state.flags.delete(flag);else state.flags.add(flag);refreshView();});els("active-filters").addEventListener("click",handleTableClick);els("action-belt").addEventListener("click",handleActionClick);els("filmstrip-list").addEventListener("click",handleActionClick);els("spotlights").addEventListener("click",handleTableClick);els("score-table").addEventListener("click",handleTableClick);els("family-panel").addEventListener("click",handleTableClick);els("table-scroll").addEventListener("scroll",scheduleTableRender,{passive:true});els("studio-mode").addEventListener("click",()=>setMode("studio"));els("table-mode").addEventListener("click",()=>setMode("table"));els("journal-open").addEventListener("click",()=>{renderJournalPreview();renderJournalExport();openModal("journal-modal");});els("legend-open").addEventListener("click",()=>openModal("legend-modal"));els("help-open").addEventListener("click",()=>openModal("help-modal"));els("journal-close").addEventListener("click",()=>closeModal("journal-modal"));els("legend-close").addEventListener("click",()=>closeModal("legend-modal"));els("help-close").addEventListener("click",()=>closeModal("help-modal"));els("lightbox-close").addEventListener("click",()=>closeModal("lightbox"));els("family-close").addEventListener("click",closeFamily);document.querySelectorAll("[data-close]").forEach((node)=>node.addEventListener("click",()=>{const name=node.dataset.close;closeModal(`${name}-modal`);if(name==="lightbox")closeModal("lightbox");}));els("export-json").addEventListener("click",exportJson);els("export-csv").addEventListener("click",exportCsv);els("privacy-reveal").addEventListener("click",revealCurrent);els("zoom-toggle").addEventListener("click",toggleZoom);els("fullscreen-toggle").addEventListener("click",toggleFullscreen);els("preview-canvas").addEventListener("pointerdown",handleStagePointerDown);els("copy-path").addEventListener("click",()=>{const row=currentRow();if(row)copyText(row.abs_path,els("copy-path"));});els("copy-sha").addEventListener("click",()=>{const row=currentRow();if(row)copyText(row.sha16,els("copy-sha"));});els("original-link").addEventListener("click",(event)=>{if(!event.currentTarget.href||event.currentTarget.getAttribute("href")==="#")event.preventDefault();});els("studio-family").addEventListener("click",()=>{const row=currentRow();if(row)openFamily(row.family_id);});document.addEventListener("keydown",handleKey);document.addEventListener("error",handleMediaError,true);document.addEventListener("fullscreenchange",()=>{setText("fullscreen-toggle",document.fullscreenElement?"退出全屏":"全屏");});renderStats();renderJournalPreview();refreshView();}
   function renderJournalExport(){const container=els("journal-export");const fragment=document.createDocumentFragment();journal.entries.slice().reverse().forEach((entry)=>{const line=document.createElement("div");line.className="journal-export-row";const time=document.createElement("span");time.textContent=entry.timestamp||"—";const name=document.createElement("span");name.textContent=entry.kind==="face"?entry.face_id:entry.kind==="cluster"?`聚类 ${entry.cluster_id}`:entry.filename||entry.sha16||"—";const action=document.createElement("span");action.textContent=journalEntryLabel(entry);line.append(time,name,action);fragment.append(line);});if(!journal.entries.length){const empty=document.createElement("p");empty.className="empty-state";empty.textContent="暂无动作日志";fragment.append(empty);}container.replaceChildren(fragment);}
   function initializeIdentityLayer(){const section=els("character-section");if(!identityEnabled){if(section)section.hidden=true;return;}section.hidden=false;els("face-overlay").addEventListener("click",(event)=>{const target=event.target instanceof Element?event.target.closest("[data-face-id]"):null;if(target)openFacePopover(target.dataset.faceId||"");});els("face-popover-close").addEventListener("click",closeFacePopover);els("face-confirm").addEventListener("click",()=>facePopoverAction("confirm"));els("face-new").addEventListener("click",()=>facePopoverAction("new"));els("face-ignore").addEventListener("click",()=>facePopoverAction("ignore"));els("face-wrong-box").addEventListener("click",()=>facePopoverAction("wrong_box"));els("face-character-name").addEventListener("keydown",(event)=>{if(event.key==="Enter"){event.preventDefault();facePopoverAction("new");}});document.addEventListener("pointerdown",(event)=>{const target=event.target instanceof Node?event.target:null;const popover=els("face-popover");if(!popover.hidden&&target&&!popover.contains(target)&&!els("face-overlay").contains(target))closeFacePopover();});els("character-panel-open").addEventListener("click",openCharacterPanel);els("character-close").addEventListener("click",closeCharacterPanel);els("character-backdrop").addEventListener("click",closeCharacterPanel);els("character-scroll").addEventListener("scroll",renderCharacterClusters,{passive:true});els("character-virtual").addEventListener("click",handleCharacterPanelClick);els("uncertainty-mode").addEventListener("change",(event)=>{state.uncertaintyFirst=event.target.checked;setText("character-queue-note",state.uncertaintyFirst?"当前按不确定度优先：低聚类置信度、边际接近零、单成员和低检测分数。":"按聚类规模排序；打开待确认优先可先处理最有信息量的人脸。");renderCharacterPanel();});els("cluster-name-close").addEventListener("click",closeClusterNameModal);els("cluster-name-confirm").addEventListener("click",confirmClusterName);els("cluster-name-modal").addEventListener("click",(event)=>{if(event.target instanceof Element&&event.target.dataset.close==="cluster-name-modal")closeClusterNameModal();});els("export-character-labels").addEventListener("click",exportCharacterLabels);els("import-character-labels").addEventListener("click",()=>els("character-labels-file").click());els("character-labels-file").addEventListener("change",(event)=>{const input=event.target;const file=input.files?.[0];importCharacterLabels(file||null);input.value="";});els("undo-character").addEventListener("click",undoRecentCharacter);els("show-nsfw").addEventListener("change",renderCharacterPanel);els("studio-image").addEventListener("load",renderFaceOverlay);if(typeof ResizeObserver==="function"){faceResizeObserver=new ResizeObserver(renderFaceOverlay);faceResizeObserver.observe(els("preview-canvas"));faceResizeObserver.observe(els("studio-image"));}window.addEventListener("resize",()=>{renderFaceOverlay();if(!els("face-popover").hidden)positionFacePopover(els("face-overlay")?.querySelector(`[data-face-id="${CSS.escape(state.openFaceId||"")}"]`));},{passive:true});renderCharacterPanel();renderFaceOverlay();}
   function groupingRowsFor(name){if(name==="未定")return rows.filter((row)=>groupingUnassigned(row));return rows.filter((row)=>(groupingImageRoles.get(row.sha16)||[]).includes(name));}function groupingFaceStats(name){const faces=[...groupingFaceById.values()].filter((face)=>name==="未定"?face.decision!=="assigned":face.character===name&&face.decision==="assigned");const sims=faces.map((face)=>face.sim).filter(finite);const margins=faces.map((face)=>face.margin).filter(finite);return {faces:faces.length,mean:sims.length?sims.reduce((sum,value)=>sum+Number(value),0)/sims.length:null,min:margins.length?Math.min(...margins):null};}function renderGroupingBadges(row){const container=els("preview-character-badges");if(!container)return;if(!groupingEnabled||!row){container.hidden=true;container.replaceChildren();return;}const roles=groupingImageRoles.get(row.sha16)||[];const display=[...new Set(roles.map((role)=>groupingAssignedNames.has(role)?role:"未定"))];container.replaceChildren();display.forEach((role)=>{const badge=document.createElement("span");badge.className="character-image-badge";badge.classList.toggle("is-unassigned",role==="未定");badge.textContent=role;container.append(badge);});container.hidden=!display.length;}function groupingCardButton(entry,unassigned){const main=document.createElement("button");main.type="button";main.className="grouping-card";main.dataset.groupCharacter=entry.name;main.setAttribute("aria-pressed",String(state.groupCharacter===entry.name));main.classList.toggle("is-selected",state.groupCharacter===entry.name);main.classList.toggle("is-unassigned",unassigned);const head=document.createElement("span");head.className="grouping-card-head";const title=document.createElement("h3");title.textContent=entry.name;const count=document.createElement("strong");count.className="grouping-card-count";count.textContent=String(entry.imageCount);head.append(title,count);main.append(head);const meta=document.createElement("span");meta.className="grouping-card-meta";const stats=groupingFaceStats(entry.name);[["人脸",stats.faces||entry.faceCount],["平均相似度",numberText(stats.mean??entry.meanSim)],["最小间隔",numberText(stats.min??entry.minMargin)],["筛选队列",groupingRowsFor(entry.name).length]].forEach(([label,value])=>{const metric=document.createElement("span");metric.className="grouping-metric";const small=document.createElement("small");small.textContent=String(label);const strong=document.createElement("strong");strong.textContent=String(value);metric.append(small,strong);meta.append(metric);});main.append(meta);const note=document.createElement("span");note.className="grouping-card-note";note.textContent=state.groupCharacter===entry.name?"已筛选 · 点击回到审阅台":"点击筛选图片与导航队列";main.append(note);return main;}function renderGroupingView(){const view=els("character-grouping-view");const tab=els("grouping-mode");if(!view||!tab)return;tab.hidden=!groupingEnabled;view.hidden=state.mode!=="grouping";if(!groupingEnabled)return;const cards=els("grouping-cards");const fragment=document.createDocumentFragment();groupingCharacters.forEach((entry)=>fragment.append(groupingCardButton(entry,false)));const unassignedRows=groupingRowsFor("未定");const unassignedStats=groupingFaceStats("未定");fragment.append(groupingCardButton({name:"未定",imageCount:unassignedRows.length,faceCount:unassignedStats.faces,meanSim:unassignedStats.mean,minMargin:unassignedStats.min},true));cards.replaceChildren(fragment);setText("grouping-thresholds",`阈值：min_sim ${numberText(groupingThresholds.min_sim)} · min_margin ${numberText(groupingThresholds.min_margin)} · 来源：character-groups.json`);setText("grouping-status-text",`${state.groupCharacter?`当前：${state.groupCharacter} · `:""}筛选队列 ${state.groupCharacter?state.visible.length:rows.length} / ${rows.length} 张 · 卡片图片计数按角色集合去重`);const toggle=els("grouping-unassigned-toggle");if(toggle)toggle.checked=state.groupCharacter==="未定";}function setGroupingFilter(name,enterStudio=true){if(!groupingEnabled)return;state.groupCharacter=name;const first=groupingRowsFor(name)[0];if(first)state.currentKey=rowKey(first);refreshView(state.currentKey);if(enterStudio)setMode("studio");renderGroupingView();}function startGroupingNaming(){setGroupingFilter("未定",true);const face=state.visible.flatMap((index)=>facesForRow(rows[index])).find((item)=>!faceIsNamed(item));if(!face){setText("studio-meta","未定队列没有可命名的人脸；可查看空角色图片");return;}const row=rows.find((item)=>item.sha16===face.image_sha16);if(row)state.currentKey=rowKey(row);renderStudio();const open=()=>{const target=els("face-overlay")?.querySelector(`[data-face-id="${CSS.escape(face.face_id)}"]`);if(target)openFacePopover(face.face_id);else if(face.cluster_id!==null&&face.cluster_id!==undefined)openClusterNameModal(String(face.cluster_id));else setText("studio-meta","未定人脸已进入队列 · 可按 N 开始命名");};requestAnimationFrame(open);}function initializeGroupingLayer(){const tab=els("grouping-mode");if(!groupingEnabled){if(tab)tab.hidden=true;return;}if(tab)tab.hidden=false;renderGroupingView();}
   init();initializeIdentityLayer();initializeGroupingLayer();bindGroupingControls();function bindGroupingControls(){els("grouping-mode")?.addEventListener("click",()=>setMode("grouping"));els("grouping-cards")?.addEventListener("click",(event)=>{const target=event.target instanceof Element?event.target.closest("[data-group-character]"):null;if(target)setGroupingFilter(target.dataset.groupCharacter||"未定",true);});els("grouping-unassigned-toggle")?.addEventListener("change",(event)=>{if(event.target.checked)setGroupingFilter("未定",false);else{state.groupCharacter=null;refreshView();renderGroupingView();}});els("grouping-open-studio")?.addEventListener("click",()=>setMode("studio"));els("grouping-start-naming")?.addEventListener("click",startGroupingNaming);}
}
})();
</script>
<!-- build metrics: legacy=__LEGACY_BYTES__B columnar=__COLUMNAR_BYTES__B gzip=__GZIP_BYTES__B base64=__BASE64_BYTES__B fingerprint=__FINGERPRINT__ -->
</body>
</html>
'''


if __name__ == "__main__":
    raise SystemExit(main())
