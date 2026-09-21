"""Argparse-compatible G1 command surface, kept separate from legacy pipeline routing."""
import argparse
import json
import time
from pathlib import Path

from .config import ROOT, Settings, load, output_path
from .identity_store import save_model
from .ingest import run
from .ingest_process import Launch, execute_process, launch
from .ingest_runtime import control
from .ingest_schema import Heartbeat, Job, Options, transition
from .ingest_storage import admit, lease, validate_paths

COMMANDS = ("ingest", "ingest-run", "ingest-status", "ingest-pause", "ingest-resume",
            "ingest-cancel", "ingest-advance", "ingest-negotiate", "ingest-confirm",
            "ingest-dismiss", "ingest-retract")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--corpus", default="default", help="Local out/ingest/<corpus> identifier")
    parser.add_argument("--inventory-only", action="store_true", help="Explicitly leave all model signals unavailable")
    parser.add_argument("--ingest-profile-from", type=Path, help="Read-only saved SigLIP provenance and anchors")
    parser.add_argument("--ingest-folder-anchors", action="store_true", help="Explicit folder-name reference labels")
    parser.add_argument("--quota-gib", type=float, default=8)
    parser.add_argument("--reserve-gib", type=float, default=1)
    parser.add_argument("--ingest-target", choices=["CONFIRM", "FIRST-PASS", "REVIEW", "ARCHIVE"])
    parser.add_argument("--decision", type=Path, help="Explicit snapshot-bound G2 decision JSON")
    parser.add_argument("--negotiation-labels", type=Path, help="Independent human labels bound to snapshot")
    parser.add_argument("--actor", help="Local human actor ID for consent withdrawal")


def handle(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if Path(args.corpus).name != args.corpus or args.corpus in {".", "..", ""}:
        parser.error("--corpus must be a single local directory name")
    root = output_path(args.out or ROOT / "out" / "ingest" / args.corpus)
    if not root.is_relative_to((ROOT / "out" / "ingest").resolve()):
        parser.error("ingestion artifacts must be under out/ingest/<corpus>")
    match args.command:
        case "ingest-negotiate" | "ingest-confirm" | "ingest-dismiss" | "ingest-retract":
            from .negotiation_cli import handle_negotiation
            handle_negotiation(root, args, parser)
        case "ingest-status":
            job = Job.model_validate_json((root / "job.json").read_bytes())
            state = job.progress
            heartbeat_path = root / "progress.json"
            if heartbeat_path.exists() and state.status in {"running", "pausing"}:
                heartbeat = Heartbeat.model_validate_json(heartbeat_path.read_bytes())
                if heartbeat.job_id == job.job_id:
                    state = heartbeat.progress
            if state.status in {"running", "pausing"} and time.time() - state.heartbeat > 60:
                state = state.model_copy(update={"status": "stalled", "reason": "heartbeat older than 60 seconds"})
            print(state.model_dump_json(indent=2))
        case "ingest-pause" | "ingest-cancel":
            control(root, "pause" if args.command == "ingest-pause" else "cancel")
            document = Launch.model_validate_json((root / "launch.json").read_bytes())
            print(json.dumps({"requested": args.command,
                              "in_flight_deadline_seconds": document.options.deadline_seconds}))
        case "ingest-advance":
            if args.ingest_target is None:
                parser.error("--ingest-target required")
            job = Job.model_validate_json((root / "job.json").read_bytes())
            if args.ingest_target == "CONFIRM":
                from .negotiation import prepare
                print(prepare(root).model_dump_json(indent=2))
            else:
                transition(job.progress.stage, args.ingest_target)
        case "ingest-resume":
            job = Job.model_validate_json((root / "job.json").read_bytes())
            if job.progress.stage in {"CONFIRM", "FIRST-PASS"}:
                from .negotiation import current
                current(root)
                print(job.progress.model_dump_json(indent=2))
                return
            document = Launch.model_validate_json((root / "launch.json").read_bytes())
            validate_paths(document.settings)
            with lease(root):
                control(root, "resume")
            print(json.dumps({"pid": launch(document), "out": str(root)}))
        case "ingest" | "ingest-run":
            from .negotiation_copy import initial_prompt
            if args.input:
                source = args.input.resolve()
                settings = (load(args.config).model_copy(update={"input": source, "out": root})
                            if args.config != ROOT / "config.yaml" else
                            Settings(input=source, references=source, posted=source,
                                     characters_root=source, out=root))
            else:
                settings = load(args.config).model_copy(update={"out": root})
            options = Options(analysis=not args.inventory_only, profile_from=args.ingest_profile_from,
                anchors_from_folders=args.ingest_folder_anchors,
                quota_bytes=int(args.quota_gib * 1024**3), reserve_bytes=int(args.reserve_gib * 1024**3),
                provider=args.wd_provider, cuda_dll_directory=args.wd_cuda_dlls)
            validate_paths(settings)
            admit(root, 1024 * 1024, options)
            document = Launch(settings=settings, options=options)
            root.mkdir(parents=True, exist_ok=True)
            with lease(root):
                save_model(root / "initial-intent.json", initial_prompt())
            if args.command == "ingest":
                with lease(root):
                    pass
                print(json.dumps({"pid": launch(document), "out": str(root),
                                  "intent": initial_prompt().model_dump()}, ensure_ascii=True))
            else:
                import logging
                logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
                root.mkdir(parents=True, exist_ok=True)
                save_model(root / "launch.json", document)
                job = run(settings, options, execute=execute_process)
                print(job.progress.model_dump_json(indent=2))
        case _:
            parser.error("unknown ingestion command")
