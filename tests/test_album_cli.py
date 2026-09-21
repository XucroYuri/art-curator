import json
import subprocess
import sys
from pathlib import Path


def test_cli_initializes_when_library_explicit(tmp_path: Path) -> None:
    # Given a new synthetic destination and the real CLI boundary.
    command = [sys.executable, "-m", "artcurator.cli", "album-map", "--album-db",
               str(tmp_path / "album.sqlite"), "--album-op", "init", "--library-id", "synthetic"]
    # When invoking the command, then it returns a reconciled genesis root.
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["root"]["revision"] == 0


def test_cli_refuses_missing_database_when_read_requested(tmp_path: Path) -> None:
    # Given an absent database and no initialization intent.
    command = [sys.executable, "-m", "artcurator.cli", "album-map", "--album-db",
               str(tmp_path / "missing.sqlite"), "--album-op", "snapshot"]
    # When invoking the reader, then it fails without creating a replacement authority.
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert not (tmp_path / "missing.sqlite").exists()
