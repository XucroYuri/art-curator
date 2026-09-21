"""Coordinator-owned compact WD evidence, revision/crop/preprocess-bound cache."""
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from .identity_group_schema import Anchor, AnchorDocument
from .identity_schema import Digest, Record
from .identity_store import digest, file_digest, load_document, load_provenance, save_model
from .wd_schema import Evidence, Handshake, PINS, Request, Response, TagDocument, TaggedAnchor, TaggedFace
from .wd_exchange import worker


class CacheEntry(Record):
    key: Digest
    handshake: Handshake
    evidence: Evidence
    payload_sha256: Digest


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


def content_key(content: str, handshake: Handshake) -> str:
    return digest((content + handshake.model_dump_json()).encode())


def cached_evidence(cache: Path, key: str, handshake: Handshake) -> Evidence | None:
    entry = cache / (key + ".json")
    if not entry.exists():
        return None
    hit = CacheEntry.model_validate_json(entry.read_bytes())
    if (hit.key != key or hit.handshake != handshake
            or hit.payload_sha256 != digest(hit.evidence.model_dump_json().encode())):
        raise ValueError("WD cache integrity mismatch")
    return hit.evidence


def tag(out: Path, options: TagOptions | None = None) -> TagDocument:
    """Run bounded foreground subprocess batches; never persist raw class vectors."""
    options = options or TagOptions()
    root = Path(__file__).resolve().parents[2]
    model = (root / options.model_dir).resolve()
    python = (root / options.python).resolve()
    document, provenance = load_document(out), load_provenance(out)
    started = time.perf_counter()
    worker_source = Path(__file__).with_name("wd_worker.py")
    handshake = Handshake.model_validate({"build": digest(worker_source.read_bytes() + worker_source.with_name("wd_schema.py").read_bytes()),
        "model_sha256": file_digest(model / "model.onnx"), "tags_sha256": file_digest(model / "selected_tags.csv"),
        "packages": PINS, "provider": options.provider})
    cache = out / "cache" / "wd-tagger"
    cache.mkdir(parents=True, exist_ok=True)
    known: dict[str, Evidence] = {}
    paths: dict[str, Path] = {}
    keys: dict[str, str] = {}
    cached = 0
    for face in document.faces:
        crop = (out / face.crop_rel).resolve()
        if not crop.is_relative_to(out.resolve()):
            raise ValueError("WD crop escapes output")
        content = file_digest(crop)
        if content != provenance.crops[face.face_id]:
            raise ValueError("saved crop differs from identity provenance")
        keys[content], paths[content] = content_key(content, handshake), crop
        hit = cached_evidence(cache, keys[content], handshake)
        if hit is not None:
            known[content] = hit
            cached += 1
    tagged_anchors: list[tuple[AnchorInput, str]] = []
    anchors_path = out / "anchors.json"
    if anchors_path.exists():
        anchors = AnchorDocument.model_validate_json(anchors_path.read_bytes()).anchors
        for anchor in verified_anchor_crops(out, anchors):
            keys[anchor.content], paths[anchor.content] = content_key(anchor.content, handshake), anchor.path
            hit = cached_evidence(cache, keys[anchor.content], handshake)
            if hit is not None:
                known[anchor.content] = hit
                cached += 1
            tagged_anchors.append((anchor, anchor.content))
    pending = [content for content in paths if content not in known]
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
                for content, evidence in zip(ids, response.evidence, strict=True):
                    save_model(cache / (keys[content] + ".json"), CacheEntry(key=keys[content], handshake=handshake,
                        evidence=evidence, payload_sha256=digest(evidence.model_dump_json().encode())))
                    known[content] = evidence
                batches.append(response)
                print(f"WD {min(offset + len(ids), len(pending))}/{len(pending)} new crops", flush=True)
    result = TagDocument(handshake=handshake, corpus_fingerprint=provenance.corpus_fingerprint,
        faces=[TaggedFace(face_id=f.face_id, image_sha16=f.image_sha16, crop_sha256=provenance.crops[f.face_id],
            evidence=known[provenance.crops[f.face_id]]) for f in document.faces if provenance.crops[f.face_id] in known],
        anchors=[TaggedAnchor(image_sha256=anchor.image_sha256, crop_sha256=anchor.crop_sha256,
            evidence=known[content]) for anchor, content in tagged_anchors if content in known],
        batches=batches, cached=cached, wall_seconds=time.perf_counter() - started)
    save_model(out / "wd-tagger.json", result)
    return result
