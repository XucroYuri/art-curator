"""Read-only folder reference sampling; directory labels are human knowledge."""
import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import imagehash
from PIL import Image

from .config import Settings
from .identity_detect import crop_bytes
from .identity_detector import Detector
from .identity_group_schema import Anchor, AnchorDocument, GroupingError
from .identity_schema import IdentityOptions
from .identity_store import atomic_bytes, digest, file_digest, manifest
from .scan import pixels

IMAGE_SUFFIXES: Final = frozenset({".png", ".jpg", ".jpeg", ".webp"})


@dataclass(frozen=True, slots=True)
class Samples:
    anchors: tuple[Anchor, ...]
    encoded: tuple[bytes, ...]
    folders: dict[str, dict[str, int]]
    excluded: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RestoredCrops:
    persisted: int
    unavailable: tuple[str, ...]


def accept_sample(score: float, phash: int, accepted: list[int], options: IdentityOptions) -> bool:
    """The four inputs are independent measured evidence, accumulated hashes and policy."""
    return (score >= options.anchor_det_score and len(accepted) < options.anchor_faces_per_character
            and all((phash ^ other).bit_count() > options.anchor_phash_distance for other in accepted))


def excluded_directories(settings: Settings) -> set[Path]:
    root = settings.characters_root.resolve()
    excluded = {settings.input.resolve(), settings.out.resolve()}
    for name in settings.identity.anchor_exclude_folders:
        path = (root / name).resolve()
        if path == root or not path.is_relative_to(root):
            raise GroupingError("anchor exclusions must name directories below characters_root")
        excluded.add(path)
    # Every existing corpus is a query dataset, not a source of folder supervision.
    for path in settings.out.parent.glob("*/manifest.sqlite"):
        excluded.update(Path(row.abs_path).resolve().parent for row in manifest(path.parent))
    return excluded


def collect(settings: Settings, detector: Detector) -> Samples:
    root = settings.characters_root.resolve()
    excluded = excluded_directories(settings)
    anchors, encoded = [], []
    folders = {}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.is_symlink() or any(folder.is_relative_to(p) for p in excluded):
            continue
        counts = dict(candidates=0, examined=0, accepted=0, ambiguous=0, rejected=0, errors=0, excluded=0)
        candidates = {}
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(folder) or any(resolved.is_relative_to(p) for p in excluded):
                counts["excluded"] += 1
                continue
            try:
                candidates.setdefault(file_digest(path), path)
            except OSError:
                counts["errors"] += 1
        counts["candidates"] = len(candidates)
        accepted = []
        for full_hash, path in sorted(candidates.items()):
            if len(accepted) >= settings.identity.anchor_faces_per_character:
                break
            counts["examined"] += 1
            try:
                with pixels(path) as image:
                    found = detector.predict(image)
                    if len(found) != 1:
                        counts["ambiguous"] += 1
                        continue
                    face = found[0]
                    crop = crop_bytes(image, face.bbox)
                with Image.open(io.BytesIO(crop)) as image:
                    phash = int(str(imagehash.phash(image)), 16)
                if not accept_sample(face.score, phash, accepted, settings.identity):
                    counts["rejected"] += 1
                    continue
                if file_digest(path) != full_hash:
                    raise GroupingError("reference source changed during sampling")
                anchors.append(Anchor(character=folder.name, source="folder-derived", source_folder=folder.name,
                                      image_sha256=full_hash, crop_sha256=digest(crop), bbox=face.bbox,
                                      det_score=face.score, phash=f"{phash:016x}"))
                encoded.append(crop)
                accepted.append(phash)
                counts["accepted"] += 1
            except OSError:
                counts["errors"] += 1
        folders[folder.name] = counts
    relative_exclusions = tuple(sorted(p.relative_to(root).as_posix() for p in excluded if p.is_relative_to(root)))
    return Samples(tuple(anchors), tuple(encoded), folders, relative_exclusions)


def persist_crops(out: Path, anchors: Sequence[Anchor], encoded: Sequence[bytes]) -> int:
    """Publish accepted reference crops by content digest before any embedding work."""
    if len(anchors) != len(encoded):
        raise GroupingError("anchor crop count disagrees with accepted anchors")
    for anchor, crop in zip(anchors, encoded, strict=True):
        if digest(crop) != anchor.crop_sha256:
            raise GroupingError("accepted anchor crop does not match its content digest")
    directory = out / "anchors"
    directory.mkdir(parents=True, exist_ok=True)
    for anchor, crop in zip(anchors, encoded, strict=True):
        path = directory / f"{anchor.crop_sha256}.jpg"
        if path.exists():
            if file_digest(path) != anchor.crop_sha256:
                raise GroupingError("persisted anchor crop is corrupt")
            continue
        atomic_bytes(path, crop)
    return len(anchors)


def restore_crops(settings: Settings) -> RestoredCrops:
    """Rebuild content-addressed crops for corpora anchored before persistence existed."""
    out = settings.out
    document = AnchorDocument.model_validate_json((out / "anchors.json").read_bytes())
    wanted = {anchor.image_sha256 for anchor in document.anchors}
    folders = {anchor.source_folder for anchor in document.anchors}
    root = settings.characters_root.resolve()
    excluded = excluded_directories(settings)
    sources: dict[str, Path] = {}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.is_symlink() or folder.name not in folders:
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(folder) or any(resolved.is_relative_to(p) for p in excluded):
                continue
            try:
                full = file_digest(path)
            except OSError:
                continue
            if full in wanted:
                sources.setdefault(full, path)
        if wanted <= sources.keys():
            break
    restored: list[Anchor] = []
    encoded: list[bytes] = []
    unavailable: list[str] = []
    for anchor in document.anchors:
        source = sources.get(anchor.image_sha256)
        crop = None
        if source is not None:
            try:
                if file_digest(source) != anchor.image_sha256:
                    raise GroupingError("reference source changed during crop restore")
                with pixels(source) as image:
                    crop = crop_bytes(image, anchor.bbox)
            except OSError:
                crop = None
        if crop is None:
            unavailable.append(anchor.crop_sha256)
            continue
        if digest(crop) != anchor.crop_sha256:
            raise GroupingError("restored reference crop differs from the saved anchor digest")
        restored.append(anchor)
        encoded.append(crop)
    return RestoredCrops(persisted=persist_crops(out, restored, encoded), unavailable=tuple(unavailable))
