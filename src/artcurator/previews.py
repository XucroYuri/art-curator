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
from .resources import Budgets, ByteBudget, Deferred, decode_estimate, record_budget
from .cache_identity import verify_content


@dataclass(frozen=True, slots=True)
class PreviewResult:
    rows: int
    unique: int
    generated: int
    seconds: float
    deferred: int = 0


def previews(settings: Settings) -> PreviewResult:
    """Read inventory without updates; publish JPEGs and coordinator resource metadata."""
    started = time.perf_counter()
    manifest = (settings.out / "manifest.sqlite").resolve()
    with sqlite3.connect(db.readonly_uri(manifest), uri=True) as connection:
        rows = [db.Row.model_validate_json(item[0]) for item in connection.execute(
            "SELECT payload FROM images ORDER BY position")]
    hashes: dict[str, db.Row] = {}
    for row in rows:
        if len(row.sha256) != 64 or any(c not in "0123456789abcdef" for c in row.sha256):
            raise ValueError("Invalid full preview content identity")
        hashes[row.sha256] = row
    directory = settings.out / "previews"
    directory.mkdir(exist_ok=True)
    budget = ByteBudget(min(Budgets.current().host_bytes // 4, 512 * 1024**2))

    def generate(row: db.Row) -> tuple[int, str]:
        destination = directory / f"{row.sha256}.jpg"
        if destination.exists():
            return 0, ""
        temporary = destination.with_suffix(".jpg.tmp")
        try:
            verify_content(row)
            with budget.reserve(decode_estimate(Path(row.abs_path))), pixels(Path(row.abs_path)) as image:
                image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                image.info.clear()
                image.save(temporary, "JPEG", quality=88)
            temporary.replace(destination)
        except Deferred as error:
            return 0, str(error)
        finally:
            temporary.unlink(missing_ok=True)
        return 1, ""

    generated = 0
    rejected = []
    with record_budget(settings.out, "previews", budget), ordered_map(generate, hashes.values(), workers=settings.workers, capacity=settings.workers * 2) as results:
        for row, (count, reason) in zip(hashes.values(), results, strict=True):
            generated += count
            if reason:
                rejected.append({"sha256": row.sha256, "path": row.abs_path, "reason": reason})
                logging.warning("preview deferred path=%s reason=%s", row.abs_path, reason)
    db.write_json(settings.out / "previews-rejected.json", rejected)
    result = PreviewResult(len(rows), len(hashes), generated, time.perf_counter() - started, len(rejected))
    db.write_json(settings.out / "previews-timing.json", {
        "rows": result.rows, "unique": result.unique, "generated": generated,
        "seconds": result.seconds, "workers": settings.workers, "deferred": result.deferred})
    logging.info("previews complete rows=%d unique=%d generated=%d seconds=%.3f",
                 result.rows, result.unique, generated, result.seconds)
    return result
