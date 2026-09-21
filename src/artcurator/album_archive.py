"""Optional physical export coordinator: preview first, ledger inverse separately."""
import os
from pathlib import Path
from typing import assert_never

from ._moves import MoveError, batch_lock, safe_path, sha256, verified_copy
from .album_archive_ledger import Ledger, entry_for, load, reverse_plan, target_stamp, validate
from .album_archive_plan import classify, layout
from .album_archive_schema import Approval, ArchivePlan, ArchiveRequest, Item, Result, Stamp
from .album_map import AlbumStore
from .album_map_schema import MappingError
from .album_archive_transfer import recover_rename, rename
from .undo import restore


def derive(store: AlbumStore, request: ArchiveRequest) -> ArchivePlan:
    """No output, mkdir, lock creation or mapping mutation; caller owns store admission."""
    return layout(store.snapshot(), request)


def check_source(item: Item) -> None:
    if Stamp.capture(item.src) != item.stamp or sha256(item.src) != item.sha256:
        raise MappingError("archive-source-changed")


def execute(store: AlbumStore, plan: ArchivePlan, approval: Approval) -> Result:
    """Reject the whole preflight before writes; interruptions retain verified copies."""
    validate(plan)
    if approval.digest != plan.digest or approval.token != plan.token:
        raise MappingError("archive-explicit-digest-and-token-required")
    live = store.snapshot()
    if live.root != plan.mapping or live.fingerprint() != plan.snapshot_digest:
        raise MappingError("archive-mapping-changed")
    if any(set(i.conflicts) - {"already_correct"} for i in plan.items):
        raise MappingError("archive-conflicts-require-new-preview")
    if plan.request.transfer == "rename" and os.name != "nt":
        raise MappingError("archive-no-replace-rename-requires-windows-same-volume")
    root = safe_path(plan.request.ledger_root)
    saved = root / "archive_plan.json"
    if saved.exists():
        if load(root) != plan:
            raise MappingError("archive-ledger-already-bound")
    elif layout(live, plan.request) != plan:
        raise MappingError("archive-stale-preview")
    ledger = Ledger(plan)
    # Validate every untouched source before the first write, also on resume.
    for item in plan.items:
        if ledger.latest(item) is None and classify(item) != item:
            raise MappingError("archive-stale-source-or-target")
    if not any(not item.conflicts for item in plan.items):
        return Result(plan_id=plan.digest, no_op=len(plan.items))
    root.mkdir(parents=True, exist_ok=True)
    with batch_lock(root):
        if not saved.exists():
            with saved.open("x", encoding="utf-8") as handle:
                handle.write(plan.model_dump_json(indent=2))
                handle.flush()
                os.fsync(handle.fileno())
        # Reload while holding output admission, excluding same-output competing runs.
        ledger = Ledger(plan)
        done, already, noop = 0, 0, 0
        for item in plan.items:
            if "already_correct" in item.conflicts:
                noop += 1
                continue
            prior = recover_rename(ledger, item)
            if prior is not None:
                if prior.entry is None:
                    raise MappingError("archive-interrupted-copy-preserved-use-undo-or-review")
                if prior.entry.status in {"undone", "already_undone", "undo_failed"}:
                    raise MappingError("archive-inverse-started-new-plan-required")
                if Stamp.capture(item.dst) != target_stamp(prior) or sha256(item.dst) != item.sha256:
                    raise MappingError("archive-export-modified")
                if item.src.exists():
                    check_source(item)
                    item.src.unlink()
                    done += 1
                else:
                    already += 1
                continue
            check_source(item)
            match plan.request.transfer:
                case "rename":
                    rename(ledger, item)
                case "copy-verify":
                    ledger.append(item, ("copy-intent", None))
                    # Existing primitive: exclusive create -> copy -> fsync -> both digests.
                    verified_copy(item.src, item.dst, item.sha256)
                    check_source(item)
                    ledger.append(item, (Stamp.capture(item.dst).model_dump_json(), entry_for(item)))
                    # Ledger is durable before removing the verified redundant source.
                    check_source(item)
                    if sha256(item.dst) != item.sha256:
                        raise MappingError("archive-copy-changed-before-unlink")
                    item.src.unlink()
                case unreachable:
                    assert_never(unreachable)
            done += 1
        return Result(plan_id=plan.digest, done=done, already_done=already, no_op=noop, source_moves=done)


def undo(root: Path) -> Result:
    """Reverse one run, preserving edits; completed inverse records are terminal tokens."""
    plan = load(safe_path(root))
    with batch_lock(root):
        ledger = Ledger(plan)
        reverse = reverse_plan(plan)
        undone, already = 0, 0
        conflicts: list[str] = []
        for item in reversed(plan.items):
            prior = recover_rename(ledger, item)
            if prior is None:
                continue
            if prior.entry is None:
                conflicts.append(f"{item.selection.occurrence_id}:uncommitted-copy-preserved")
                continue
            entry = prior.entry
            if entry.status in {"undone", "already_undone"}:
                already += 1
                continue
            try:
                if item.dst.exists() and Stamp.capture(item.dst) != target_stamp(prior):
                    raise MappingError("archive-target-edited")
                if item.src.exists() and item.dst.exists():
                    current = Stamp.capture(item.src)
                    if item.stamp is None or (current.size, current.mtime_ns) != (item.stamp.size, item.stamp.mtime_ns):
                        raise MappingError("archive-original-edited")
                status = restore(entry, reverse)
                ledger.append(item, (prior.detail, entry.model_copy(update={"status": status})))
                undone += status == "undone"
                already += status == "already_undone"
            except (OSError, MoveError, MappingError) as error:
                ledger.append(item, (prior.detail, entry.model_copy(update={"status": "undo_failed"})))
                conflicts.append(f"{item.selection.occurrence_id}:{error}")
        return Result(plan_id=plan.digest, undone=undone, already_undone=already,
                      conflicts=tuple(conflicts), partial_undo=bool(conflicts))


def status(store: AlbumStore, root: Path) -> Result:
    """Surface outstanding physical work even after the originating mapping was undone."""
    plan = load(safe_path(root))
    ledger = Ledger(plan)
    outstanding = 0
    for item in plan.items:
        prior = ledger.latest(item)
        if prior is not None and (prior.entry is None or prior.entry.status not in {"undone", "already_undone"}):
            outstanding += 1
    return Result(plan_id=plan.digest, outstanding=outstanding, mapping_changed=store.snapshot().root != plan.mapping)
