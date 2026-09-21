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

Operation = Literal["init", "snapshot", "prepare", "publish", "abort", "undo", "export", "restore", "stage", "confirm", "tray"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--album-db", type=Path)
    parser.add_argument("--album-op", choices=TypeAdapter(Operation).json_schema()["enum"])
    parser.add_argument("--library-id")
    parser.add_argument("--album-file", type=Path)
    parser.add_argument("--album-manifest", type=Path)
    parser.add_argument("--album-batch")
    parser.add_argument("--album-authorize")


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
            case "init":
                raise MappingError("initialization-already-dispatched")
            case unreachable:
                assert_never(unreachable)
