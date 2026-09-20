"""Monotonic SQLite migration with verified backup and transactional recovery."""
import hashlib
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Final

VERSION: Final = 1


class MigrationError(RuntimeError):
    """Schema/backup integrity could not be established."""


def integrity(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise MigrationError("SQLite integrity check failed")


def migrate(connection: sqlite3.Connection, path: Path, columns: tuple[str, ...],
            *, checkpoint: Callable[[str], None] = lambda stage: None) -> None:
    """Version zero includes legacy manifests. DDL and version commit atomically."""
    integrity(connection)
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > VERSION:
        raise MigrationError("Unsupported future schema version")
    if version == VERSION:
        return
    statements = [
        "CREATE TABLE IF NOT EXISTS images (position INTEGER PRIMARY KEY, payload TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS timings (pass TEXT, seconds REAL, images INTEGER, cached INTEGER, load_seconds REAL)",
        "CREATE TABLE IF NOT EXISTS journal_events (sequence INTEGER PRIMARY KEY, operation_id TEXT, kind TEXT, payload TEXT NOT NULL)",
        "DROP VIEW IF EXISTS scores",
        "CREATE VIEW scores AS SELECT " + ",".join(
            f"json_extract(payload, '$.{key}') AS {key}" for key in (*columns, "mode")) + " FROM images ORDER BY position",
    ]
    digest = hashlib.sha256("\n".join(statements).encode()).hexdigest()
    # Ledger bootstrap is additive and separately durable: interrupted attempts remain observable.
    rebuilding = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='images'").fetchone() is not None
    connection.execute("CREATE TABLE IF NOT EXISTS migrations (attempt INTEGER PRIMARY KEY, from_version INTEGER, "
                       "to_version INTEGER, digest TEXT, outcome TEXT NOT NULL)")
    connection.commit()
    backup = path.with_name(path.name + f".pre-v{VERSION}.bak")
    if rebuilding and not backup.exists():
        temporary = backup.with_suffix(".tmp")
        with closing(sqlite3.connect(temporary)) as destination:
            connection.backup(destination)
            integrity(destination)
        temporary.replace(backup)
    elif rebuilding:
        with closing(sqlite3.connect(backup)) as saved:
            integrity(saved)
    checkpoint("after_backup")
    connection.execute("UPDATE migrations SET outcome='interrupted' WHERE outcome='started'")
    cursor = connection.execute("INSERT INTO migrations(from_version,to_version,digest,outcome) VALUES(?,?,?,'started')",
                                (version, VERSION, digest))
    attempt = cursor.lastrowid
    connection.commit()
    checkpoint("after_ledger")
    # Context rolls back DDL and user_version together even on injected exceptions.
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        for statement in statements:
            connection.execute(statement)
        checkpoint("after_schema")
        integrity(connection)
        connection.execute(f"PRAGMA user_version={VERSION}")
        checkpoint("after_version")
        connection.execute("UPDATE migrations SET outcome='applied' WHERE attempt=?", (attempt,))
        checkpoint("before_commit")
    integrity(connection)
