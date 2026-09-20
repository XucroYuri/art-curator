"""Filesystem safety primitives and typed on-disk move contracts."""
import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Final, Literal, assert_never

from pydantic import BaseModel, ConfigDict, Field

ROOT: Final = Path(__file__).resolve().parents[2]
REQUIRED_SCORE_FIELDS: Final = ("sha16", "abs_path", "filesize", "proposed_tier")
Tier = Literal["queue", "route_nsfw", "route_identity", "archive_candidate", "review"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ShortHash = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
Status = Literal["done", "duplicate", "failed", "undone", "already_undone", "undo_failed", "rolled_back"]


class MoveError(RuntimeError):
    """An operation was refused without sacrificing the last verified copy."""


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Targets(Frozen):
    queue: str = "queue"
    route_nsfw: str = "safety-review"
    route_identity: str = "身份待核"
    archive_candidate: str = "归档候选"

    def folder(self, tier: Tier) -> str | None:
        match tier:
            case "queue":
                return self.queue
            case "route_nsfw":
                return self.route_nsfw
            case "route_identity":
                return self.route_identity
            case "archive_candidate":
                return self.archive_candidate
            case "review":
                return None
            case _ as unreachable:
                assert_never(unreachable)


class ApplyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    characters_root: Path
    apply: Targets = Field(default_factory=Targets)
    workers: int = Field(default=8, ge=1, le=12)


class Score(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    sha16: ShortHash
    abs_path: Path
    filesize: int = Field(ge=0)
    proposed_tier: Tier
    sha256: Digest | Literal[""] | None = None


class Move(Frozen):
    src: Path
    dst: Path | None
    character: Path
    sha16: ShortHash
    bytes: int = Field(ge=0)
    sha256: Digest
    tier: Tier


class Plan(Frozen):
    version: Literal[1] = 1
    scores_sha256: Digest
    characters_root: Path
    characters: tuple[Path, ...]
    targets: Targets
    moves: tuple[Move, ...]
    digest: str = ""

    def fingerprint(self) -> str:
        payload = json.dumps(self.model_dump(mode="json", exclude={"digest"}),
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Entry(Frozen):
    sequence: int = 0
    operation_id: str = ""
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    sha16: ShortHash
    src: Path
    dst: Path
    bytes: int = Field(ge=0)
    sha256_before: Digest
    sha256_after: str
    status: Status


def safe_path(path: Path) -> Path:
    """Reject links, Windows junctions, relative paths, and traversal components."""
    if not path.is_absolute() or ".." in path.parts:
        raise MoveError(f"拒绝相对路径或路径越界：{path}")
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise MoveError(f"拒绝符号链接或目录联接：{part}")
    return path


def confined(path: Path, root: Path) -> Path:
    safe_path(root)
    safe_path(path)
    if path == root or not path.is_relative_to(root):
        raise MoveError(f"拒绝角色目录外的路径：{path}")
    return path


def sha256(path: Path) -> str:
    safe_path(path)
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def append_entry(log: Path, entry: Entry) -> None:
    from .journal import append
    append(log, entry)


def read_log(log: Path) -> list[Entry]:
    from .journal import read
    return read(log)


@contextmanager
def batch_lock(out: Path) -> Iterator[None]:
    """Fail closed on concurrent runs or a stale lock after interruption."""
    lock = safe_path(out / ".disposition.lock")
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise MoveError("输出目录存在未完成操作锁；确认无活动进程后删除 .disposition.lock") from error
    with handle:
        handle.write(str(os.getpid()))
        handle.flush()
    try:
        yield
    finally:
        lock.unlink()


def copy_bytes(src: Path, dst: Path) -> None:
    """Exclusive creation: never overwrite an existing destination."""
    safe_path(src)
    safe_path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as reader, dst.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    shutil.copystat(src, dst, follow_symlinks=False)


def verified_copy(src: Path, dst: Path, expected: str) -> str:
    if sha256(src) != expected:
        raise MoveError(f"源文件哈希已变化，拒绝移动：{src}")
    copy_bytes(src, dst)
    after = sha256(dst)
    if after != expected or sha256(src) != expected:
        raise MoveError(f"哈希校验不一致；保留源文件及失败副本，终止批次：{src}")
    return after


@dataclass(frozen=True, slots=True)
class StagedCopy:
    move: Move
    dst: Path
    after: str = ""
    duplicate: bool = False
    error: OSError | MoveError | None = None


def staged_copies(moves: list[Move], workers: int = 8) -> Iterator[StagedCopy]:
    """Parallel copy/verify waves; no worker ever logs or unlinks a source.

    Join the entire wave before any commit/rollback. Aliased destinations or
    source/target dependencies use serial waves, preserving collision semantics.
    Failed or uncommitted copies remain alongside their intact sources.
    """
    if not 1 <= workers <= 12:
        raise MoveError("workers must be between 1 and 12")
    destinations = [collision_path(move) for move in moves]
    sources = {move.src for move in moves}
    width = workers if len(set(destinations)) == len(destinations) and not sources.intersection(destinations) else 1

    def stage(move: Move) -> StagedCopy:
        dst = move.src
        try:
            dst = collision_path(move)
            if dst.exists():
                if sha256(move.src) != move.sha256 or sha256(dst) != move.sha256:
                    raise MoveError("重复文件在校验期间发生变化")
                return StagedCopy(move, dst, move.sha256, True)
            return StagedCopy(move, dst, verified_copy(move.src, dst, move.sha256))
        except (OSError, MoveError) as error:
            return StagedCopy(move, dst, error=error)

    for start in range(0, len(moves), width):
        with ThreadPoolExecutor(max_workers=width, thread_name_prefix="curator-copy") as pool:
            wave = list(pool.map(stage, moves[start:start + width]))
        yield from wave
        if any(item.error is not None for item in wave):
            return


def collision_path(move: Move) -> Path:
    if move.dst is None:
        raise MoveError("review 没有移动目标")
    dst = confined(move.dst, move.character)
    if dst.exists() and sha256(dst) != move.sha256:
        dst = confined(dst.with_name(f"{dst.stem}__{move.sha16}{dst.suffix}"), move.character)
        if dst.exists() and sha256(dst) != move.sha256:
            dst = confined(move.dst.with_name(f"{move.dst.stem}__{move.sha256}{move.dst.suffix}"), move.character)
            if dst.exists() and sha256(dst) != move.sha256:
                raise MoveError(f"带完整哈希后缀的目标仍冲突，拒绝覆盖：{dst}")
    return dst


def check_plan(plan: Plan) -> None:
    if plan.digest != plan.fingerprint():
        raise MoveError("计划摘要不匹配；请重新生成计划")
    safe_path(plan.characters_root)
    if set(plan.characters) != {move.character for move in plan.moves}:
        raise MoveError("计划角色白名单不匹配")
    sources: set[Path] = set()
    for move in plan.moves:
        if move.character.parent != plan.characters_root or move.src.parent.parent != move.character:
            raise MoveError("拒绝角色目录外的计划条目")
        confined(move.character, plan.characters_root)
        confined(move.src, move.character)
        if move.src in sources or move.sha16 != move.sha256[:16]:
            raise MoveError("重复源路径或哈希不匹配")
        sources.add(move.src)
        folder = plan.targets.folder(move.tier)
        expected = move.character / folder / move.src.name if folder else None
        if move.dst != expected:
            raise MoveError("计划目标不符合分流映射")
        if move.dst:
            confined(move.dst, move.character)


def check_targets(targets: Targets) -> None:
    for name in targets.model_dump().values():
        if not name or name in {".", ".."} or any(c in name for c in '/\\:<>"|?*') or name.endswith((".", " ")):
            raise MoveError(f"目标必须是单层普通文件夹名称：{name}")


def load_plan(out: Path) -> Plan:
    path = safe_path(out / "moves_plan.json")
    if not path.is_file():
        raise MoveError("缺少 moves_plan.json；先运行 --plan")
    plan = Plan.model_validate_json(path.read_text(encoding="utf-8"))
    check_targets(plan.targets)
    check_plan(plan)
    if out.is_relative_to(plan.characters_root):
        raise MoveError("输出目录不得位于角色语料目录内")
    return plan


def cli_out(path: Path, project: Path) -> Path:
    return confined(path.absolute(), project.absolute())
