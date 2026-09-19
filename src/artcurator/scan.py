"""Pixel-only decoding: skip PNG ancillary payloads BEFORE Pillow sees them."""
import hashlib
import io
import logging
import struct
import time
from pathlib import Path

import imagehash
from PIL import Image, ImageFile

from . import db
from .config import Settings
from .parallel import ordered_map


def _source(path: Path) -> bytes:
    """Keep critical PNG chunks plus pixel transparency; seek past all other chunks.

    No PNG text, ICC, EXIF, or other metadata payload is read by the decoder.
    SHA256 separately hashes opaque file bytes solely for integrity/cache identity.
    """
    with path.open("rb") as handle:
        signature = handle.read(8)
        if signature == b"\x89PNG\r\n\x1a\n":
            clean = bytearray(signature)
            while True:
                header = handle.read(8)
                if len(header) != 8:
                    raise ValueError(f"Truncated PNG: {path}")
                length, kind = struct.unpack(">I4s", header)
                if kind in {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}:
                    content = handle.read(length + 4)
                    if len(content) != length + 4:
                        raise ValueError(f"Truncated PNG chunk: {path}")
                    clean.extend(header + content)
                else:
                    handle.seek(length + 4, io.SEEK_CUR)
                if kind == b"IEND":
                    break
            return bytes(clean)
        else:
            handle.seek(0)
            return handle.read()


def decoded(path: Path) -> tuple[Image.Image, str]:
    """Two fresh strict reads, then incremental strict decode of sanitized bytes.

    Never enables LOAD_TRUNCATED_IMAGES or substitutes pixels. Ancillary PNG
    exclusion applies to every attempt, including the fallback parser.
    """
    errors: list[str] = []
    for attempt in range(3):
        try:
            data = _source(path)
            if attempt < 2:
                image = Image.open(io.BytesIO(data))
            else:
                parser = ImageFile.Parser()
                for offset in range(0, len(data), 65536):
                    parser.feed(data[offset:offset + 65536])
                image = parser.close()
            with image:
                image.load()
                result = Image.frombytes("RGB", image.size, image.convert("RGB").tobytes()), image.mode
            if errors:
                logging.warning("decode recovered path=%s attempt=%d fallback=%s errors=%s",
                                path, attempt + 1, attempt == 2, errors)
            return result
        except (OSError, ValueError) as error:
            errors.append(f"{type(error).__name__}: {error}")
    raise OSError(f"Strict decode failed after 3 attempts (last=incremental): {path}; {errors}")


def pixels(path: Path) -> Image.Image:
    return decoded(path)[0]


def image_paths(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                  and not p.name.startswith(".backup-baseline-"))


def inspect(path: Path, root: Path) -> db.Row:
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    image, mode = decoded(path)
    return db.Row(sha16=digest[:16], sha256=digest, abs_path=str(path.absolute()),
                  path_rel=str(path.relative_to(root)), filename=path.name,
                  width=image.width, height=image.height, filesize=path.stat().st_size,
                  phash=str(imagehash.phash(image, hash_size=16)), mode=mode)


def scan(settings: Settings, limit: int | None) -> list[db.Row]:
    started = time.perf_counter()
    paths = image_paths(settings.input)
    rows = []
    rejected = []
    # Keep detailed exceptions with their file, without shared worker mutation.
    def inspect_result(path: Path) -> tuple[db.Row | None, str]:
        try:
            return inspect(path, settings.input), ""
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            return None, f"{type(error).__name__}: {error}"

    with ordered_map(inspect_result, paths, workers=settings.workers, capacity=settings.workers * 2) as results:
        for path, (row, reason) in zip(paths, results, strict=True):
            if row is not None:
                rows.append(row)
            else:
                logging.warning("image rejected path=%s stage=inspect reason=%s", path, reason)
                rejected.append({"path": str(path), "stage": "inspect", "reason": reason})
    rows.sort(key=lambda r: r.sha256)
    rows = rows[:limit] if limit else rows
    if not rows:
        db.write_json(settings.out / "scan-rejected.json", rejected)
        raise ValueError("Empty corpus")
    hashes: dict[str, str] = {}
    thumbs = settings.out / "thumbs"
    thumbs.mkdir(exist_ok=True)
    for row in rows:
        if row.sha16 in hashes and hashes[row.sha16] != row.sha256:
            raise ValueError(f"sha16 collision: {row.sha16}")
        hashes[row.sha16] = row.sha256
        row.thumb_rel = f"thumbs/{row.sha16}.jpg"
    def thumbnail(row: db.Row) -> str:
        destination = settings.out / row.thumb_rel
        if destination.exists():
            return ""
        try:
            with pixels(Path(row.abs_path)) as image:
                image.thumbnail((384, 384), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                image.save(buffer, "JPEG", quality=82)
            destination.write_bytes(buffer.getvalue())
            return ""
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            return f"{type(error).__name__}: {error}"

    unique = list({row.sha16: row for row in rows}.values())
    failures: dict[str, str] = {}
    with ordered_map(thumbnail, unique, workers=settings.workers, capacity=settings.workers * 2) as results:
        for row, reason in zip(unique, results, strict=True):
            if reason:
                failures[row.sha16] = reason
    for row in rows:
        if row.sha16 in failures:
            reason = failures[row.sha16]
            logging.warning("image rejected path=%s stage=thumbnail reason=%s", row.abs_path, reason)
            rejected.append({"path": row.abs_path, "stage": "thumbnail", "reason": reason})
    rows = [row for row in rows if row.sha16 not in failures]
    db.write_json(settings.out / "scan-rejected.json", rejected)
    if not rows:
        raise ValueError("Empty corpus after thumbnail rejection")
    db.save_rows(settings.out, rows)
    db.meta(settings.out, "scanned_total", str(len(paths)))
    db.meta(settings.out, "scan_rejected", str(len(rejected)))
    elapsed = time.perf_counter() - started
    logging.info("scan complete images=%d selected=%d seconds=%.3f", len(paths), len(rows), elapsed)
    with db.connection(settings.out) as connection:
        connection.execute("INSERT INTO timings VALUES (?,?,?,?,?)", ("scan", elapsed, len(paths), 0, 0))
    return rows
