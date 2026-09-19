"""Run one real RGB image in a fresh isolated process; retain a reproducible VRAM receipt."""
import argparse
import importlib.metadata
import json
import platform
import time

from artcurator.config import ROOT, confine_writes, environment
from artcurator.hpsv3_model import PROCESSOR_REVISION, REVISION, load
from artcurator import db
from artcurator.scan import pixels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("precision", choices=["bf16", "8bit", "4bit", "cpu"])
    args = parser.parse_args()
    out = ROOT / "out/library"
    environment(out)
    confine_writes()
    import torch

    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    receipt = {"precision": args.precision, "gpu": torch.cuda.get_device_name(0),
               "total_bytes": torch.cuda.get_device_properties(0).total_memory,
               "checkpoint_revision": REVISION, "processor_revision": PROCESSOR_REVISION}
    versions_path = ROOT / "environment-versions.json"
    versions = json.loads(versions_path.read_text(encoding="utf-8")) if versions_path.exists() else {}
    versions["hpsv3"] = {"python": platform.python_version(), "packages": {
        dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()},
        "checkpoint_revision": REVISION, "processor_revision": PROCESSOR_REVISION}
    db.write_json(versions_path, versions)
    try:
        predictor = load(args.precision)
        receipt["load_seconds"] = time.perf_counter() - started
        row = db.load_rows(out)[0]
        from pathlib import Path
        with pixels(Path(row.abs_path)) as image:
            inference = time.perf_counter()
            values = predictor.predict([image])
            receipt["inference_seconds"] = time.perf_counter() - inference
        receipt["values"] = values.tolist()
        receipt["status"] = "ok"
    except torch.OutOfMemoryError as error:
        receipt["status"] = "oom"
        receipt["error"] = str(error)
    finally:
        receipt["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        receipt["peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        receipt["wall_seconds"] = time.perf_counter() - started
        db.write_json(out / f"hpsv3-probe-sharded-{args.precision}.json", receipt)
        print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
