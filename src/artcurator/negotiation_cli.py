"""Existing argparse CLI adapter for non-visual G2 operations."""
import argparse
from pathlib import Path

from .negotiation import confirm, dismiss, prepare, retract
from .negotiation_consent import Decision
from .negotiation_metrics import Labels


def handle_negotiation(root: Path, args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    match args.command:
        case "ingest-negotiate":
            labels = Labels.model_validate_json(args.negotiation_labels.read_bytes()) if args.negotiation_labels else None
            print(prepare(root, labels).model_dump_json(indent=2))
        case "ingest-confirm":
            if args.decision is None:
                parser.error("--decision required; defaults are not consent")
            print(confirm(root, Decision.model_validate_json(args.decision.read_bytes())).model_dump_json(indent=2))
        case "ingest-dismiss":
            dismiss(root)
            print('{"status":"waiting","consent":null}')
        case "ingest-retract":
            if not args.actor:
                parser.error("--actor required")
            retract(root, args.actor)
            print('{"status":"retracted","active_consent":null,"mapping_mutations":0}')
        case _:
            parser.error("unknown negotiation command")
