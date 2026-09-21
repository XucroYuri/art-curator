"""G5 coordinator. P and C are distinct FULL-synchronous SQLite transactions."""
import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, assert_never

from pydantic import TypeAdapter

from .album_map_protocol import (
    Artifact, BatchRequest, Change, ExecutionReceipt, Mutation, Prepared, Snapshot, Support,
    image_digest, next_root,
)
from .album_map_recovery import receipt_for, reconcile, root_of
from .album_map_schema import MappingError, MappingRecord
from .album_map_storage import connect, transaction


class AlbumStore:
    """Mutable coordinator lifetime is bounded by OS admission and one connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.recovery = reconcile(connection)
        self.cutpoint: Callable[[str], None] = lambda phase: None

    @classmethod
    @contextmanager
    def initialize(cls, path: Path, library_id: str) -> Iterator["AlbumStore"]:
        with connect(path, library_id) as connection:
            yield cls(connection)

    @classmethod
    @contextmanager
    def open(cls, path: Path) -> Iterator["AlbumStore"]:
        with connect(path) as connection:
            yield cls(connection)

    def snapshot(self) -> Snapshot:
        """Pin root before all rows/history; no view reads an independently latest row."""
        self.connection.execute("BEGIN")
        try:
            root = root_of(self.connection)
            records, supports = [], []
            for key, payload in self.connection.execute("SELECT key,payload FROM materialized WHERE payload IS NOT NULL ORDER BY key"):
                if key.startswith("support:"):
                    supports.append(Support.model_validate_json(payload))
                else:
                    records.append(MappingRecord.model_validate_json(payload))
            history = tuple(ExecutionReceipt.model_validate_json(row[0]) for row in
                            self.connection.execute("SELECT payload FROM commits ORDER BY revision"))
            return Snapshot(root=root, records=tuple(records), supports=tuple(supports), history=history)
        finally:
            self.connection.rollback()

    def prepare(self, request: BatchRequest, authorization: str) -> Prepared | ExecutionReceipt:
        """Affirmation must echo the exact preview digest; changed-ID replay is refused."""
        self.recovery = reconcile(self.connection)
        if authorization != request.fingerprint():
            raise MappingError("affirmative-preview-digest-required")
        existing = self.connection.execute("SELECT batch_id,request_digest,state,manifest FROM batches WHERE operation_id=? OR batch_id=?",
                                           (request.operation_id, request.batch_id)).fetchall()
        if existing:
            if len(existing) != 1 or existing[0][1] != request.fingerprint():
                raise MappingError("operation-id-reused")
            match existing[0][2]:
                case "committed":
                    return self.receipt(existing[0][0])
                case "prepared":
                    return Prepared.model_validate_json(existing[0][3])
                case "aborted":
                    raise MappingError("operation-aborted")
                case unreachable:
                    assert_never(unreachable)
        if self.recovery.prepared:
            raise MappingError("prepared-recovery-required")
        if request.parent != self.recovery.root:
            raise MappingError("stale-parent")
        self._evidence(request)
        changes = []
        adapter = TypeAdapter(MappingRecord | Support)
        for proposed in request.changes:
            row = self.connection.execute("SELECT payload,token,digest FROM materialized WHERE key=?", (proposed.key,)).fetchone()
            before = adapter.validate_json(row[0]) if row and row[0] is not None else None
            token = hashlib.sha256(f"{request.fingerprint()}:{proposed.key}".encode()).hexdigest()
            changes.append(Change(key=proposed.key, before=before, after=proposed.after,
                                  before_token=row[1] if row else None, after_token=token,
                                  before_digest=image_digest(before), after_digest=image_digest(proposed.after)))
        prepared = Prepared(request=request, request_digest=request.fingerprint(), authorization=authorization,
                            changes=tuple(changes))
        self.cutpoint("before-P")
        with transaction(self.connection):
            for artifact in request.artifacts:
                self.connection.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?)",
                                        (artifact.digest, artifact.model_dump_json()))
                self.cutpoint("P-artifact")
            self.connection.execute("INSERT INTO batches VALUES(?,?,?,?,?,?,?)", (request.batch_id,
                request.operation_id, request.fingerprint(), "prepared", prepared.model_dump_json(),
                prepared.fingerprint(), request.inverse_of))
            self.cutpoint("P-manifest")
        self.cutpoint("after-P")
        self.recovery = reconcile(self.connection)
        return prepared

    def _evidence(self, request: BatchRequest) -> None:
        known = {row[0] for row in self.connection.execute("SELECT digest FROM artifacts")}
        known.update(a.digest for a in request.artifacts)
        required = {request.consent_ref}
        for mutation in request.changes:
            match mutation.after:
                case MappingRecord() as record:
                    fields = (record, *record.subjects, *record.relations,
                              *(r for s in record.subjects for r in s.relations))
                    required.update(ref for field in fields for ref in field.evidence_refs)
                case Support() as support:
                    required.add(support.evidence_ref)
                case None:
                    pass
                case unreachable:
                    assert_never(unreachable)
        if not required <= known:
            raise MappingError("missing-evidence")

    def publish(self, batch_id: str) -> ExecutionReceipt:
        self.recovery = reconcile(self.connection)
        row = self.connection.execute("SELECT state,manifest FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
        if row is None:
            raise MappingError("unknown-batch")
        if row[0] == "committed":
            return self.receipt(batch_id)
        if row[0] != "prepared":
            raise MappingError("batch-not-prepared")
        prepared = Prepared.model_validate_json(row[1])
        self._evidence(prepared.request)
        parent = prepared.request.parent
        root = next_root(parent, prepared.fingerprint())
        receipt = receipt_for(prepared, root)
        self.cutpoint("before-C")
        with transaction(self.connection):
            if root_of(self.connection) != parent:
                raise MappingError("publication-parent-conflict")
            self.connection.execute("INSERT INTO commits VALUES(?,?,?)", (root.revision, batch_id, receipt.model_dump_json()))
            self.cutpoint("C-marker")
            for index, change in enumerate(prepared.changes):
                self.connection.execute("INSERT INTO events VALUES(?,?,?)", (root.revision, index, change.model_dump_json()))
                self.cutpoint("C-event")
                self.connection.execute("INSERT OR REPLACE INTO materialized VALUES(?,?,?,?)", (change.key,
                    None if change.after is None else change.after.model_dump_json(), change.after_token, change.after_digest))
                self.cutpoint("C-row")
            self.connection.execute("UPDATE batches SET state='committed' WHERE batch_id=?", (batch_id,))
            self.connection.execute("UPDATE root SET payload=? WHERE singleton=1 AND payload=?",
                                    (root.model_dump_json(), parent.model_dump_json()))
            if self.connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise MappingError("root-compare-failed")
            self.cutpoint("C-root")
        self.cutpoint("after-C")
        self.recovery = reconcile(self.connection)
        self.cutpoint("acknowledgement")
        return receipt

    def receipt(self, batch_id: str) -> ExecutionReceipt:
        row = self.connection.execute("SELECT payload FROM commits WHERE batch_id=?", (batch_id,)).fetchone()
        if row is None:
            raise MappingError("uncommitted-receipt")
        return ExecutionReceipt.model_validate_json(row[0])

    def abort(self, batch_id: str) -> None:
        self.recovery = reconcile(self.connection)
        with transaction(self.connection):
            self.connection.execute("UPDATE batches SET state='aborted' WHERE batch_id=? AND state='prepared'", (batch_id,))
        self.recovery = reconcile(self.connection)

    def undo(self, batch_id: str) -> ExecutionReceipt:
        """Exactly one inverse; both token and after digest are required, including tombstones."""
        self.recovery = reconcile(self.connection)
        self.receipt(batch_id)
        prior = self.connection.execute("SELECT batch_id,state FROM batches WHERE inverse_of=?", (batch_id,)).fetchone()
        if prior:
            return self.publish(prior[0])
        row = self.connection.execute("SELECT manifest FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
        original = Prepared.model_validate_json(row[0])
        changes, conflicts = [], []
        for change in original.changes:
            current = self.connection.execute("SELECT token,digest FROM materialized WHERE key=?", (change.key,)).fetchone()
            if current != (change.after_token, change.after_digest):
                conflicts.append(change.key)
            else:
                changes.append(Mutation(key=change.key, after=change.before))
        operation = "inverse:" + batch_id
        authorization = Artifact.capture(f"explicit-batch-undo:{batch_id}".encode())
        request = BatchRequest(parent=self.recovery.root, batch_id=operation, operation_id=operation,
                               name=operation, changes=tuple(changes), artifacts=(authorization,),
                               consent_ref=authorization.digest, inverse_of=batch_id, conflicts=tuple(conflicts))
        self.prepare(request, request.fingerprint())
        return self.publish(operation)
