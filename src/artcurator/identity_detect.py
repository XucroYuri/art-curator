"""Resumable detection/crops. Corpus reads are hash-checked; only output is written."""
import io
import json
from pathlib import Path

from PIL import Image

from .identity_detector import Detector, load_detector
from .identity_schema import (
    BBox, ClusteringInfo, Face, IdentityDocument, IdentityOptions, ImageFaces, ModelInfo, Provenance, Record,
)
from .identity_store import atomic_bytes, digest, file_digest, fingerprint, manifest, save_model
from .scan import pixels


class DetectionCache(Record):
    source_sha256: str
    semantic_profile: str
    faces: list[Face]
    crops: dict[str, str]


def face_id(image_full_sha256: str, bbox: BBox) -> str:
    canonical = json.dumps(bbox, separators=(",", ":"))
    return "f_" + digest((image_full_sha256 + canonical).encode())[:8]


def crop_bytes(image: Image.Image, bbox: BBox) -> bytes:
    x, y, width, height = bbox
    size = (max(1, round(width * 256 / max(width, height))), max(1, round(height * 256 / max(width, height))))
    with image.crop((x, y, x + width, y + height)) as cropped, cropped.resize(size, Image.Resampling.LANCZOS) as resized:
        clean = Image.frombytes("RGB", resized.size, resized.convert("RGB").tobytes())
        with clean, io.BytesIO() as buffer:
            clean.save(buffer, "JPEG", quality=90, subsampling=0)
            return buffer.getvalue()


def detect(out: Path, options: IdentityOptions, detector: Detector | None = None) -> None:
    rows = manifest(out)
    adapter = detector or load_detector(options)
    profile = digest(json.dumps({"detector": adapter.info.model_dump(), "artifact": adapter.artifact_sha256,
                                 "options": options.model_dump(exclude={"device", "precision", "batch_size",
                                     "anchor_faces_per_character", "anchor_det_score", "anchor_phash_distance",
                                     "anchor_exclude_folders", "anchor_min_sim", "anchor_min_margin"}), "preprocess": "legacy-rgb-v1-stretch640-bilinear",
                                 "crop": "xywh-v1-lanczos256-jpeg90-444"}, sort_keys=True).encode())
    prior = out / "identity-provenance.json"
    if prior.exists():
        previous = Provenance.model_validate_json(prior.read_bytes())
        if previous.semantic_profile != profile or previous.corpus_fingerprint != fingerprint(rows):
            raise ValueError("identity profile/snapshot changed; use a separate output profile")
    cache = out / "cache/identity-detection" / profile
    cache.mkdir(parents=True, exist_ok=True)
    (out / "faces").mkdir(exist_ok=True)
    images: list[ImageFaces] = []
    faces: dict[str, Face] = {}
    crop_hashes: dict[str, str] = {}
    ownership: dict[str, tuple[str, BBox]] = {}
    errors: list[dict[str, str]] = []
    hits = 0
    for row in rows:
        source = Path(row.abs_path)
        try:
            if file_digest(source) != row.sha256:
                raise ValueError("source content changed since snapshot")
            cached = cache / (row.sha256 + ".json")
            record = None
            if cached.exists():
                candidate = DetectionCache.model_validate_json(cached.read_bytes())
                if candidate.source_sha256 != row.sha256 or candidate.semantic_profile != profile:
                    raise ValueError("detection cache identity mismatch")
                if all((out / f.crop_rel).exists() and file_digest(out / f.crop_rel) == candidate.crops[f.face_id]
                       for f in candidate.faces):
                    record = candidate
                    hits += 1
            if record is None:
                found: list[Face] = []
                crops: dict[str, str] = {}
                with pixels(source) as image:
                    for detection in adapter.predict(image):
                        identifier = face_id(row.sha256, detection.bbox)
                        face = Face(face_id=identifier, image_sha16=row.sha16, bbox=detection.bbox,
                                    det_score=detection.score, crop_rel=f"faces/{identifier}.jpg")
                        encoded = crop_bytes(image, detection.bbox)
                        crop_path = out / face.crop_rel
                        if crop_path.exists() and file_digest(crop_path) != digest(encoded):
                            raise ValueError("face crop collision or corrupt existing crop")
                        atomic_bytes(crop_path, encoded)
                        found.append(face)
                        crops[identifier] = digest(encoded)
                if file_digest(source) != row.sha256:
                    raise ValueError("source changed during detection")
                record = DetectionCache(source_sha256=row.sha256, semantic_profile=profile, faces=found, crops=crops)
                save_model(cached, record)
            for face in record.faces:
                owner = (row.sha256, face.bbox)
                if face.face_id in ownership and ownership[face.face_id] != owner:
                    raise ValueError("short face_id collision")
                ownership[face.face_id] = owner
                faces[face.face_id] = face
            crop_hashes.update(record.crops)
            images.append(ImageFaces(sha16=row.sha16, path_rel=row.path_rel, faces=[f.face_id for f in record.faces]))
        except (FileNotFoundError, OSError) as error:
            errors.append({"image_sha16": row.sha16, "reason": type(error).__name__})
            images.append(ImageFaces(sha16=row.sha16, path_rel=row.path_rel, faces=[]))
    provenance = Provenance(corpus_fingerprint=fingerprint(rows), semantic_profile=profile,
                            contents={r.sha16: r.sha256 for r in rows}, crops=crop_hashes)
    document = IdentityDocument(detector=adapter.info, embedder=ModelInfo(name=options.embedder, model="pending", revision="pending"),
                                clustering=ClusteringInfo(algorithm=options.cluster, min_cluster_size=options.min_cluster_size),
                                image_count=len(images), face_count=len(faces), cluster_count=0,
                                images=images, faces=sorted(faces.values(), key=lambda f: f.face_id), clusters=[])
    save_model(out / "identity-provenance.json", provenance)
    save_model(out / "identity-detections.json", document)
    # Detection never destroys existing labels/clusters on a cache-only resume.
    if not (out / "identities.json").exists():
        save_model(out / "identities.json", document)
    atomic_bytes(out / "identity-detection-status.json", json.dumps({"images": len(rows), "cached": hits,
                 "faces": len(faces), "unavailable": errors, "zero_faces": sum(not i.faces for i in images)}).encode())
