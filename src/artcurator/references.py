"""Reference manifests and cosine-derived signals, independent of path spelling."""
import logging
from pathlib import Path

import numpy as np

from . import db
from .cache import Pass, infer
from .config import Settings
from .models import Predictor
from .scan import image_paths, inspect
from .parallel import ordered_map


def reference_rows(root: Path, workers: int = 8) -> list[db.Row]:
    with ordered_map(lambda path: inspect(path, root), image_paths(root),
                     workers=workers, capacity=workers * 2) as rows:
        return sorted(rows, key=lambda row: row.sha256)


def dedup(rows: list[db.Row]) -> list[db.Row]:
    # Deterministic greedy representatives: every retained pair has distance >4.
    retained: list[db.Row] = []
    for row in rows:
        value = int(row.phash, 16)
        if all((value ^ int(other.phash, 16)).bit_count() > 4 for other in retained):
            retained.append(row)
    return retained


def normalize(matrix: np.ndarray) -> np.ndarray:
    values = matrix.astype(np.float32)
    return values / np.maximum(np.linalg.norm(values, axis=1, keepdims=True), 1e-12)


def derive(settings: Settings, rows: list[db.Row], predictor: Predictor) -> None:
    matrix = normalize(np.load(settings.out / "embeddings.npy", allow_pickle=False))
    own = reference_rows(settings.references, settings.workers)
    refs = dedup(own)
    if not refs:
        raise ValueError("Identity reference set is empty")
    other_roots = [folder for character in settings.characters_root.iterdir() if character.is_dir()
                   and character.resolve() != settings.references.parent.resolve()
                   for folder in character.glob("*参考图集*") if folder.is_dir()]
    others = [row for root in other_roots for row in reference_rows(root, settings.workers)]
    posted = reference_rows(settings.posted, settings.workers) if settings.posted.is_dir() else []
    groups = [("identity_refs", refs), ("confusable_refs", others), ("posted", posted)]
    db.write_json(settings.out / "cache/reference_manifest.json", {
        "own_before_dedup": len(own), "own_after_dedup": len(refs),
        "other_folders": [str(p) for p in other_roots],
        "groups": {name: [r.model_dump() for r in group] for name, group in groups},
    })
    for name, group in groups:
        if not group:
            logging.warning("optional reference set absent name=%s", name)
            continue
        embeddings = infer(group, Pass(settings.out, name, settings.batch_size, predictor,
                                       workers=settings.workers, prefetch_batches=settings.prefetch_batches))
        similarity = np.clip(matrix @ normalize(embeddings).T, -1, 1)
        match name:
            case "identity_refs":
                count = min(3, len(group))
                scores = np.sort(similarity, axis=1)[:, -count:].mean(axis=1)
                for row, value in zip(rows, scores, strict=True):
                    row.identity_sim = float(value)
            case "confusable_refs":
                for row, value in zip(rows, similarity.max(axis=1), strict=True):
                    row.confusable_margin = float(row.identity_sim - value)
            case "posted":
                for row, value in zip(rows, similarity.max(axis=1), strict=True):
                    row.novelty = float(1 - value)
    db.save_rows(settings.out, rows)
