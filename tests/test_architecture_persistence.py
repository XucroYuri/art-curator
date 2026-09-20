"""Real SQLite and synthetic move recovery regressions."""
import sqlite3
from pathlib import Path

import pytest


@pytest.mark.parametrize("cutpoint", ["after_backup", "after_ledger", "after_schema", "after_version", "before_commit"])
def test_migration_when_interrupted(tmp_path: Path, cutpoint: str) -> None:
    # Given a legacy database and interruption inside a rebuilding migration.
    from artcurator import db, migrations
    path = tmp_path / "manifest.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE images(position INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO images VALUES(0, '{\"sentinel\":42}')")

    def interrupt(stage: str) -> None:
        if stage == cutpoint:
            raise RuntimeError("injected interruption")

    with sqlite3.connect(path) as connection:
        with pytest.raises(RuntimeError, match="injected"):
            migrations.migrate(connection, path, db.COLUMNS, checkpoint=interrupt)
    # When retried; then schema and data are recovered exactly, once.
    with db.connection(tmp_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == migrations.VERSION
        assert connection.execute("SELECT payload FROM images").fetchone()[0] == '{"sentinel":42}'
        assert connection.execute("SELECT count(*) FROM migrations WHERE outcome='applied'").fetchone()[0] == 1
    assert list(tmp_path.glob("manifest.sqlite.pre-v*.bak"))


def test_journal_when_tail_is_torn(tmp_path: Path) -> None:
    # Given a completed synthetic move and a torn final undo record.
    from artcurator import apply, db, undo
    from artcurator._moves import read_log
    from test_apply import fixture_files
    out, config, sources = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    apply.execute(out, "APPLY-" + plan.digest[:8])
    log = out / "disposition_log.jsonl"
    with log.open("ab") as handle:
        handle.write(b'{"torn":')
    # When undo recovers the validated prefix; then original bytes and evidence survive.
    assert undo.revert(out) == ["undone"]
    assert sources[0].read_bytes() == b"pixels-0"
    entries = read_log(log)
    assert [entry.sequence for entry in entries] == sorted({entry.sequence for entry in entries})
    assert list(out.glob("disposition_log.jsonl.torn-*.bak"))
    with db.connection(out) as connection:
        assert connection.execute("SELECT count(*) FROM journal_events WHERE kind='recovery'").fetchone()[0] == 1
    assert undo.revert(out) == ["already_undone"]


def test_journal_when_only_done_record_is_truncated(tmp_path: Path) -> None:
    # Given source unlink followed by damage to the sole durable done record.
    from artcurator import apply, undo
    from test_apply import fixture_files
    out, config, sources = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    apply.execute(out, "APPLY-" + plan.digest[:8])
    log = out / "disposition_log.jsonl"
    with log.open("r+b") as handle:
        handle.truncate(30)
    # When recovery reconciles the sealed plan with destination bytes; then undo is safe.
    assert undo.revert(out) == ["undone"]
    assert sources[0].read_bytes() == b"pixels-0"


def test_journal_when_midstream_record_is_corrupt(tmp_path: Path) -> None:
    # Given a framed record followed by another record, with corruption in the first.
    from artcurator import apply, undo
    from artcurator._moves import MoveError, read_log
    from test_apply import fixture_files
    out, config, _ = fixture_files(tmp_path)
    plan = apply.make_plan(out, config)
    apply.execute(out, "APPLY-" + plan.digest[:8])
    undo.revert(out)
    log = out / "disposition_log.jsonl"
    log.write_bytes(log.read_bytes().replace(b'"sequence":1', b'"sequence":9', 1))
    # When replayed; then midstream corruption is refused, never truncated away.
    with pytest.raises(MoveError, match="integrity"):
        read_log(log)
