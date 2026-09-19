"""SQLite persistence and the frozen CSV row schema."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Final, Iterator

from pydantic import BaseModel, ConfigDict, Field

COLUMNS: Final = (
    "sha16", "abs_path", "path_rel", "filename", "width", "height", "filesize", "phash",
    "family_id", "aes_v25", "topiq_iaa", "topiq_nr", "qrealign", "hpsv3_mu", "hpsv3_sigma", "nsfw_prob", "identity_sim",
    "confusable_margin", "novelty", "consensus_z", "disagreement", "gaming_delta",
    "flags", "proposed_tier", "thumb_rel",
)


class Row(BaseModel):
    """Mutable accumulation of completed pipeline stages; validated at disk boundaries."""
    model_config = ConfigDict(allow_inf_nan=False)
    sha16: str
    sha256: str
    abs_path: str
    path_rel: str
    filename: str
    width: int
    height: int
    filesize: int
    phash: str
    mode: str
    family_id: str = ""
    aes_v25: float | None = None
    topiq_iaa: float | None = None
    topiq_nr: float | None = None
    qrealign: float | None = None
    hpsv3_mu: float | None = None
    hpsv3_sigma: float | None = Field(default=None, ge=0)
    nsfw_prob: float | None = None
    identity_sim: float | None = None
    confusable_margin: float | None = None
    novelty: float | None = None
    consensus_z: float | None = None
    disagreement: float | None = None
    gaming_delta: float | None = None
    flags: str = ""
    proposed_tier: str = ""
    thumb_rel: str = ""


@contextmanager
def connection(out: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(out / "manifest.sqlite")
    try:
        db.execute("CREATE TABLE IF NOT EXISTS images (position INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS timings (pass TEXT, seconds REAL, images INTEGER, cached INTEGER, load_seconds REAL)")
        fields = ",".join(f"json_extract(payload, '$.{key}') AS {key}" for key in (*COLUMNS, "sha256", "mode"))
        db.execute("DROP VIEW IF EXISTS scores")
        db.execute(f"CREATE VIEW scores AS SELECT {fields} FROM images ORDER BY position")
        yield db
        db.commit()
    finally:
        db.close()


def save_rows(out: Path, rows: list[Row]) -> None:
    with connection(out) as db:
        db.execute("DELETE FROM images")
        db.executemany("INSERT INTO images VALUES (?,?)", [(i, row.model_dump_json()) for i, row in enumerate(rows)])


def load_rows(out: Path) -> list[Row]:
    with connection(out) as db:
        return [Row.model_validate_json(r[0]) for r in db.execute("SELECT payload FROM images ORDER BY position")]


def meta(out: Path, key: str, value: str) -> None:
    with connection(out) as db:
        db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
