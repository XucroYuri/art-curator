# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pydantic>=2", "Pillow", "ImageHash"]
# ///
# How to run (project installed in the existing environment):
# uv run --no-project --python .venv/Scripts/python.exe python tools/backfill_anchor_crops.py config.yaml out/tifa-pilot out/tifa-review out/tifa-similarity
"""Persist verified reference crops for corpora anchored before crops were saved."""
from __future__ import annotations

import sys
from pathlib import Path

from artcurator.config import load, output_path
from artcurator.identity_anchor_sources import restore_crops


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("Provide the config path and at least one output directory")
    settings = load(Path(sys.argv[1]))
    for argument in sys.argv[2:]:
        out = output_path(Path(argument))
        restored = restore_crops(settings.model_copy(update={"out": out}))
        print(f"{out}: persisted={restored.persisted} unavailable={len(restored.unavailable)}", flush=True)
        for crop in restored.unavailable:
            print(f"  unavailable crop {crop}", flush=True)


if __name__ == "__main__":
    main()
