"""Sequential GPU passes with restartable per-image caches."""
import io
import subprocess
import time

import numpy as np
from PIL import Image, ImageEnhance

from . import db, models
from .cache import Pass, infer
from .config import ROOT, Settings
from .references import derive


def jpeg68(image: Image.Image) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=68)
    buffer.seek(0)
    with Image.open(buffer) as variant:
        return variant.convert("RGB")


def saturated(image: Image.Image) -> Image.Image:
    return ImageEnhance.Color(image).enhance(1.15)


def score(settings: Settings, only: str | None = None) -> None:
    rows = db.load_rows(settings.out)
    names = [only] if only else ["siglip", "aes_v25", "topiq_iaa", "topiq_nr", "qrealign", "nsfw_prob"]
    for name in names:
        if name == "qrealign":
            subprocess.run([str(ROOT / ".venv-qrealign/Scripts/python.exe"), "-m", "artcurator.qrealign_worker",
                            "--out", str(settings.out), "--workers", str(settings.workers),
                            "--prefetch-batches", str(settings.prefetch_batches)], check=True, cwd=ROOT)
            rows = db.load_rows(settings.out)
            continue
        started = time.perf_counter()
        predictor = models.load(name, settings.out)
        loaded = time.perf_counter() - started
        values = infer(rows, Pass(settings.out, name, settings.batch_size, predictor, loaded,
                                 workers=settings.workers, prefetch_batches=settings.prefetch_batches))
        match name:
            case "siglip":
                np.save(settings.out / "embeddings.npy", values.astype(np.float16), allow_pickle=False)
                db.write_json(settings.out / "embeddings_ids.json", [row.sha16 for row in rows])
                derive(settings, rows, predictor)
            case "aes_v25":
                for row, value in zip(rows, values, strict=True):
                    row.aes_v25 = float(value)
                sample = [row for row in rows if int(row.sha16[:8], 16) % 5 == 0]
                if sample:
                    jpeg = infer(sample, Pass(settings.out, "gaming_jpeg", settings.batch_size, predictor,
                                              variant="jpeg-q68", workers=settings.workers,
                                              prefetch_batches=settings.prefetch_batches), jpeg68)
                    saturation = infer(sample, Pass(settings.out, "gaming_saturation", settings.batch_size, predictor,
                                                    variant="saturation-1.15", workers=settings.workers,
                                                    prefetch_batches=settings.prefetch_batches), saturated)
                    for row, a, b in zip(sample, jpeg, saturation, strict=True):
                        row.gaming_delta = float(max(row.aes_v25 - a, row.aes_v25 - b))
            case "topiq_iaa" | "topiq_nr" | "nsfw_prob":
                for row, value in zip(rows, values, strict=True):
                    setattr(row, name, float(value))
            case _:
                raise ValueError(f"Unknown scoring pass: {name}")
        db.save_rows(settings.out, rows)
        del predictor
        models.release()
