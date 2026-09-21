"""Read ONLY artifacts enumerated by G1's seal; sidecar presence is not authority."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict

from .candidates_schema_v2 import CandidateDocumentV2
from .identity_schema import IdentityDocument, Provenance
from .identity_store import file_digest
from .ingest_profile import Seal
from .ingest_schema import IngestError, Inventory, Job, Receipt
from .ingest_storage import valid
from .negotiation_metrics import ImageEvidence


class G1Report(BaseModel):
    """Typed projection of the incumbent G1 document; untouched extras remain in G1."""
    model_config = ConfigDict(frozen=True)
    revision: str
    profile_digest: str
    occurrences: int
    unique_images: int
    decode_failed: tuple[str, ...]
    detected_faces: int | None
    unavailable_signals: tuple[str, ...]
    costs: tuple[Receipt, ...]


class VectorLedger(BaseModel):
    model_config = ConfigDict(frozen=True)
    faces: tuple[str, ...]
    sha256: str
    semantic_profile: str


@dataclass(frozen=True, slots=True)
class Evidence:
    job: Job
    inventory: Inventory
    g1: G1Report
    seal_digest: str
    artifact_names: frozenset[str]
    identities: IdentityDocument | None
    candidates: CandidateDocumentV2 | None
    images: tuple[ImageEvidence, ...]
    vectors: dict[str, tuple[float, ...]]
    full_hashes: dict[str, str]
    vector_profile: str | None


def read_evidence(root: Path) -> Evidence:
    """Validate the full seal, then bind each optional input to its sealed name."""
    job = Job.model_validate_json((root / "job.json").read_bytes())
    out = root / "revisions" / job.revision
    seal_path = out / "seal.json"
    seal = Seal.model_validate_json(seal_path.read_bytes())
    if seal.revision != job.revision or not valid(root, seal.artifacts):
        raise IngestError("sealed PROPOSE artifacts inconsistent")
    names = frozenset(a.path for a in seal.artifacts)

    def present(name: str) -> bool:
        return (out / name).relative_to(root).as_posix() in names

    if not all(present(name) for name in ("inventory.json", "analysis-report.json", "barrier-PROPOSE.json")):
        raise IngestError("sealed PROPOSE barrier/report/inventory missing")
    inventory = Inventory.model_validate_json((out / "inventory.json").read_bytes())
    g1 = G1Report.model_validate_json((out / "analysis-report.json").read_bytes())
    if inventory.revision != job.revision or g1.revision != job.revision or g1.profile_digest != job.profile_digest:
        raise IngestError("snapshot/profile digest mismatch")
    document_name = "identities.json" if present("identities.json") else "identity-detections.json"
    identities = IdentityDocument.model_validate_json((out / document_name).read_bytes()) if present(document_name) else None
    candidates = (CandidateDocumentV2.model_validate_json((out / "identity-candidates.json").read_bytes())
                  if present("identity-candidates.json") else None)
    full_hashes: dict[str, str] = {}
    for occurrence in inventory.occurrences:
        if occurrence.sha256:
            short = occurrence.sha256[:16]
            if short in full_hashes and full_hashes[short] != occurrence.sha256:
                raise IngestError("ambiguous legacy short hash")
            full_hashes[short] = occurrence.sha256
    vectors: dict[str, tuple[float, ...]] = {}
    profile = None
    if identities and all(present(name) for name in ("identities.npy", "identity-embedding.json", "identity-provenance.json")):
        ledger = VectorLedger.model_validate_json((out / "identity-embedding.json").read_bytes())
        provenance = Provenance.model_validate_json((out / "identity-provenance.json").read_bytes())
        if (ledger.faces != tuple(f.face_id for f in identities.faces)
                or ledger.sha256 != file_digest(out / "identities.npy")
                or ledger.semantic_profile != provenance.semantic_profile
                or any(full_hashes.get(k) != v for k, v in provenance.contents.items())):
            raise IngestError("sealed vector alignment/profile mismatch")
        matrix = np.load(out / "identities.npy", allow_pickle=False)
        if matrix.ndim != 2 or matrix.shape[0] != len(ledger.faces) or matrix.dtype != np.float16:
            raise IngestError("sealed vector matrix shape/dtype mismatch")
        vectors = {key: tuple(float(v) for v in row) for key, row in zip(ledger.faces, matrix, strict=True)}
        profile = ledger.semantic_profile
    by_image = {image.sha16: image for image in identities.images} if identities else {}
    faces = {face.face_id: face for face in identities.faces} if identities else {}
    options = {face.face_id: face for face in candidates.faces} if candidates else {}
    if candidates and any(f.face_id not in faces or faces[f.face_id].image_sha16 != f.image_sha16 for f in candidates.faces):
        raise IngestError("candidate content/face link mismatch")
    images = []
    for sha in sorted({r.sha256 for r in inventory.occurrences if r.sha256 and r.status != "unavailable"}):
        image = by_image.get(sha[:16])
        # One fixed crop per distinct image, never pooled with whole-image vectors.
        selected = min(image.faces) if image and image.faces else None
        vector = vectors.get(selected) if selected else None
        covered = image is not None and candidates is not None and all(f in options for f in image.faces)
        names_for_image = tuple(sorted({c.name for f in image.faces for c in options[f].candidates
            if c.source in {"model", "memory"}})) if covered and image else None
        images.append(ImageEvidence(image_id=sha, vector=vector, profile=profile,
            representation="lowest-face-id-crop" if vector is not None else "unavailable",
            face_clusters=tuple(faces[f].cluster_id for f in image.faces) if image else None,
            candidates=names_for_image,
            conflict=any(options[f].model_demoted for f in image.faces) if covered and image else None))
    return Evidence(job, inventory, g1, file_digest(seal_path), names, identities, candidates,
                    tuple(images), vectors, full_hashes, profile)
