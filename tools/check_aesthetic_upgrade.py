# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# Run: .venv\Scripts\python.exe tools\check_aesthetic_upgrade.py
"""Compare fresh inference against eight saved pre-upgrade aesthetic scores."""
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from artcurator import db, models
from artcurator.config import ROOT, confine_writes, environment
from artcurator.scan import pixels


def main() -> None:
    out = ROOT / "out/library"
    environment(out)
    confine_writes()
    rows = db.load_rows(out)[:8]
    predictor = models.aesthetic(out)
    values = predictor.predict([pixels(Path(row.abs_path)) for row in rows])
    differences = np.abs(values - np.asarray([row.aes_v25 for row in rows]))
    result = {
        "transformers": importlib.metadata.version("transformers"),
        "revision": predictor.revision,
        "samples": [{"sha16": row.sha16, "cached": row.aes_v25, "fresh": float(value)}
                    for row, value in zip(rows, values, strict=True)],
        "maximum_absolute_difference": float(differences.max()),
        "compatible": bool((differences <= 1e-3).all()),
    }
    db.write_json(out / f"aesthetic-check-{result['transformers']}.json", result)
    print(json.dumps(result, indent=2))
    if not result["compatible"]:
        raise RuntimeError("Aesthetic scores changed beyond 1e-3")


if __name__ == "__main__":
    main()
