"""Isolated, bounded, restartable HPSv3 pass with native sigma and timing receipts."""
import argparse
import hashlib
import json
import logging
import time
from pathlib import Path

from . import db
from .cache import Pass, infer
from .config import confine_writes, environment, output_path
from .hpsv3_model import load


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-new", type=int, default=0)
    parser.add_argument("--precision", choices=["bf16", "8bit", "4bit", "cpu"], default="8bit")
    args = parser.parse_args()
    if args.max_new < 0:
        parser.error("--max-new must be nonnegative")
    out = output_path(args.out)
    environment(out)
    confine_writes()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(out / "run.log", encoding="utf-8"), logging.StreamHandler()])
    seen_cast_warning = False

    def cast_warning_once(record: logging.LogRecord) -> bool:
        nonlocal seen_cast_warning
        if not record.getMessage().startswith("MatMul8bitLt: inputs will be cast"):
            return True
        first = not seen_cast_warning
        seen_cast_warning = True
        return first

    logging.getLogger("bitsandbytes.autograd._functions").addFilter(cast_warning_once)
    import torch

    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    rows = db.load_rows(out)
    baseline = out / "hpsv3-before.json"
    if not baseline.exists():
        db.write_json(baseline, [row.model_dump() for row in rows])
    predictor = load(args.precision)
    loaded = time.perf_counter() - started
    fingerprint = "|".join((predictor.name, predictor.revision, predictor.preproc, "original"))
    namespace = hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
    directory = out / "cache/predictions" / namespace
    pending = list(dict.fromkeys(row.sha16 for row in rows if not (directory / f"{row.sha16}.npy").exists()))
    chosen = set(pending[:args.max_new] if args.max_new else pending)
    selected = [row for row in rows if row.sha16 in chosen]
    receipt = {"precision": args.precision, "fingerprint": fingerprint,
               "new_contents": len(chosen), "rows": len(selected), "load_seconds": loaded}
    try:
        # Only process newly selected contents. Existing cache is restored below without another model call.
        if selected:
            infer(selected, Pass(out, "hpsv3", 1, predictor, loaded, workers=1, prefetch_batches=0))
        import numpy as np
        complete = 0
        for row in rows:
            path = directory / f"{row.sha16}.npy"
            if path.exists():
                value = np.load(path, allow_pickle=False)
                if value.shape != (2,) or not np.isfinite(value).all() or value[1] < 0:
                    raise ValueError(f"Invalid HPSv3 cached pair: {row.sha16}")
                row.hpsv3_mu, row.hpsv3_sigma = map(float, value)
                complete += 1
            else:
                row.hpsv3_mu = row.hpsv3_sigma = None
        db.save_rows(out, rows)
        db.meta(out, "model_hpsv3", fingerprint)
        db.meta(out, "deviation_hpsv3", "Isolated Transformers 4.45.2; empty image-specific prompt with fixed upstream "
                "instruction; native sigma=exp(raw channel 1). Precision=" + args.precision +
                "; SDPA; 85% physical-VRAM allocator cap prevents WDDM shared-memory paging. No model substitution.")
        receipt["completed_rows"] = complete
        receipt["remaining_rows"] = len(rows) - complete
        logging.info("hpsv3 checkpoint completed=%d remaining=%d", complete, len(rows) - complete)
    finally:
        receipt["wall_seconds"] = time.perf_counter() - started
        receipt["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        receipt["peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        with (out / "hpsv3-invocations.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt) + "\n")
        print(json.dumps(receipt))


if __name__ == "__main__":
    main()
