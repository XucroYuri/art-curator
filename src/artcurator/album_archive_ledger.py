"""Archive lineage adapter over the existing hash-framed journal/Entry contracts.

The legacy reader requires a character score plan; archive records instead bind
an archive plan. Reuse Record/publish, not its score-plan-specific projection.
"""
import hashlib
import os
from pathlib import Path

from ._moves import Entry, Move, Plan, Targets, confined, safe_path
from .album_archive_schema import ArchivePlan, Item, Stamp
from .album_map_schema import MappingError
from .journal import Record, publish


def validate(plan: ArchivePlan) -> None:
    if plan.digest != plan.fingerprint():
        raise MappingError("archive-plan-digest")
    for item in plan.items:
        confined(item.src, plan.request.source_root)
        confined(item.dst, plan.request.export_root)
        if item.dst != plan.request.export_root / item.target / item.src.name:
            raise MappingError("archive-target-binding")


def load(root: Path) -> ArchivePlan:
    plan = ArchivePlan.model_validate_json(safe_path(root / "archive_plan.json").read_bytes())
    validate(plan)
    if plan.request.ledger_root != root:
        raise MappingError("archive-ledger-binding")
    return plan


class Ledger:
    """Append-only coordinator; records accumulates fsynced frames in sequence."""

    def __init__(self, plan: ArchivePlan) -> None:
        self.plan = plan
        self.path = safe_path(plan.request.ledger_root / "disposition_log.jsonl")
        self.records: list[Record] = []
        if not self.path.exists():
            return
        for line in self.path.read_bytes().splitlines(keepends=True):
            if not line.endswith(b"\n"):
                raise MappingError("archive-torn-ledger-preserved-manual-recovery-required")
            record = Record.model_validate_json(line)
            previous = self.records[-1].digest if self.records else ""
            if (record.sequence != len(self.records) + 1 or record.previous != previous
                    or record.digest != record.fingerprint() or record.plan_id != plan.digest
                    or record.run_id != plan.digest):
                raise MappingError("archive-ledger-lineage")
            if record.entry is not None:
                entry = record.entry
                matches = [i for i in plan.items if i.src == entry.src and i.dst == entry.dst]
                if len(matches) != 1:
                    raise MappingError("archive-ledger-path")
                item = matches[0]
                if (item.stamp is None or entry.bytes != item.stamp.size or entry.sha256_before != item.sha256
                        or entry.sha16 != item.sha256[:16] or record.operation_id != self.operation(item)):
                    raise MappingError("archive-ledger-content")
            self.records.append(record)

    def operation(self, item: Item) -> str:
        return hashlib.sha256(f"{self.plan.digest}\n{item.src}\n{item.dst}\n{item.sha256}".encode()).hexdigest()

    def latest(self, item: Item) -> Record | None:
        return next((r for r in reversed(self.records) if r.operation_id == self.operation(item)), None)

    def append(self, item: Item, event: tuple[str, Entry | None]) -> None:
        detail, entry = event
        sequence = len(self.records) + 1
        operation = self.operation(item)
        record = Record(sequence=sequence, operation_id=operation, run_id=self.plan.digest,
            plan_id=self.plan.digest, kind="move", previous=self.records[-1].digest if self.records else "",
            entry=entry.model_copy(update={"sequence": sequence, "operation_id": operation}) if entry else None,
            detail=detail)
        self.records.append(publish(self.path, record))


def entry_for(item: Item) -> Entry:
    if item.stamp is None:
        raise MappingError("archive-source-unavailable")
    return Entry(sha16=item.sha256[:16], src=item.src, dst=item.dst, bytes=item.stamp.size,
                 sha256_before=item.sha256, sha256_after=item.sha256, status="done")


def reverse_plan(plan: ArchivePlan) -> Plan:
    """Reuse undo.restore's confined reverse-copy algorithm, never the collision planner."""
    common = Path(os.path.commonpath((plan.request.source_root, plan.request.export_root)))
    moves = tuple(Move(src=i.src, dst=i.dst, character=common, sha16=i.sha256[:16],
                       bytes=i.stamp.size, sha256=i.sha256, tier="queue")
                  for i in plan.items if i.stamp is not None and not i.conflicts)
    return Plan(scores_sha256=plan.snapshot_digest, characters_root=common,
                characters=(common,), targets=Targets(), moves=moves)


def target_stamp(record: Record) -> Stamp:
    return Stamp.model_validate_json(record.detail)
