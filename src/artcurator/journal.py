"""Ordered, hash-framed move journal; SQLite is a rebuildable projection."""
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from . import db
from ._moves import Entry, MoveError, load_plan, safe_path, sha256


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal[1] = 1
    sequence: int
    operation_id: str
    run_id: str
    plan_id: str
    kind: Literal["move", "recovery", "reconciliation"]
    previous: str
    entry: Entry | None = None
    detail: str = ""
    digest: str = ""

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json", exclude={"digest"}),
                                         sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def project(log: Path, records: list[Record]) -> None:
    """Replace only the non-authoritative SQLite projection after journal validation."""
    with db.connection(log.parent) as connection:
        connection.execute("DELETE FROM journal_events")
        connection.executemany("INSERT INTO journal_events VALUES (?,?,?,?)", [
            (record.sequence, record.operation_id, record.kind, record.model_dump_json()) for record in records])


def publish(log: Path, record: Record) -> Record:
    sealed = record.model_copy(update={"digest": record.fingerprint()})
    with log.open("ab") as handle:
        handle.write((sealed.model_dump_json() + "\n").encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    return sealed


def read_records(log: Path) -> list[Record]:
    safe_path(log)
    if not log.exists():
        return []
    original = log.read_bytes()
    lines = original.splitlines(keepends=True)
    records: list[Record] = []
    offset = 0
    torn = False
    for index, line in enumerate(lines):
        if index == len(lines) - 1 and not line.endswith(b"\n"):
            torn = True
            break
        try:
            record = Record.model_validate_json(line)
        except ValidationError as error:
            raise MoveError("Journal corruption or legacy unframed journal; explicit migration required") from error
        if (record.sequence != len(records) + 1 or record.digest != record.fingerprint()
                or record.previous != (records[-1].digest if records else "")):
            raise MoveError("Journal order or record integrity mismatch")
        records.append(record)
        offset += len(line)
    if records:
        plan = load_plan(log.parent)
        if any(record.plan_id != plan.digest or record.run_id != records[0].run_id for record in records):
            raise MoveError("Journal run/plan lineage mismatch")
    if torn:
        backup = log.with_name(log.name + ".torn-" + hashlib.sha256(original).hexdigest() + ".bak")
        if not backup.exists():
            with backup.open("xb") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
        plan = load_plan(log.parent)
        # Replace prefix + recovery marker atomically: no unrecorded truncation window.
        temporary = log.with_name(log.name + ".recovery.tmp")
        with temporary.open("wb") as handle:
            handle.write(original[:offset])
            handle.flush()
            os.fsync(handle.fileno())
        records.append(publish(temporary, Record(sequence=len(records) + 1, operation_id=uuid.uuid4().hex,
            run_id=records[0].run_id if records else uuid.uuid4().hex, plan_id=plan.digest,
            kind="recovery", previous=records[-1].digest if records else "",
            detail=f"torn_tail_discarded:{len(original) - offset};backup:{backup.name}")))
        os.replace(temporary, log)
    # A durable recovery record also resumes a crash after truncation but before reconciliation.
    if records and any(record.kind == "recovery" for record in records):
        reconcile(log, records)
    project(log, records)
    return records


def reconcile(log: Path, records: list[Record]) -> None:
    """Reconstruct only verified plan-bound copied/moved states; never unlink here."""
    plan = load_plan(log.parent)
    known = {record.entry.src for record in records if record.entry is not None}
    for move in plan.moves:
        if move.src in known or move.dst is None or move.dst == move.src:
            continue
        observation = hashlib.sha256(json.dumps([plan.digest, str(move.src), "recovery-observation"]).encode()).hexdigest()
        if any(record.operation_id == observation for record in records):
            continue
        candidates = (move.dst, move.dst.with_name(f"{move.dst.stem}__{move.sha16}{move.dst.suffix}"),
                      move.dst.with_name(f"{move.dst.stem}__{move.sha256}{move.dst.suffix}"))
        destination = next((p for p in candidates if p.exists() and sha256(p) == move.sha256), None)
        if move.src.exists() and sha256(move.src) != move.sha256:
            raise MoveError("Recovery source conflict: manual recovery required")
        if destination is None:
            if not move.src.exists():
                raise MoveError("Neither verified path present: manual recovery required")
            records.append(publish(log, Record(sequence=len(records) + 1, operation_id=observation,
                run_id=records[0].run_id, plan_id=plan.digest, kind="reconciliation",
                previous=records[-1].digest, detail="source_only_verified_preserved")))
            continue
        if move.src.exists():
            # A torn duplicate record is indistinguishable from a staged copy here.
            # Preserve both copies; do not manufacture authority to remove either.
            records.append(publish(log, Record(sequence=len(records) + 1, operation_id=observation,
                run_id=records[0].run_id, plan_id=plan.digest, kind="reconciliation",
                previous=records[-1].digest, detail="both_present_ambiguous_preserved")))
            continue
        entry = Entry(sha16=move.sha16, src=move.src, dst=destination, bytes=move.bytes,
                      sha256_before=move.sha256, sha256_after=move.sha256, status="done")
        records.append(publish(log, make_record(log, records, entry).model_copy(update={
            "kind": "reconciliation", "detail": "verified_plan_paths_after_tail_recovery"})))


def make_record(log: Path, records: list[Record], entry: Entry) -> Record:
    plan = load_plan(log.parent)
    operation = hashlib.sha256(json.dumps([plan.digest, str(entry.src), str(entry.dst),
                                          entry.sha256_before]).encode()).hexdigest()
    sequence = len(records) + 1
    return Record(sequence=sequence, operation_id=operation,
                  run_id=records[0].run_id if records else uuid.uuid4().hex, plan_id=plan.digest,
                  kind="move", previous=records[-1].digest if records else "",
                  entry=entry.model_copy(update={"sequence": sequence, "operation_id": operation}))


def append(log: Path, entry: Entry) -> None:
    records = read_records(log)
    records.append(publish(log, make_record(log, records, entry)))
    project(log, records)


def read(log: Path) -> list[Entry]:
    return [record.entry for record in read_records(log) if record.entry is not None]
