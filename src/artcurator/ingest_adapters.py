"""Thin stage calls only: algorithms and model protocols remain in existing modules."""
import os
import sqlite3
from pathlib import Path
from typing import Literal, assert_never

from pydantic import BaseModel

from .config import Settings
from .db import Row
from .identity_store import file_digest, save_model
from .ingest_schema import Frozen, Options

Action = Literal["scan", "detect", "embed", "cluster", "anchors", "group", "tag", "candidates"]


class Request(Frozen):
    settings: Settings
    options: Options
    action: Action
    paths: tuple[Path, ...] = ()


class Result(Frozen):
    outcome: Literal["completed", "unavailable", "failed"] = "completed"
    reason: str = ""
    paths: tuple[Path, ...] = ()
    items: int = 0
    cached: int = 0
    unit: str = "unique images"


class Rows(Frozen):
    rows: tuple[Row, ...]
    contents: tuple[str, ...] = ()


class StageMetrics(BaseModel):
    """Read only the metered subset of existing, independently versioned stage ledgers."""
    cached: int = 0
    computed: int = 0
    images: int = 0


class EmbeddingLedger(BaseModel):
    metrics: StageMetrics


def unavailable(reason: str) -> Result:
    return Result(outcome="unavailable", reason=reason)


def execute(request: Request) -> Result:
    """Run a single existing stage. The process boundary owns unexpected exceptions."""
    settings, options, action = request.settings, request.options, request.action
    out = settings.out
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    if action != "scan" and not options.analysis:
        return unavailable("analysis explicitly not requested (inventory-only); manual review required")
    if options.analysis:
        # The library may already be imported in an embedding host; environment alone is insufficient.
        from huggingface_hub import constants
        constants.HF_HUB_OFFLINE = True
    out.mkdir(parents=True, exist_ok=True)
    try:
        match action:
            case "scan":
                from .db import save_rows
                from .previews import previews
                from .scan import scan
                try:
                    rows = scan(settings, None, paths=list(request.paths))
                except ValueError as error:
                    if str(error) not in {"Empty corpus", "Empty corpus after thumbnail rejection"}:
                        raise
                    rows = []
                    save_rows(out, rows)
                if rows:
                    previews(settings)
                save_model(out / "rows.json", Rows(rows=tuple(rows),
                    contents=tuple(file_digest(p) for p in request.paths)))
                files = [out / "rows.json", out / "scan-rejected.json"]
                files.extend(p for directory in (out / "thumbs", out / "previews")
                             for p in directory.glob("*.jpg"))
                return Result(paths=tuple(files), items=len(request.paths))
            case "detect":
                from .identity_detect import detect
                detect(out, settings.identity)
                metrics = StageMetrics.model_validate_json((out / "identity-detection-status.json").read_bytes())
                return Result(paths=(out / "identity-detections.json", out / "identity-provenance.json",
                                     out / "identity-detection-status.json", *tuple((out / "faces").glob("*.jpg"))),
                              items=metrics.images, cached=metrics.cached)
            case "embed":
                from .identity_embed import embed
                from .identity_profiles import execution_profile
                if not (out / "identity-detections.json").exists():
                    return unavailable("detection unavailable")
                try:
                    execution_profile(settings.identity)
                except ValueError as error:
                    return unavailable(f"requested embedding execution unavailable: {error}")
                with sqlite3.connect(out / "manifest.sqlite") as connection:
                    pinned = connection.execute("SELECT value FROM meta WHERE key='model_siglip'").fetchone()
                if settings.identity.embedder == "siglip" and pinned is None:
                    return unavailable("incumbent SigLIP provenance unavailable; supply --ingest-profile-from")
                embed(out, settings.identity)
                metrics = EmbeddingLedger.model_validate_json((out / "identity-embedding.json").read_bytes()).metrics
                return Result(paths=(out / "identities.npy", out / "identity-embedding.json"), unit="faces",
                              items=metrics.computed + metrics.cached, cached=metrics.cached)
            case "cluster":
                from .identity_cluster import cluster
                if not (out / "identity-embedding.json").exists():
                    return unavailable("embedding unavailable")
                cluster(out, settings.identity)
                return Result(paths=tuple(p for p in (out / "identities.json", out / "characters.json")
                                          if p.exists()), unit="faces")
            case "anchors":
                from .identity_anchor import create_anchors, load_anchors
                if (out / "anchors.json").exists():
                    load_anchors(out)
                elif options.anchors_from_folders and (out / "identity-embedding.json").exists():
                    create_anchors(settings)
                else:
                    return unavailable("compatible saved references unavailable; folder labels require explicit opt-in")
                return Result(paths=(out / "anchors.json", out / "anchors.npy"), unit="faces")
            case "group":
                from .identity_group import group
                if not all((out / p).exists() for p in ("anchors.json", "identity-embedding.json")):
                    return unavailable("reference/embedding evidence unavailable")
                group(out, settings.identity)
                return Result(paths=tuple(out / p for p in ("character-groups.json",
                    "character-groups-by-character.csv", "character-groups-by-image.csv")), unit="faces")
            case "tag":
                from .identity_tag import TagOptions, tag
                if not (out / "identity-detections.json").exists():
                    return unavailable("detection unavailable")
                tagged = tag(out, TagOptions(provider=options.provider, cuda_dll_directory=options.cuda_dll_directory))
                return Result(paths=(out / "wd-tagger.json",), items=len(tagged.faces),
                              cached=tagged.cached, unit="faces")
            case "candidates":
                from .identity_candidates_v2 import emit
                if not (out / "identity-provenance.json").exists():
                    return unavailable("detection unavailable; no fabricated non-character classification")
                emit(out)
                return Result(paths=(out / "identity-candidates.json",), unit="faces")
            case unreachable:
                assert_never(unreachable)
    except (FileNotFoundError, ImportError) as error:
        if action == "scan":
            raise
        if isinstance(error, FileNotFoundError) and error.filename:
            from .ingest_storage import long_path
            if long_path(Path(error.filename)).is_relative_to(long_path(out)):
                raise  # Derived-storage failures are not missing-model evidence.
        return unavailable(f"{type(error).__name__}: {error}; no download/substitution attempted")


def read_rows(path: Path) -> list[Row]:
    return list(Rows.model_validate_json(path.read_bytes()).rows)
