"""Standalone verified reversal of the disposition journal; safe to repeat."""
import argparse
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from ._moves import (
    ROOT, Entry, MoveError, Plan, append_entry, batch_lock, cli_out, confined,
    load_plan, read_log, sha256, verified_copy,
)


def restore(entry: Entry, plan: Plan) -> Literal["undone", "already_undone"]:
    """Never overwrite either side; remove reverse source only after equal hashes."""
    matches = [m for m in plan.moves if m.src == entry.src and m.sha256 == entry.sha256_before]
    if len(matches) != 1:
        raise MoveError("日志源路径不属于计划")
    move = matches[0]
    if move.dst is None or move.dst == move.src:
        raise MoveError("日志不是计划中的移动操作")
    suffixed = move.dst.with_name(f"{move.dst.stem}__{move.sha16}{move.dst.suffix}")
    full_suffixed = move.dst.with_name(f"{move.dst.stem}__{move.sha256}{move.dst.suffix}")
    if (entry.dst not in {move.dst, suffixed, full_suffixed} or entry.bytes != move.bytes
            or entry.sha256_before != move.sha256 or entry.sha256_after != move.sha256):
        raise MoveError("日志目标或哈希不属于计划")
    src = confined(entry.src, move.character)
    dst = confined(entry.dst, move.character)
    if src.exists() and sha256(src) != move.sha256:
        raise MoveError(f"原位置已被不同内容占用，拒绝覆盖：{src}")
    if not dst.exists():
        if src.exists():
            return "already_undone"
        raise MoveError(f"两端文件均缺失，需要人工恢复：{src}")
    if sha256(dst) != move.sha256:
        raise MoveError(f"目标文件已修改，拒绝撤销：{dst}")
    if not src.exists():
        verified_copy(dst, src, move.sha256)
    # Both-present state also recovers interruption after the durable done record.
    if sha256(src) != move.sha256 or sha256(dst) != move.sha256:
        raise MoveError("撤销哈希校验不一致；保留两端文件")
    confined(dst, move.character).unlink()
    return "undone"


def revert(out: Path, log_name: Path = Path("disposition_log.jsonl"), limit: int | None = None) -> list[str]:
    """Report every done entry, reverse order; preserve the append-only history."""
    if limit is not None and limit < 1:
        raise MoveError("--limit 必须为正整数")
    log = confined(out / log_name, out)
    if not log.is_file():
        raise MoveError(f"操作日志不存在：{log}")
    with batch_lock(out):
        plan = load_plan(out)
        entries = [e for e in reversed(read_log(log)) if e.status == "done"]
        if limit is not None:
            entries = entries[:limit]
        results: list[str] = []
        for entry in entries:
            try:
                status = restore(entry, plan)
                append_entry(log, entry.model_copy(update={"status": status}))
                results.append(status)
                print(f"撤销结果 {status}：{entry.src}")
            except (OSError, MoveError) as error:
                append_entry(log, entry.model_copy(update={"status": "undo_failed"}))
                results.append("undo_failed")
                print(f"撤销失败，文件保留：{entry.src}：{error}")
        return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=Path("disposition_log.jsonl"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    try:
        results = revert(cli_out(args.out, ROOT), args.log, args.limit)
        return int("undo_failed" in results)
    except (OSError, ValueError, MoveError, ValidationError) as error:
        print(f"拒绝撤销：{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
