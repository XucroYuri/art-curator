"""Artifact failures must not trigger a different SigLIP model."""
import json
from pathlib import Path

import pytest
import numpy as np

from artcurator import db, models


@pytest.mark.parametrize("failure", [OSError, RuntimeError, ValueError])
def test_siglip_refuses_substitution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[Exception]) -> None:
    # Given a requested artifact/revision that cannot be loaded, without GPU/network access.
    attempts: list[str] = []
    error = failure("requested revision unavailable")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "google--siglip-so400m-patch14-384-revision.txt").write_text("a" * 40, encoding="utf-8")

    def unavailable(out: Path, repo: str = "google/siglip-so400m-patch14-384") -> models.Predictor:
        attempts.append(repo)
        raise error

    monkeypatch.setattr(models, "siglip", unavailable)
    monkeypatch.setattr(models, "release", lambda: None)
    # When loading the signal, then the original failure propagates.
    with pytest.raises(failure) as caught:
        models.load("siglip", tmp_path)
    assert caught.value is error
    assert attempts == ["google/siglip-so400m-patch14-384"]
    with db.connection(tmp_path) as connection:
        record = json.loads(connection.execute("SELECT value FROM meta WHERE key='signal_unavailable_siglip'").fetchone()[0])
    assert record["signal"] == "siglip"
    assert record["requested_model"] == attempts[0]
    assert record["requested_revision"] == "a" * 40
    assert record["error_type"] == failure.__name__


def test_siglip_success_clears_previous_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a recovered artifact after an earlier unavailable attempt.
    db.meta(tmp_path, "signal_unavailable_siglip", '{"signal":"siglip"}')
    predictor = models.Predictor("requested", "pinned", "pixels", lambda images: np.empty((0, 1)))
    monkeypatch.setattr(models, "siglip", lambda out: predictor)
    # When the requested artifact loads successfully.
    result = models.load("siglip", tmp_path)
    # Then stale failure evidence no longer describes current availability.
    assert result is predictor
    with db.connection(tmp_path) as connection:
        assert connection.execute("SELECT value FROM meta WHERE key='signal_unavailable_siglip'").fetchone() is None
