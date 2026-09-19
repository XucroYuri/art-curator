"""Standalone, dry-run-first disposition planner and explicitly gated executor."""
import argparse
import csv
import hashlib
import io
import os
from collections import Counter
from pathlib import Path

import yaml
from pydantic import ValidationError

from ._moves import (
    REQUIRED_SCORE_FIELDS, ROOT, ApplyConfig, Entry, Move, MoveError, Plan, Score,
    append_entry, batch_lock, check_plan, check_targets, cli_out, collision_path,
    confined, load_plan, read_log, safe_path, sha256, staged_copies,
)


def make_plan(out: Path, config: Path, limit: int | None = None) -> Plan:
    """Read corpus bytes only; write an immutable, content-bound proposal to out."""
    if limit is not None and limit < 1:
        raise MoveError("--limit 必须为正整数")
    settings = ApplyConfig.model_validate(yaml.safe_load(config.read_text(encoding="utf-8")))
    root = safe_path(settings.characters_root)
    check_targets(settings.apply)
    safe_path(out)
    if out.is_relative_to(root):
        raise MoveError("输出目录不得位于角色语料目录内")
    with batch_lock(out):
        if read_log(out / "disposition_log.jsonl"):
            raise MoveError("已有操作日志；保留原计划以便撤销，请使用新的输出目录")
        scores_path = safe_path(out / "scores.csv")
        if not scores_path.is_file():
            raise MoveError("缺少 scores.csv")
        scores = scores_path.read_bytes()
        reader = csv.DictReader(io.StringIO(scores.decode("utf-8-sig")))
        names = reader.fieldnames or []
        missing = [field for field in REQUIRED_SCORE_FIELDS if field not in names]
        if missing:
            raise MoveError(f"scores.csv 缺少必要列：{', '.join(missing)}")
        moves: list[Move] = []
        for raw in reader:
            row = Score.model_validate(raw)
            src = safe_path(row.abs_path)
            character = src.parent.parent
            if character.parent != root:
                raise MoveError(f"源路径不属于配置中的角色目录：{src}")
            folder = settings.apply.folder(row.proposed_tier)
            dst = character / folder / src.name if folder else None
            full_hash = sha256(src)
            if full_hash[:16] != row.sha16 or src.stat().st_size != row.filesize:
                raise MoveError(f"源文件与评分记录不一致：{src}")
            moves.append(Move(src=src, dst=dst, character=character, sha16=row.sha16,
                              bytes=row.filesize, sha256=full_hash, tier=row.proposed_tier))
            if limit is not None and len(moves) >= limit:
                break
        draft = Plan(scores_sha256=hashlib.sha256(scores).hexdigest(), characters_root=root,
                     characters=tuple(sorted({m.character for m in moves})),
                     targets=settings.apply, moves=tuple(moves))
        plan = draft.model_copy(update={"digest": draft.fingerprint()})
        check_plan(plan)
        destination = safe_path(out / "moves_plan.json")
        temporary = safe_path(out / "moves_plan.json.tmp")
        temporary.unlink(missing_ok=True)
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(plan.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    return plan


def execute(out: Path, token: str, limit: int | None = None, *, workers: int = 8) -> None:
    """Execute a sealed plan once; reverse completed entries if this batch fails."""
    from .undo import restore

    if limit is not None and limit < 1:
        raise MoveError("--limit 必须为正整数")
    with batch_lock(out):
        plan = load_plan(out)
        if sha256(out / "scores.csv") != plan.scores_sha256:
            raise MoveError("scores.csv 摘要已变化；拒绝执行旧计划")
        if token != "APPLY-" + plan.digest[:8]:
            raise MoveError("确认令牌错误；需要 APPLY- 加计划摘要前 8 位")
        log = safe_path(out / "disposition_log.jsonl")
        if read_log(log):
            raise MoveError("已有操作日志；禁止重复执行，请先检查或撤销")
        selected = [m for m in plan.moves if m.dst is not None]
        if limit is not None:
            selected = selected[:limit]
        # Preflight every selected source before creating any corpus directories.
        for move in selected:
            confined(move.src, move.character)
            if sha256(move.src) != move.sha256 or move.src.stat().st_size != move.bytes:
                raise MoveError(f"源文件已变化：{move.src}")
            collision_path(move)
        completed: list[Entry] = []
        for staged in staged_copies(selected, workers):
            move = staged.move
            dst = staged.dst
            entry = Entry(sha16=move.sha16, src=move.src, dst=dst, bytes=move.bytes,
                          sha256_before=move.sha256, sha256_after="", status="failed")
            try:
                if staged.error is not None:
                    raise staged.error
                if staged.duplicate:
                    if sha256(move.src) != move.sha256 or sha256(dst) != move.sha256:
                        raise MoveError("重复文件在校验期间发生变化")
                    append_entry(log, entry.model_copy(update={"sha256_after": sha256(dst), "status": "duplicate"}))
                    continue
                after = staged.after
                done = entry.model_copy(update={"sha256_after": after, "status": "done"})
                # Durable write-ahead completion intent closes the unlink/journal crash gap.
                completed.append(done)
                append_entry(log, done)
                if sha256(move.src) != after or sha256(dst) != after:
                    raise MoveError("提交前文件已变化；拒绝移除源文件")
                confined(move.src, move.character).unlink()
                print(f"已移动：{move.src.name} → {dst.parent.name}")
            except (OSError, MoveError) as error:
                # Restore first: even a full ledger disk must not prevent rollback.
                for done in reversed(completed):
                    try:
                        restore(done, plan)
                        append_entry(log, done.model_copy(update={"status": "rolled_back"}))
                    except (OSError, MoveError) as rollback_error:
                        print(f"回滚未完成，请运行 undo：{done.src}：{rollback_error}")
                observed = sha256(dst) if dst.is_file() else ""
                append_entry(log, entry.model_copy(update={"sha256_after": observed}))
                raise MoveError(f"批次已终止；已尝试恢复全部完成项：{error}") from error


def summarize(plan: Plan) -> None:
    counts = Counter(m.dst.parent.name if m.dst else "不移动（review）" for m in plan.moves)
    print(f"仅生成计划，未改动语料。共 {len(plan.moves)} 条：")
    for target, count in sorted(counts.items()):
        print(f"  {target}: {count}")
    print(f"实际待移动：{sum(m.dst is not None and m.dst != m.src for m in plan.moves)}；"
          f"已在目标目录：{sum(m.dst == m.src for m in plan.moves)}")
    for move in [m for m in plan.moves if m.dst is not None and m.dst != m.src][:3]:
        print(f"  示例：{move.src} → {move.dst}")
    print(f"计划摘要：{plan.digest}\n执行令牌：APPLY-{plan.digest[:8]}")


def main(argv: list[str] | None = None, *, project: Path = ROOT) -> int:
    """Keep the existing argparse style without importing the pipeline CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plan", action="store_true")
    group.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    try:
        out = cli_out(args.out, project)
        if args.execute:
            if not args.confirm:
                raise MoveError("执行必须同时指定 --execute 和 --confirm <TOKEN>")
            settings = ApplyConfig.model_validate(yaml.safe_load(args.config.read_text(encoding="utf-8")))
            execute(out, args.confirm, args.limit, workers=settings.workers)
        else:
            if args.confirm:
                raise MoveError("--confirm 只能与 --execute 一起使用")
            summarize(make_plan(out, args.config, args.limit))
    except (OSError, ValueError, MoveError, ValidationError, yaml.YAMLError) as error:
        print(f"拒绝或中止操作：{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
