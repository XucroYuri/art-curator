"""Backend-only mapping commands, following the existing argparse/JSON convention."""
import argparse
from pathlib import Path
from typing import Literal, assert_never

from pydantic import TypeAdapter

from .album_map import AlbumStore
from .album_map_browser import BrowserEnvelope, StagedImport, confirm_import, stage_import
from .album_map_exchange import Export, Manifest, export_bundle, restore_bundle
from .album_map_protocol import BatchRequest
from .album_map_schema import MappingError
from .album_map_tray import TrayAction, tray_request
from .album_map_discovery import DiscoveryInput, preview_pool, recluster
from .album_map_promotion import DiscoveryDecision, stage_discovery
from .album_map_vectors import SavedVectors, Wall, representative_wall, saved_vectors
from .first_pass import execute as execute_first_pass, preview as preview_first_pass
from .first_pass_schema import Preview as FirstPassPreview, Run as FirstPassRun
from .first_pass_audit import Incident, freeze
from .album_archive import derive as archive_plan, execute as archive_execute, undo as archive_undo
from .album_archive_schema import Approval, ArchivePlan, ArchiveRequest
from .album_archive import status as archive_status

Operation = Literal["init", "snapshot", "prepare", "publish", "abort", "undo", "export", "restore", "stage", "confirm", "tray",
                     "pool", "discover", "recluster", "promote", "vectors", "wall",
                     "first-pass-preview", "first-pass-execute", "first-pass-audit-error",
                     "archive-plan", "archive-preview", "archive-execute", "archive-undo", "archive-status"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--album-db", type=Path)
    parser.add_argument("--album-op", choices=TypeAdapter(Operation).json_schema()["enum"])
    parser.add_argument("--library-id")
    parser.add_argument("--album-file", type=Path)
    parser.add_argument("--album-manifest", type=Path)
    parser.add_argument("--album-batch")
    parser.add_argument("--album-authorize")
    parser.add_argument("--first-pass-root", type=Path)
    parser.add_argument("--archive-token")
    parser.add_argument("--archive-ledger", type=Path)


def handle(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.album_db is None or args.album_op is None:
        parser.error("album-map requires --album-db and --album-op")
    operation = TypeAdapter(Operation).validate_python(args.album_op)
    path = Path(args.album_db)
    if operation == "init":
        if not args.library_id:
            parser.error("init requires --library-id")
        with AlbumStore.initialize(path, args.library_id) as store:
            print(store.recovery.model_dump_json(indent=2))
        return
    payload = Path(args.album_file).read_bytes() if args.album_file is not None else b""
    with AlbumStore.open(path) as store:
        match operation:
            case "archive-plan" | "archive-preview":
                plan = archive_plan(store, ArchiveRequest.model_validate_json(payload))
                print(plan.model_dump_json(indent=2))
            case "archive-execute":
                result = archive_execute(store, ArchivePlan.model_validate_json(payload),
                    Approval(digest=args.album_authorize or "", token=args.archive_token or ""))
                print(result.model_dump_json(indent=2))
            case "archive-undo":
                if args.archive_ledger is None:
                    parser.error("archive-undo requires --archive-ledger; mapping undo is separate")
                print(archive_undo(Path(args.archive_ledger)).model_dump_json(indent=2))
            case "archive-status":
                if args.archive_ledger is None:
                    parser.error("archive-status requires --archive-ledger")
                print(archive_status(store, Path(args.archive_ledger)).model_dump_json(indent=2))
            case "first-pass-audit-error":
                print(freeze(store, Incident.model_validate_json(payload)).model_dump_json(indent=2))
            case "first-pass-preview" | "first-pass-execute":
                if args.first_pass_root is None:
                    parser.error("first pass requires --first-pass-root (G2 job directory)")
                root = Path(args.first_pass_root)
                if operation == "first-pass-preview":
                    result = preview_first_pass(store.snapshot(), FirstPassRun.model_validate_json(payload), root)
                else:
                    result = execute_first_pass(store, FirstPassPreview.model_validate_json(payload),
                                                (root, args.album_authorize or ""))
                print(result.model_dump_json(indent=2))
            case "snapshot":
                print(store.snapshot().model_dump_json(indent=2))
            case "prepare":
                request = BatchRequest.model_validate_json(payload)
                print(store.prepare(request, args.album_authorize or "").model_dump_json(indent=2))
            case "publish" | "abort" | "undo":
                if not args.album_batch:
                    parser.error("batch operation requires --album-batch")
                if operation == "abort":
                    store.abort(args.album_batch)
                    print(store.recovery.model_dump_json(indent=2))
                else:
                    receipt = store.undo(args.album_batch) if operation == "undo" else store.publish(args.album_batch)
                    print(receipt.model_dump_json(indent=2))
            case "export":
                print(export_bundle(store).model_dump_json(indent=2))
            case "restore":
                exported = Export.model_validate_json(payload)
                if args.album_authorize != exported.digest:
                    raise MappingError("explicit-restore-digest-required")
                restore_bundle(store, exported)
                print(store.snapshot().root.model_dump_json(indent=2))
            case "stage":
                if args.album_manifest is None:
                    parser.error("stage requires --album-manifest")
                staged = stage_import(store.snapshot(), BrowserEnvelope.model_validate_json(payload),
                    Manifest.model_validate_json(Path(args.album_manifest).read_bytes()))
                print(staged.model_dump_json(indent=2))
            case "confirm":
                staged = StagedImport.model_validate_json(payload)
                print(confirm_import(store, staged, args.album_authorize or "").model_dump_json(indent=2))
            case "tray":
                print(tray_request(store.snapshot(), TrayAction.model_validate_json(payload)).model_dump_json(indent=2))
            case "pool" | "discover":
                pool = preview_pool(store.snapshot(), DiscoveryInput.model_validate_json(payload))
                result = pool if operation == "pool" else recluster(pool)
                print(result.model_dump_json(indent=2))
            case "recluster" | "promote":
                decision = DiscoveryDecision.model_validate_json(payload)
                if (operation == "promote") != (decision.entity is not None):
                    raise MappingError("promotion-requires-entity-recluster-forbids-entity")
                print(stage_discovery(store.snapshot(), decision).model_dump_json(indent=2))
            case "vectors":
                print(saved_vectors(SavedVectors.model_validate_json(payload)).model_dump_json(indent=2))
            case "wall":
                print(representative_wall(Wall.model_validate_json(payload)).model_dump_json(indent=2))
            case "init":
                raise MappingError("initialization-already-dispatched")
            case unreachable:
                assert_never(unreachable)
