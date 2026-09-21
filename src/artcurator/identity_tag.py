"""Coordinator-owned WD evidence: raw model-space cache plus schema-projecting read path."""
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from .identity_group_schema import Anchor, AnchorDocument
from .identity_schema import Record
from .identity_store import digest, file_digest, load_document, load_provenance, save_model
from .wd_cache import InferenceIdentity, inference_key, read_inference, save_inference, scan_legacy
from .wd_exchange import worker
from .wd_preprocess import preprocess_digest
from .wd_projection import compact, decode_raw, load_tags
from .wd_schema import (
    BUILD_FILES,
    PINS,
    Evidence,
    Handshake,
    Request,
    Response,
    TagDocument,
    TaggedAnchor,
    TaggedFace,
)


class TagOptions(Record):
    model_dir: Path = Path("out/zero-shot-candidates/model")
    python: Path = Path(".venv-wdtagger/Scripts/python.exe")
    batch_size: int = Field(default=8, ge=1, le=16)
    max_new: int = Field(default=0, ge=0)
    provider: str = "CPUExecutionProvider"
    cuda_dll_directory: Path | None = None


@dataclass(frozen=True, slots=True)
class AnchorInput:
    image_sha256: str
    crop_sha256: str
    path: Path
    content: str


def verified_anchor_crops(out: Path, anchors: Sequence[Anchor]) -> list[AnchorInput]:
    """Saved reference crops that can be tagged; missing or corrupt files are omitted."""
    result: list[AnchorInput] = []
    for anchor in anchors:
        path = out / "anchors" / f"{anchor.crop_sha256}.jpg"
        if not path.is_file():
            continue
        content = file_digest(path)
        if content != anchor.crop_sha256:
            continue
        result.append(AnchorInput(anchor.image_sha256, anchor.crop_sha256, path, content))
    return result


def build_digest() -> str:
    """Lineage digest over every worker-side source file; identical for coordinator and worker."""
    return digest(b"".join(Path(__file__).with_name(name).read_bytes() for name in BUILD_FILES))


def tag(out: Path, options: TagOptions | None = None) -> TagDocument:
    """Serve cached model-space evidence when possible; only content/model/preprocess changes re-infer."""
    options = options or TagOptions()
    root = Path(__file__).resolve().parents[2]
    model = (root / options.model_dir).resolve()
    python = (root / options.python).resolve()
    document, provenance = load_document(out), load_provenance(out)
    started = time.perf_counter()
    handshake = Handshake.model_validate({"build": build_digest(),
        "model_sha256": file_digest(model / "model.onnx"), "tags_sha256": file_digest(model / "selected_tags.csv"),
        "packages": PINS, "provider": options.provider})
    identity = InferenceIdentity(model_sha256=handshake.model_sha256, tags_sha256=handshake.tags_sha256,
                                 preprocess=preprocess_digest())
    tags = load_tags(model / "selected_tags.csv")
    cache = out / "cache" / "wd-tagger"
    cache.mkdir(parents=True, exist_ok=True)
    known: dict[str, Evidence] = {}
    paths: dict[str, Path] = {}
    keys: dict[str, str] = {}
    for face in document.faces:
        crop = (out / face.crop_rel).resolve()
        if not crop.is_relative_to(out.resolve()):
            raise ValueError("WD crop escapes output")
        content = file_digest(crop)
        if content != provenance.crops[face.face_id]:
            raise ValueError("saved crop differs from identity provenance")
        keys[content], paths[content] = inference_key(content, identity), crop
    tagged_anchors: list[tuple[AnchorInput, str]] = []
    anchors_path = out / "anchors.json"
    if anchors_path.exists():
        anchors = AnchorDocument.model_validate_json(anchors_path.read_bytes()).anchors
        for anchor in verified_anchor_crops(out, anchors):
            keys[anchor.content], paths[anchor.content] = inference_key(anchor.content, identity), anchor.path
            tagged_anchors.append((anchor, anchor.content))
    cached = 0
    pending: list[str] = []
    for content, key in keys.items():
        values = read_inference(cache, key, identity)
        if values is None:
            pending.append(content)
        else:
            known[content] = compact(values, tags)
            cached += 1
    legacy_scanned = legacy_reused = legacy_invalidated = 0
    if pending:
        legacy = scan_legacy(cache)
        still: list[str] = []
        for content in pending:
            evidence = legacy.reuse(content, identity, options.provider)
            if evidence is None:
                still.append(content)
            else:
                known[content] = evidence
                cached += 1
        legacy_scanned, legacy_reused, legacy_invalidated = legacy.total, legacy.reused, legacy.invalidated
        print(f"WD cache: {cached} crops served ({legacy.crops_reused} legacy), {len(still)} new; "
              f"legacy entries scanned={legacy.total} reused={legacy.reused} "
              f"invalidated={legacy.invalidated} orphan={legacy.orphan}", flush=True)
        pending = still
    if options.max_new:
        pending = pending[:options.max_new]
    batches: list[Response] = []
    run_id = uuid.uuid4().hex
    if pending:
        with (out / "wd-worker.log").open("a", encoding="utf-8") as error_log, worker(python, error_log) as exchange:
            for offset in range(0, len(pending), options.batch_size):
                ids = pending[offset:offset + options.batch_size]
                request = Request(handshake=handshake, run_id=run_id, request_id=uuid.uuid4().hex,
                    deadline=time.time() + 240, model_dir=str(model), input_ids=ids, crops=[str(paths[key]) for key in ids],
                    cuda_dll_directory=str(options.cuda_dll_directory.resolve()) if options.cuda_dll_directory else None)
                response = exchange.request(request)
                if response.raw is None or len(response.raw) != len(ids):
                    raise ValueError("WD worker omitted model-space scores")
                for content, text in zip(ids, response.raw, strict=True):
                    values = decode_raw(text)
                    save_inference(cache, keys[content], identity, values)
                    known[content] = compact(values, tags)
                batches.append(response.model_copy(update={"raw": None}))
                print(f"WD {min(offset + len(ids), len(pending))}/{len(pending)} new crops", flush=True)
    result = TagDocument(handshake=handshake, corpus_fingerprint=provenance.corpus_fingerprint,
        faces=[TaggedFace(face_id=f.face_id, image_sha16=f.image_sha16, crop_sha256=provenance.crops[f.face_id],
            evidence=known[provenance.crops[f.face_id]]) for f in document.faces if provenance.crops[f.face_id] in known],
        anchors=[TaggedAnchor(image_sha256=anchor.image_sha256, crop_sha256=anchor.crop_sha256,
            evidence=known[content]) for anchor, content in tagged_anchors if content in known],
        batches=batches, cached=cached, legacy_scanned=legacy_scanned, legacy_reused=legacy_reused,
        legacy_invalidated=legacy_invalidated, wall_seconds=time.perf_counter() - started)
    save_model(out / "wd-tagger.json", result)
    return result
