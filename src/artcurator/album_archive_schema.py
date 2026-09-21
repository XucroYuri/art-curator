"""Frozen G6 export boundaries; physical layout never replaces the mapping root."""
import hashlib
import json
from pathlib import Path
from typing import Final, Literal

from pydantic import Field

from ._moves import Frozen
from .album_map_protocol import Root
from .album_map_schema import EntityType, Hash, Identifier

NAMESPACES: Final[dict[EntityType, str]] = {
    "work": "IP/作品", "artist": "画师", "original-series": "原创系列",
    "character": "角色", "ordinary-person": "普通人", "undetermined": "未定",
}
Conflict = Literal["already_correct", "name_collision", "different_target", "missing", "unreadable",
                   "path_length", "case_hazard", "cross_volume", "capacity", "changed_source", "unsafe_path"]
CONFLICTS: Final[tuple[Conflict, ...]] = ("already_correct", "name_collision", "different_target", "missing",
    "unreadable", "path_length", "case_hazard", "cross_volume", "capacity", "changed_source", "unsafe_path")


class Selection(Frozen):
    image_id: Hash
    occurrence_id: Identifier
    relation_id: Identifier
    reviewed_inclusion: bool = False


class ArchiveRequest(Frozen):
    schema_version: Literal["album-archive-request-v1"] = "album-archive-request-v1"
    source_root: Path
    export_root: Path
    ledger_root: Path
    selections: tuple[Selection, ...] = ()
    transfer: Literal["copy-verify", "rename"] = "copy-verify"
    policy: Literal["one-selected-relation-per-occurrence"] = "one-selected-relation-per-occurrence"


class Stamp(Frozen):
    size: int
    mtime_ns: int
    device: int
    inode: int

    @classmethod
    def capture(cls, path: Path) -> "Stamp":
        stat = path.stat()
        return cls(size=stat.st_size, mtime_ns=stat.st_mtime_ns, device=stat.st_dev, inode=stat.st_ino)


class Item(Frozen):
    selection: Selection
    src: Path
    dst: Path
    target: str
    sha256: Hash
    stamp: Stamp | None
    conflicts: tuple[Conflict, ...] = ()


class Summary(Frozen):
    targets: dict[str, int]
    conflicts: dict[Conflict, int]
    ready: int
    excluded: tuple[str, ...]
    required_bytes: int


class ArchivePlan(Frozen):
    schema_version: Literal["album-archive-plan-v1"] = "album-archive-plan-v1"
    request: ArchiveRequest
    mapping: Root
    snapshot_digest: Hash
    items: tuple[Item, ...]
    summary: Summary
    digest: str = ""

    def fingerprint(self) -> str:
        data = json.dumps(self.model_dump(mode="json", exclude={"digest"}), sort_keys=True,
                          ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(data.encode()).hexdigest()

    @property
    def token(self) -> str:
        return "EXPORT-" + self.digest


class Approval(Frozen):
    digest: str
    token: str


class Result(Frozen):
    plan_id: str
    done: int = 0
    already_done: int = 0
    undone: int = 0
    already_undone: int = 0
    no_op: int = 0
    conflicts: tuple[str, ...] = ()
    partial_undo: bool = False
    mapping_changed: bool = False
    source_moves: int = Field(default=0, ge=0)
    outstanding: int = Field(default=0, ge=0)
