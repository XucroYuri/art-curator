"""Argparse command boundary and local-only pipeline orchestration."""
import argparse
import logging
import sys
import time
from pathlib import Path

from . import db
from .config import ROOT, confine_writes, environment, load, output_path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["scan", "score", "cluster", "report", "run-all", "previews",
                        "identity", "identity-detect", "identity-embed", "identity-cluster", "identity-report",
                         "identity-apply", "identity-benchmark", "identity-anchor", "identity-group",
                         "identity-tag", "identity-candidates", "character-memory"])
    parser.add_argument("--memory-op", choices=["rename", "merge", "delete", "import", "export", "list"])
    parser.add_argument("--name", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--memory-file", type=Path)
    parser.add_argument("--wd-provider", choices=["CPUExecutionProvider", "CUDAExecutionProvider"], default="CPUExecutionProvider")
    parser.add_argument("--wd-cuda-dlls", type=Path)
    parser.add_argument("--from-folders", action="store_true", help="Use character folder names as human reference labels")
    parser.add_argument("--labels", type=Path, help="Content-bound review-studio character labels")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--pass", dest="only", choices=["siglip", "aes_v25", "topiq_iaa", "topiq_nr", "qrealign", "hpsv3", "nsfw_prob"])
    parser.add_argument("--max-new", type=int, default=0, help="HPSv3 new-content budget; 0 means unlimited")
    args = parser.parse_args()
    if args.command == "identity-anchor" and not args.from_folders:
        parser.error("identity-anchor requires --from-folders")
    if args.from_folders and args.command != "identity-anchor":
        parser.error("--from-folders is only valid for identity-anchor")
    if args.max_new < 0 or (args.max_new and (args.command != "score" or args.only != "hpsv3")):
        parser.error("--max-new must be nonnegative and is only valid for score --pass hpsv3")
    settings = load(args.config)
    updates = {"out": output_path(args.out or settings.out)}
    if args.input:
        updates["input"] = args.input.absolute()
    settings = settings.model_copy(update=updates)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    settings.out.mkdir(parents=True, exist_ok=True)
    environment(settings.out)
    confine_writes()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(settings.out / "run.log", encoding="utf-8"), logging.StreamHandler()])
    started = time.perf_counter()
    logging.info("command start name=%s limit=%s out=%s", args.command, args.limit, settings.out)
    try:
        from .cluster import cluster
        from .report import report
        from .scan import scan
        from .score import score
        from .previews import previews
        match args.command:
            case "identity-tag":
                from .identity_tag import tag, TagOptions
                from .identity_store import stage
                with stage(settings.out, "identity-tag"):
                    tag(settings.out, TagOptions(provider=args.wd_provider, cuda_dll_directory=args.wd_cuda_dlls))
            case "identity-candidates":
                from .identity_candidates_v2 import emit
                from .identity_store import stage
                with stage(settings.out, "identity-candidates"):
                    emit(settings.out)
            case "character-memory":
                from .memory_curation import curate, export_memory, import_memory
                from .character_memory import load_memory
                match args.memory_op:
                    case "rename" | "merge" | "delete":
                        curate(settings.out, args.memory_op, args.name, args.target)
                    case "import" | "export":
                        if args.memory_file is None:
                            parser.error("memory import/export requires --memory-file")
                        operation = import_memory if args.memory_op == "import" else export_memory
                        operation(settings.out, args.memory_file)
                    case "list":
                        print(load_memory(settings.out).model_dump_json(indent=2))
                    case _:
                        parser.error("character-memory requires --memory-op")
            case "identity" | "identity-detect" | "identity-embed" | "identity-cluster" | "identity-report" | "identity-apply" | "identity-benchmark" | "identity-anchor" | "identity-group":
                from .identity import run
                run(settings, args.command, args.labels)
            case "previews":
                previews(settings)
            case "scan":
                scan(settings, args.limit)
            case "score":
                score(settings, args.only, args.max_new)
            case "cluster":
                cluster(settings)
            case "report":
                report(settings)
            case "run-all":
                scan(settings, args.limit)
                score(settings)
                cluster(settings)
                label = "smoke" if args.limit else "full"
                db.meta(settings.out, label + "_wall_seconds", str(time.perf_counter() - started))
                report(settings)
        logging.info("command complete name=%s wall_seconds=%.3f", args.command, time.perf_counter() - started)
    except Exception:
        # Broad catch at CLI boundary only: full traceback is logged and surfaced.
        logging.exception("command failed name=%s", args.command)
        raise


if __name__ == "__main__":
    main()
