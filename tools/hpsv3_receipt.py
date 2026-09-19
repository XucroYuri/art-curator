"""Summarize completed HPSv3 costs and paired tier shifts; never write corpus files."""
import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from artcurator import db
from artcurator.config import confine_writes, output_path


class Invocation(BaseModel):
    model_config = ConfigDict(frozen=True)
    wall_seconds: float
    load_seconds: float
    new_contents: int
    peak_allocated_bytes: int
    peak_reserved_bytes: int


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = output_path(args.out)
    confine_writes()
    before = TypeAdapter(list[db.Row]).validate_json((out / "hpsv3-before.json").read_text(encoding="utf-8"))
    after = db.load_rows(out)
    if len(before) != len(after) or any(row.hpsv3_mu is None or row.hpsv3_sigma is None for row in after):
        raise ValueError("Receipt requires complete HPSv3 scoring on an unchanged manifest")
    immutable = ("sha256", "abs_path", "aes_v25", "topiq_iaa", "topiq_nr", "qrealign", "nsfw_prob", "identity_sim")
    for old, new in zip(before, after, strict=True):
        if any(getattr(old, key) != getattr(new, key) for key in immutable):
            raise ValueError("Existing scorer or corpus identity changed")
    invocations = [Invocation.model_validate_json(line) for line in
                   (out / "hpsv3-invocations.jsonl").read_text(encoding="utf-8").splitlines()]
    with db.connection(out) as connection:
        timings = list(connection.execute("SELECT seconds,images,cached FROM timings WHERE pass='hpsv3'"))
    inference = sum(row[0] for row in timings)
    previous = Counter(row.proposed_tier for row in before)
    current = Counter(row.proposed_tier for row in after)
    log = (out / "run.log").read_text(encoding="utf-8")
    progress = [(datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S,%f"), int(done), int(pending))
                for stamp, done, pending in re.findall(
                    r"([\d-]+ [\d:,]+) INFO pass progress name=qrealign completed=(\d+) pending=(\d+)", log)]
    observed_seconds = 0.0
    observed_images = 0
    for first, second in zip(progress, progress[1:]):
        if first[2] == second[2] and second[1] > first[1]:
            observed_seconds += (second[0] - first[0]).total_seconds()
            observed_images += second[1] - first[1]
    command_walls = [float(value) for value in re.findall(r"command complete name=score wall_seconds=([\d.]+)",
                     log)][-len(invocations):]
    result = {
        "rows": len(after), "unique_contents": len({row.sha256 for row in after}),
        "inference_seconds": inference, "seconds_per_row": inference / len(after),
        "seconds_per_unique_content": inference / len({row.sha256 for row in after}),
        "worker_wall_seconds": sum(run.wall_seconds for run in invocations),
        "command_wall_seconds": sum(command_walls), "invocations": len(invocations),
        "load_seconds": sum(run.load_seconds for run in invocations),
        "peak_allocated_bytes": max(run.peak_allocated_bytes for run in invocations),
        "peak_reserved_bytes": max(run.peak_reserved_bytes for run in invocations),
        "before_tiers": dict(previous), "after_tiers": dict(current),
        "tier_delta": {tier: current[tier] - previous[tier] for tier in sorted(previous.keys() | current.keys())},
        "rows_changed_tier": sum(old.proposed_tier != new.proposed_tier for old, new in zip(before, after, strict=True)),
        "transitions": dict(Counter(f"{old.proposed_tier} -> {new.proposed_tier}" for old, new in
                            zip(before, after, strict=True) if old.proposed_tier != new.proposed_tier)),
        "flags": dict(Counter(flag for row in after for flag in row.flags.split("|") if flag)),
        "old_scores_unchanged": True,
        "prior_qrealign_progress_seconds": observed_seconds,
        "prior_qrealign_progress_images": observed_images,
        "prior_qrealign_progress_seconds_per_image": observed_seconds / observed_images if observed_images else None,
    }
    db.write_json(out / "hpsv3-receipt.json", result)
    db.meta(out, "hpsv3_wall_seconds_worker_sum", str(result["worker_wall_seconds"]))
    db.meta(out, "hpsv3_wall_seconds_command_sum", str(result["command_wall_seconds"]))
    db.meta(out, "hpsv3_measurements", json.dumps(result))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
