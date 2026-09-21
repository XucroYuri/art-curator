"""Read-only reconciliation: replay every committed event, never repair by recency."""
import sqlite3

from .album_map_protocol import Artifact, Change, ExecutionReceipt, Prepared, Recovery, Root, image_digest, next_root
from .album_map_schema import MappingError
from .album_map_storage import MIGRATION_DIGEST, genesis


def root_of(connection: sqlite3.Connection) -> Root:
    rows = connection.execute("SELECT payload FROM root").fetchall()
    if len(rows) != 1:
        raise MappingError("root-cardinality")
    return Root.model_validate_json(rows[0][0])


def validate_prepared(prepared: Prepared) -> None:
    if prepared.request_digest != prepared.request.fingerprint() or prepared.authorization != prepared.request_digest:
        raise MappingError("prepared-request-digest")
    if len(prepared.changes) != len(prepared.request.changes):
        raise MappingError("prepared-change-count")
    for change, proposed in zip(prepared.changes, prepared.request.changes, strict=True):
        if (change.key != proposed.key or change.after != proposed.after
                or change.before_digest != image_digest(change.before)
                or change.after_digest != image_digest(change.after)):
            raise MappingError("before-after-digest")


def reconcile(connection: sqlite3.Connection) -> Recovery:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise MappingError("sqlite-integrity")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise MappingError("sqlite-foreign-keys")
    if (connection.execute("PRAGMA user_version").fetchone()[0] != 1
            or connection.execute("SELECT version,checksum FROM migrations").fetchall() != [(1, MIGRATION_DIGEST)]):
        raise MappingError("migration-ledger")
    actual_root = root_of(connection)
    library_id = connection.execute("SELECT library_id FROM binding").fetchone()[0]
    expected_root = genesis(library_id)
    artifacts = {}
    for digest, payload in connection.execute("SELECT digest,payload FROM artifacts"):
        artifact = Artifact.model_validate_json(payload)
        if artifact.digest != digest:
            raise MappingError("artifact-key")
        artifacts[digest] = artifact
    batches = {}
    pending = []
    for batch_id, operation, request_digest, state, payload, digest, inverse in connection.execute("SELECT * FROM batches"):
        prepared = Prepared.model_validate_json(payload)
        validate_prepared(prepared)
        if (prepared.fingerprint() != digest or prepared.request.batch_id != batch_id
                or prepared.request.operation_id != operation or request_digest != prepared.request_digest
                or prepared.request.inverse_of != inverse):
            raise MappingError("batch-manifest-digest")
        for artifact in prepared.request.artifacts:
            if artifacts.get(artifact.digest) != artifact:
                raise MappingError("missing-evidence")
        batches[batch_id] = (prepared, state)
        if state == "prepared":
            pending.append(batch_id)
            if prepared.request.parent != actual_root:
                raise MappingError("prepared-parent-divergence")
    materialized: dict[str, tuple[str | None, str, str]] = {}
    committed = set()
    for revision, batch_id, payload in connection.execute("SELECT * FROM commits ORDER BY revision"):
        receipt = ExecutionReceipt.model_validate_json(payload)
        prepared, state = batches[batch_id]
        proposed_root = next_root(expected_root, prepared.fingerprint())
        expected_receipt = receipt_for(prepared, proposed_root)
        if (state != "committed" or revision != proposed_root.revision or receipt != expected_receipt
                or prepared.request.parent != expected_root):
            raise MappingError("commit-lineage")
        events = connection.execute("SELECT position,payload FROM events WHERE revision=? ORDER BY position", (revision,)).fetchall()
        if len(events) != len(prepared.changes):
            raise MappingError("event-count")
        for index, ((position, event), change) in enumerate(zip(events, prepared.changes, strict=True)):
            previous = materialized.get(change.key)
            if (position != index or Change.model_validate_json(event) != change
                    or change.before_token != (previous[1] if previous else None)
                    or change.before_digest != (previous[2] if previous else image_digest(None))):
                raise MappingError("event-chain")
            materialized[change.key] = (None if change.after is None else change.after.model_dump_json(),
                                        change.after_token, change.after_digest)
        committed.add(batch_id)
        expected_root = proposed_root
    if committed != {key for key, (_, state) in batches.items() if state == "committed"}:
        raise MappingError("missing-commit")
    if actual_root != expected_root:
        raise MappingError("root-lineage")
    actual = {key: (payload, token, digest) for key, payload, token, digest in connection.execute("SELECT * FROM materialized")}
    if actual != materialized:
        raise MappingError("materialized-divergence")
    for batch_id in pending:
        for change in batches[batch_id][0].changes:
            previous = materialized.get(change.key)
            if (change.before_token != (previous[1] if previous else None)
                    or change.before_digest != (previous[2] if previous else image_digest(None))):
                raise MappingError("prepared-before-state")
    return Recovery(root=actual_root, prepared=tuple(pending), sqlite_version=sqlite3.sqlite_version,
                    status="explicit-resume-or-abort" if pending else "reconciled")


def receipt_for(prepared: Prepared, root: Root) -> ExecutionReceipt:
    return ExecutionReceipt(library_id=root.library_id, batch_id=prepared.request.batch_id,
                            operation_id=prepared.request.operation_id, revision=root.revision,
                            parent_revision=prepared.request.parent.revision, root_digest=root.root_digest,
                            manifest_digest=prepared.fingerprint(), consent_ref=prepared.request.consent_ref,
                            mapping_mutations=sum(not c.key.startswith("support:") for c in prepared.changes),
                            conflicts=prepared.request.conflicts, partial_undo=bool(prepared.request.conflicts),
                            inverse_of=prepared.request.inverse_of)
