"""Pinned settings/reference identity and validated predecessor cache seeding."""
import importlib.metadata
import json
import shutil
import sqlite3
from pathlib import Path

from .config import ROOT, Settings
from .identity_store import digest, file_digest
from .ingest_schema import Artifact, Frozen, IngestError, Job, Options
from .ingest_storage import valid


class Seal(Frozen):
    revision: str
    artifacts: tuple[Artifact, ...]


def profile_digest(settings: Settings, options: Options) -> str:
    references = {}
    if options.profile_from:
        for name in ("manifest.sqlite", "anchors.json", "anchors.npy", "character-memory.json"):
            path = options.profile_from / name
            references[name] = file_digest(path) if path.is_file() else None
    if options.anchors_from_folders:
        from .scan import image_paths
        references["reference_sources"] = [(p.relative_to(settings.characters_root).as_posix(), file_digest(p))
                                           for p in image_paths(settings.characters_root)]
    # Execution/model availability changes invalidate unavailable proposals too.
    from .identity_tag import TagOptions
    tag = TagOptions()
    model = ROOT / tag.model_dir
    weights = {name: file_digest(model / name) if (model / name).is_file() else None
               for name in ("model.onnx", "selected_tags.csv")} if options.analysis else {}
    packages = {name: importlib.metadata.version(name) for name in ("numpy", "Pillow", "pydantic")}
    execution = None
    if options.analysis:
        from .identity_profiles import execution_profile
        from .identity_detector import ANIME_REVISION
        from huggingface_hub import try_to_load_from_cache
        if settings.identity.detector == "anime_face_detection":
            cached_detector = try_to_load_from_cache("deepghs/anime_face_detection",
                f"face_detect_v1.4_{settings.identity.variant}/model.onnx", revision=ANIME_REVISION)
            weights["detector"] = file_digest(Path(cached_detector)) if isinstance(cached_detector, str) else None
        try:
            execution = execution_profile(settings.identity).model_dump()
        except ValueError as error:
            execution = {"unavailable": str(error)}
    sources = {name: file_digest(Path(__file__).with_name(name + ".py")) for name in
               ("scan", "previews", "identity_detect", "identity_embed", "identity_cluster",
                "identity_anchor", "identity_group", "identity_tag", "wd_worker", "wd_schema",
                "identity_candidates_v2", "model_suggestions", "ingest_adapters", "ingest_schema",
                "ingest", "ingest_report", "ingest_catalog", "ingest_inventory", "identity_profiles")}
    value = {"identity": settings.identity.model_dump(), "options": options.model_dump(mode="json",
             exclude={"quota_bytes", "reserve_bytes", "deadline_seconds", "scan_batch_size"}),
             "references": references, "weights": weights, "packages": packages,
             "execution": execution, "source_versions": sources}
    return digest(json.dumps(value, sort_keys=True).encode())


def seed(settings: Settings, prior: Job | None, options: Options) -> None:
    """Copy only sealed, hash-validated cache/crop payloads; never hardlink mutable sidecars."""
    out = settings.out
    if prior and prior.progress.status == "complete":
        root = out.parent.parent
        previous = root / "revisions" / prior.revision
        seal_path = previous / "seal.json"
        if seal_path.exists():
            sealed = Seal.model_validate_json(seal_path.read_bytes())
            if not valid(root, sealed.artifacts):
                raise IngestError("previous snapshot sidecars inconsistent; recovery required")
            for entry in sealed.artifacts:
                source = root / entry.path
                relative = source.relative_to(previous)
                if relative.parts[0] in {"cache", "faces"}:
                    target = out / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    if options.profile_from:
        source = options.profile_from
        manifest = source / "manifest.sqlite"
        if manifest.is_file():
            with sqlite3.connect(manifest.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                value = connection.execute("SELECT value FROM meta WHERE key='model_siglip'").fetchone()
            if value:
                from .db import meta
                meta(out, "model_siglip", value[0])
        for name in ("anchors.json", "anchors.npy", "character-memory.json"):
            if (source / name).is_file():
                shutil.copyfile(source / name, out / name)
