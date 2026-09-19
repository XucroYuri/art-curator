"""Record execution provenance after a resumed run (no model work)."""
import importlib.metadata
import json
import logging
from datetime import datetime

from . import db
from .config import ROOT, confine_writes, environment, load
from .report import report


def main() -> None:
    settings = load(ROOT / "config.yaml").model_copy(update={"out": ROOT / "out/library"})
    environment(settings.out)
    confine_writes()
    lines = (settings.out / "run.log").read_text(encoding="utf-8").splitlines()
    starts = [line[:23] for line in lines if "command start name=run-all limit=None" in line]
    finishes = [line[:23] for line in lines if "command complete name=report" in line]
    if starts and finishes:
        start = datetime.strptime(starts[-1], "%Y-%m-%d %H:%M:%S,%f")
        end = datetime.strptime(finishes[-1], "%Y-%m-%d %H:%M:%S,%f")
        db.meta(settings.out, "full_wall_seconds_including_resume", str((end - start).total_seconds()))
        db.meta(settings.out, "full_wall_interval_local", f"{start.isoformat()} to {end.isoformat()}")
    versions = {distribution.metadata["Name"]: distribution.version for distribution in importlib.metadata.distributions()}
    db.write_json(settings.out / "environment-versions.json", dict(sorted(versions.items())))
    (settings.out / "requirements-installed.txt").write_text(
        "\n".join(f"{name}=={version}" for name, version in sorted(versions.items())) + "\n", encoding="utf-8")
    report(settings)
    logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(settings.out / "run.log", encoding="utf-8")],
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.info("receipt completed full_start=%s full_end=%s timeout_resume=documented", starts[-1], finishes[-1])
    print(json.dumps({"versions_recorded": len(versions), "full_start": starts[-1], "full_end": finishes[-1]}))


if __name__ == "__main__":
    main()
