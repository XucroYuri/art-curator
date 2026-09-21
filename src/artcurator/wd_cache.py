"""Two-layer WD cache: raw model-space inference results plus legacy projected entries.

The inference layer is keyed only by crop content, model artifact digests and the preprocessing
profile, and stores the full float32 score vector. The projection layer maps that vector onto the
current output schema at read time, so an output-schema change costs zero inference. Legacy
handshake-bound entries are reused only when their model, tag table, preprocessing profile and
projection contract all match and the match is unambiguous; every other old entry is explicitly
invalidated and counted, never silently mis-read.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np
from numpy.typing import NDArray

from .identity_schema import Digest, Record
from .identity_store import digest, file_digest, save_array, save_model
from .wd_projection import PROJECTION
from .wd_schema import PREPROCESS, Evidence, Handshake

INFERENCE_FORMAT: Final = "wd-inference-v1"


class InferenceIdentity(Record):
    """Semantic inputs that determine model-space scores: weights, tag table, preprocessing."""
    model_sha256: Digest
    tags_sha256: Digest
    preprocess: Digest


class InferenceEntry(Record):
    format: Literal["wd-inference-v1"] = "wd-inference-v1"
    key: Digest
    model_sha256: Digest
    tags_sha256: Digest
    preprocess: Digest
    scores_sha256: Digest


class LegacyCacheEntry(Record):
    """Handshake-bound entry written by the pre-two-layer cache; shape frozen for parsing."""
    key: Digest
    handshake: Handshake
    evidence: Evidence
    payload_sha256: Digest


def model_digest(model_sha256: str, tags_sha256: str) -> str:
    return digest(b"wd-model-v1\0" + model_sha256.encode() + b"\0" + tags_sha256.encode())


def inference_key(content: str, identity: InferenceIdentity) -> str:
    """Content plus model artifact plus preprocessing profile; deliberately schema-free."""
    return digest(b"wd-inference-v1\0" + content.encode() + b"\0"
                  + model_digest(identity.model_sha256, identity.tags_sha256).encode() + b"\0"
                  + identity.preprocess.encode())


def read_inference(cache: Path, key: str, identity: InferenceIdentity) -> NDArray[np.float32] | None:
    """Raw vectors for this key, or None when absent. Corrupt or mismatched entries fail closed."""
    metadata = cache / f"{key}.json"
    if not metadata.is_file():
        return None
    document: Any = json.loads(metadata.read_bytes())
    if not isinstance(document, dict):
        raise ValueError("WD inference cache entry is not an object")
    if document.get("format") != INFERENCE_FORMAT:
        return None  # Legacy-shaped entry at a colliding name; the legacy index owns it.
    entry = InferenceEntry.model_validate(document)
    if (entry.key != key or entry.model_sha256 != identity.model_sha256
            or entry.tags_sha256 != identity.tags_sha256 or entry.preprocess != identity.preprocess):
        raise ValueError("WD inference cache key/identity mismatch")
    payload = cache / f"{key}.npy"
    if not payload.is_file() or file_digest(payload) != entry.scores_sha256:
        raise ValueError("WD inference cache payload digest mismatch")
    values = np.load(payload, allow_pickle=False)
    if values.dtype != np.float32 or values.ndim != 1:
        raise ValueError("WD inference cache payload contract mismatch")
    return values


def save_inference(cache: Path, key: str, identity: InferenceIdentity, values: NDArray) -> None:
    """Publish the payload before its metadata so a crash leaves an orphan, not a lie."""
    payload = cache / f"{key}.npy"
    save_array(payload, values)
    save_model(cache / f"{key}.json", InferenceEntry(key=key, model_sha256=identity.model_sha256,
        tags_sha256=identity.tags_sha256, preprocess=identity.preprocess, scores_sha256=file_digest(payload)))


@dataclass(frozen=True, slots=True)
class _LegacyEntry:
    key: str
    handshake: dict[str, Any]
    evidence: Evidence


@dataclass(slots=True)
class LegacyCache:
    """Old entries indexed by the handshake serialization reconstructed from each file."""
    by_handshake: dict[str, dict[str, _LegacyEntry]]
    total: int
    crops_reused: int = 0
    _reused: set[str] = field(default_factory=set)
    _invalidated: set[str] = field(default_factory=set)

    @property
    def reused(self) -> int:
        return len(self._reused)

    @property
    def invalidated(self) -> int:
        return len(self._invalidated)

    @property
    def orphan(self) -> int:
        return self.total - self.reused - self.invalidated

    def reuse(self, content: str, identity: InferenceIdentity, provider: str) -> Evidence | None:
        """Evidence for this crop, or None with every matched entry explicitly invalidated."""
        matches = [entry for handshake_json, entries in self.by_handshake.items()
                   if (entry := entries.get(digest((content + handshake_json).encode()))) is not None]
        if not matches:
            return None
        compatible = [entry for entry in matches if _compatible(entry.handshake, identity)]
        if not compatible:
            self._invalidated.update(entry.key for entry in matches)
            return None
        same_provider = [entry for entry in compatible if entry.handshake.get("provider") == provider]
        pool = same_provider or compatible
        if len({entry.evidence.model_dump_json() for entry in pool}) != 1:
            self._invalidated.update(entry.key for entry in pool)
            return None
        self._reused.update(entry.key for entry in pool)
        self.crops_reused += 1
        return pool[0].evidence


def _compatible(handshake: dict[str, Any], identity: InferenceIdentity) -> bool:
    return (handshake.get("model_sha256") == identity.model_sha256
            and handshake.get("tags_sha256") == identity.tags_sha256
            and handshake.get("preprocess") == PREPROCESS
            and handshake.get("output_contract") == PROJECTION)


def scan_legacy(cache: Path) -> LegacyCache:
    """Index every old-format entry without trusting a reserialized Pydantic model."""
    by_handshake: dict[str, dict[str, _LegacyEntry]] = {}
    total = 0
    for path in sorted(cache.glob("*.json")):
        document: Any = json.loads(path.read_bytes())
        if not isinstance(document, dict):
            raise ValueError(f"WD cache entry is not an object: {path.name}")
        if document.get("format") == INFERENCE_FORMAT:
            continue
        entry = LegacyCacheEntry.model_validate(document)
        if entry.key != path.stem:
            raise ValueError(f"WD cache key/filename mismatch: {path.name}")
        handshake_json = json.dumps(document["handshake"], separators=(",", ":"), ensure_ascii=False)
        by_handshake.setdefault(handshake_json, {})[entry.key] = _LegacyEntry(
            key=entry.key, handshake=document["handshake"], evidence=entry.evidence)
        total += 1
    return LegacyCache(by_handshake=by_handshake, total=total)
