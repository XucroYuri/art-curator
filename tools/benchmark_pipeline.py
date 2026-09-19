"""Read-only 300-row benchmark; run with project .venv Python, before then after."""
import argparse
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np

from artcurator import db, models, scan
from artcurator.cache import Pass, infer
from artcurator.config import ROOT, confine_writes, environment, load


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["before", "after"])
    args = parser.parse_args()
    out = ROOT / "out/wave2-benchmark" / args.phase
    out.mkdir(parents=True, exist_ok=False)
    environment(out)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    confine_writes()
    original = ROOT / "out/review"
    with sqlite3.connect(f"{(original / 'manifest.sqlite').as_uri()}?mode=ro", uri=True) as connection:
        rows = [db.Row.model_validate_json(r[0]) for r in connection.execute(
            "SELECT payload FROM images ORDER BY position LIMIT 300")]
    paths = [Path(r.abs_path) for r in rows]
    settings = load(ROOT / "config.yaml").model_copy(update={"input": paths[0].parent, "out": out})
    protected = {name: hashlib.sha256((ROOT / f"out/{name}/scores.csv").read_bytes()).hexdigest()
                 for name in ("library", "review", "similarity")}
    started = time.perf_counter()
    with patch.object(scan, "image_paths", return_value=paths):
        scanned = scan.scan(settings, None)
    scan_seconds = time.perf_counter() - started
    revision = "Falconsai--nsfw_image_detection-revision.txt"
    (out / "cache" / revision).write_bytes((ROOT / "out/library/cache" / revision).read_bytes())
    started = time.perf_counter()
    predictor = models.safety(out)
    load_seconds = time.perf_counter() - started
    # Identical warmup/batch shape in each fresh process.
    predictor.predict([scan.pixels(paths[0])])
    started = time.perf_counter()
    values = infer(scanned, Pass(out, "nsfw_prob", settings.batch_size, predictor))
    gpu_seconds = time.perf_counter() - started
    np.save(out / "values.npy", values, allow_pickle=False)
    result = {"phase": args.phase, "rows": len(scanned), "scan_seconds": scan_seconds,
              "scan_s_per_image": scan_seconds / len(scanned), "gpu_seconds": gpu_seconds,
              "gpu_s_per_image": gpu_seconds / len(scanned), "load_seconds": load_seconds,
              "scores_sha256": protected, "scanned": [r.model_dump() for r in scanned]}
    if args.phase == "after":
        before = out.parent / "before"
        result["exact_scores"] = bool(np.array_equal(values, np.load(before / "values.npy")))
        result["max_score_difference"] = float(np.max(np.abs(values - np.load(before / "values.npy"))))
        result["exact_scan"] = result["scanned"] == json.loads((before / "receipt.json").read_text())["scanned"]
    db.write_json(out / "receipt.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "scanned"}, indent=2))


if __name__ == "__main__":
    main()
