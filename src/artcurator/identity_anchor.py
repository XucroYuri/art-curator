"""Certified folder anchors and replay-validated human reference merges."""
import io
import time
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from .config import Settings
from .identity_anchor_sources import collect
from .identity_detector import load_detector
from .identity_embed import load_embedder
from .identity_group_math import ReferenceBank, calibrate
from .identity_group_schema import Anchor, AnchorDocument, EmbeddingLedger, GroupingError
from .identity_labels import load_registry
from .identity_profiles import CERTIFICATE, Certificate
from .identity_schema import ModelInfo
from .identity_store import (file_digest, load_document, load_provenance, load_vectors,
                             normalized, save_array, save_model)


def create_anchors(settings: Settings) -> None:
    started = time.perf_counter()
    options = settings.identity
    predictor = load_embedder(settings.out, options)
    certificate = Certificate.model_validate_json(CERTIFICATE.read_bytes())
    if not certificate.numerical_pass or (predictor.execution, predictor.name, predictor.revision, predictor.preproc) != (
        certificate.execution, certificate.model, certificate.revision, certificate.preprocess
    ):
        raise GroupingError("anchor construction requires the exact certified execution/model/preprocess")
    detector = load_detector(options)
    samples = collect(settings, detector)
    values = []
    for offset in range(0, len(samples.encoded), predictor.execution.batch_size):
        with ExitStack() as stack:
            images = [stack.enter_context(Image.open(io.BytesIO(data)))
                      for data in samples.encoded[offset:offset + predictor.execution.batch_size]]
            values.extend(normalized(predictor.predict(images)))
    if not values:
        raise GroupingError("no eligible folder anchors")
    matrix = normalized(np.stack(values))
    bank = ReferenceBank(matrix, tuple(a.character for a in samples.anchors), tuple(a.crop_sha256 for a in samples.anchors))
    calibration = calibrate(bank)
    save_array(settings.out / "anchors.npy", matrix)
    document = AnchorDocument(model=ModelInfo(name=options.embedder, model=predictor.name, revision=predictor.revision),
        preprocess=predictor.preproc, execution=predictor.execution, detector=detector.info,
        detector_sha256=detector.artifact_sha256,
        detector_options={"threshold": options.det_threshold, "nms": options.nms_threshold,
                          "min_face_px": options.min_face_px, "anchor_det_score": options.anchor_det_score,
                          "phash_distance": options.anchor_phash_distance, "cap": options.anchor_faces_per_character},
        licenses={"source_code": "AGPL-3.0-only", "detector": "MIT (pinned model card)",
                  "embedder": "Apache-2.0 (pinned model card)",
                  "source_images": "User supplied; rights unknown, no redistribution clearance",
                  "labels": "User-organized folder names, human-supplied label knowledge"},
        folders=samples.folders, excluded_folders=list(samples.excluded), anchors=list(samples.anchors),
        matrix_sha256=file_digest(settings.out / "anchors.npy"), calibration=calibration,
        wall_seconds=time.perf_counter() - started)
    save_model(settings.out / "anchors.json", document)


def load_anchors(out: Path) -> tuple[AnchorDocument, NDArray[np.float32]]:
    document = AnchorDocument.model_validate_json((out / "anchors.json").read_bytes())
    if file_digest(out / "anchors.npy") != document.matrix_sha256:
        raise GroupingError("anchor matrix digest mismatch")
    matrix = normalized(np.load(out / "anchors.npy", allow_pickle=False))
    if len(matrix) != len(document.anchors):
        raise GroupingError("anchor row count mismatch")
    return document, matrix


def effective_references(out: Path, anchors: AnchorDocument, matrix: NDArray) -> tuple[list[Anchor], ReferenceBank]:
    """Rebuild from folder rows plus current confirmed events, never stale merged rows."""
    document = load_document(out)
    provenance = load_provenance(out)
    ledger = EmbeddingLedger.model_validate_json((out / "identity-embedding.json").read_bytes())
    if (ledger.model, ledger.execution, ledger.preprocess) != (anchors.model, anchors.execution, anchors.preprocess):
        raise GroupingError("query and anchor embedding profiles differ")
    registry = load_registry(out)
    vectors = load_vectors(out, document)
    references = list(anchors.anchors)
    values = list(matrix)
    events = {event.label.face_id: event for event in registry.events}
    for face, vector in zip(document.faces, vectors, strict=True):
        if face.face_id not in registry.references:
            continue
        event = events[face.face_id]
        references.append(Anchor(character=registry.references[face.face_id], source="human-confirmed",
            source_folder="", image_sha256=provenance.contents[face.image_sha16],
            crop_sha256=provenance.crops[face.face_id], bbox=face.bbox, det_score=face.det_score,
            phash="", event_id=event.event_id))
        values.append(vector)
    labels_by_crop = defaultdict(set)
    for reference in references:
        labels_by_crop[reference.crop_sha256].add(reference.character)
    unique = {}
    for index, reference in enumerate(references):
        if len(labels_by_crop[reference.crop_sha256]) == 1:
            # Confirmed provenance takes precedence over identical folder-derived rows.
            unique[reference.crop_sha256] = index
    indices = sorted(unique.values())
    selected = [references[i] for i in indices]
    selected_values = np.stack([values[i] for i in indices]) if indices else np.empty((0, matrix.shape[1]))
    return selected, ReferenceBank(normalized(selected_values), tuple(a.character for a in selected),
                                    tuple(a.crop_sha256 for a in selected))
