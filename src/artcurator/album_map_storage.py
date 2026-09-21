"""One SQLite connection and an OS-held admission lock, no sidecar authority."""
import hashlib
import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Final, Iterator

from .album_map_protocol import Root
from .album_map_schema import MappingError

MIGRATION_1: Final = (
    "CREATE TABLE migrations(version INTEGER PRIMARY KEY, checksum TEXT NOT NULL)",
    "CREATE TABLE binding(library_id TEXT PRIMARY KEY, canonical_path TEXT NOT NULL)",
    "CREATE TABLE root(singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL)",
    "CREATE TABLE artifacts(digest TEXT PRIMARY KEY, payload TEXT NOT NULL)",
    "CREATE TABLE batches(batch_id TEXT PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL, "
    "request_digest TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('prepared','committed','aborted')), "
    "manifest TEXT NOT NULL, manifest_digest TEXT NOT NULL, inverse_of TEXT UNIQUE REFERENCES batches(batch_id))",
    "CREATE UNIQUE INDEX one_prepared ON batches(state) WHERE state='prepared'",
    "CREATE TABLE commits(revision INTEGER PRIMARY KEY, batch_id TEXT UNIQUE NOT NULL REFERENCES batches(batch_id), "
    "payload TEXT NOT NULL)",
    "CREATE TABLE events(revision INTEGER NOT NULL REFERENCES commits(revision), position INTEGER NOT NULL, "
    "payload TEXT NOT NULL, PRIMARY KEY(revision,position))",
    "CREATE TABLE materialized(key TEXT PRIMARY KEY, payload TEXT, token TEXT NOT NULL, digest TEXT NOT NULL)",
)
MIGRATION_DIGEST: Final = hashlib.sha256("\n".join(MIGRATION_1).encode()).hexdigest()


def runtime_gate() -> None:
    version = sqlite3.sqlite_version_info
    if not (version >= (3, 51, 3) or version in {(3, 44, 6), (3, 50, 7)}):
        raise MappingError("sqlite-wal-reset-fix-required")


@contextmanager
def admission(path: Path) -> Iterator[None]:
    """A canonical database binding refuses writable copies; lock survives no process."""
    lock = path.with_suffix(path.suffix + ".admission")
    with lock.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise MappingError("library-busy") from error
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise MappingError("library-busy") from error
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    finally:
        if connection.in_transaction:
            connection.rollback()


@contextmanager
def connect(path: Path, library_id: str | None = None) -> Iterator[sqlite3.Connection]:
    runtime_gate()
    canonical = path.resolve()
    if str(canonical).startswith("\\\\"):
        raise MappingError("local-filesystem-required")
    with admission(canonical):
        if library_id is not None:
            # Exclusive creation: never recreate a disappeared enrolled authority implicitly.
            with canonical.open("xb"):
                pass
        with closing(sqlite3.connect(canonical.as_uri() + "?mode=rw", uri=True,
                                     isolation_level=None, timeout=0)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode != "wal" or connection.execute("PRAGMA synchronous").fetchone()[0] != 2:
                raise MappingError("sqlite-settings")
            if library_id is not None:
                with transaction(connection):
                    for statement in MIGRATION_1:
                        connection.execute(statement)
                    connection.execute("INSERT INTO migrations VALUES(1,?)", (MIGRATION_DIGEST,))
                    connection.execute("INSERT INTO binding VALUES(?,?)", (library_id, str(canonical)))
                    root = genesis(library_id)
                    connection.execute("INSERT INTO root VALUES(1,?)", (root.model_dump_json(),))
                    connection.execute("PRAGMA user_version=1")
            binding = connection.execute("SELECT library_id,canonical_path FROM binding").fetchall()
            if len(binding) != 1 or Path(binding[0][1]).resolve() != canonical:
                raise MappingError("library-fork-binding")
            yield connection


def genesis(library_id: str) -> Root:
    return Root(library_id=library_id, revision=0,
                root_digest=hashlib.sha256(f"album-store-v1:genesis:{library_id}".encode()).hexdigest())
