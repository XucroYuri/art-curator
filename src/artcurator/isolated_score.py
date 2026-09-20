"""Coordinator-owned isolated scoring, cache selection and unavailable evidence."""
import json
from pathlib import Path

from . import db
from .cache import Pass, infer
from .cache_identity import namespace
from .resources import Deferred
from .worker_adapter import handshake, remote_predictor
from .worker_protocol import ProtocolError


def score_isolated(out: Path, signal: str, max_new: int = 0) -> None:
    rows = db.load_rows(out)
    ids: list[str] = []
    predictor = remote_predictor(out, signal, ids)
    execution = handshake(signal).execution
    directory = out / "cache/predictions" / namespace(predictor, "original", execution)
    missing = list(dict.fromkeys(row.sha256 for row in rows if not (directory / f"{row.sha256}.npy").exists()))
    ids.extend(missing[:max_new] if max_new else missing)
    chosen = set(ids)
    selected = [row for row in rows if row.sha256 in chosen or (directory / f"{row.sha256}.npy").exists()]
    fields = ("hpsv3_mu", "hpsv3_sigma") if signal == "hpsv3" else ("qrealign",)
    for row in rows:
        for field in fields:
            setattr(row, field, None)
    try:
        if selected:
            values = infer(selected, Pass(out, signal, 1, predictor, workers=1, prefetch_batches=0,
                                          execution=execution))
            for row, value in zip(selected, values, strict=True):
                numbers = value.reshape(-1)
                for field, number in zip(fields, numbers, strict=True):
                    setattr(row, field, float(number))
    except (ProtocolError, Deferred) as error:
        db.meta(out, "signal_unavailable_" + signal, json.dumps({"status": "failed", "reason": str(error)}))
    finally:
        db.save_rows(out, rows)
