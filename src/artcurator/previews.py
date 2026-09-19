"""Content-addressed viewing assets, never used as scoring inputs."""
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import db
from .config import Settings
from .parallel import ordered_map
from .scan import pixels


@dataclass(frozen=True, slots=True)
class PreviewResult:
    rows: int
    unique: int
    generated: int
    seconds: float


def previews(settings: Settings) -> PreviewResult:
    """Read manifest in SQLite read-only mode; atomically publish q88 JPEGs."""
    started = time.perf_counter()
    manifest = (settings.out / "manifest.sqlite").resolve()
    with sqlite3.connect(f"{manifest.as_uri()}?mode=ro", uri=True) as connection:
        rows = [db.Row.model_validate_json(item[0]) for item in connection.execute(
            "SELECT payload FROM images ORDER BY position")]
    hashes: dict[str, db.Row] = {}
    for row in rows:
        if len(row.sha16) != 16 or any(c not in "0123456789abcdef" for c in row.sha16):
            raise ValueError(f"Invalid preview key: {row.sha16}")
        if row.sha16 in hashes and hashes[row.sha16].sha256 != row.sha256:
            raise ValueError(f"sha16 collision: {row.sha16}")
        hashes[row.sha16] = row
    directory = settings.out / "previews"
    directory.mkdir(exist_ok=True)

    def generate(row: db.Row) -> int:
        destination = directory / f"{row.sha16}.jpg"
        if destination.exists():
            return 0
        temporary = destination.with_suffix(".jpg.tmp")
        try:
            with pixels(Path(row.abs_path)) as image:
                image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                image.info.clear()
                image.save(temporary, "JPEG", quality=88)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return 1

    with ordered_map(generate, hashes.values(), workers=settings.workers, capacity=settings.workers * 2) as results:
        generated = sum(results)
    result = PreviewResult(len(rows), len(hashes), generated, time.perf_counter() - started)
    db.write_json(settings.out / "previews-timing.json", {
        "rows": result.rows, "unique": result.unique, "generated": generated,
        "seconds": result.seconds, "workers": settings.workers})
    logging.info("previews complete rows=%d unique=%d generated=%d seconds=%.3f",
                 result.rows, result.unique, generated, result.seconds)
    return result
