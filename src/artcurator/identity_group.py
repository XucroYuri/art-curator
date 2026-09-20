"""Additive known-character grouping over saved, profile-bound face embeddings."""
import time
from collections import Counter
from pathlib import Path

import numpy as np

from .identity_anchor import effective_references, load_anchors
from .identity_group_export import ExportRows, FaceExport, export, report
from .identity_group_math import decide, without_crop
from .identity_group_schema import (Abstained, Anchor, CharacterGroup, ClusterGroup, Decision, GroupDocument,
                                    GroupProvenance, Thresholds)
from .identity_labels import load_registry
from .identity_schema import IdentityOptions, Record
from .identity_store import (digest, file_digest, load_document, load_provenance,
                             load_vectors, save_model)


class EffectiveSources(Record):
    references: list[Anchor]


def group(out: Path, options: IdentityOptions) -> GroupDocument:
    started = time.perf_counter()
    document = load_document(out)
    source = load_provenance(out)
    anchors, matrix = load_anchors(out)
    references, bank = effective_references(out, anchors, matrix)
    registry = load_registry(out)
    vectors = load_vectors(out, document)
    defaults = anchors.calibration.defaults
    gates = Thresholds(min_sim=defaults.min_sim if options.anchor_min_sim is None else options.anchor_min_sim,
                       min_margin=defaults.min_margin if options.anchor_min_margin is None else options.anchor_min_margin)
    decisions = []
    for face, vector in zip(document.faces, vectors, strict=True):
        available = without_crop(bank, source.crops[face.face_id])
        decisions.append(Decision() if face.face_id in registry.excluded else decide(vector[None], available, gates)[0])
    filenames = {image.sha16: Path(image.path_rel).name for image in document.images}
    rows = ExportRows(faces=[FaceExport(face=f, filename=filenames[f.image_sha16], decision=d)
                             for f, d in zip(document.faces, decisions, strict=True)], filenames=filenames)
    characters = []
    for name in sorted({a.character for a in anchors.anchors} | set(bank.labels)):
        matched = [row for row in rows.faces if row.decision.character == name]
        images = sorted({row.face.image_sha16 for row in matched})
        similarities = [row.decision.sim for row in matched if row.decision.sim is not None]
        margins = [row.decision.margin for row in matched if row.decision.margin is not None]
        characters.append(CharacterGroup(character=name, image_count=len(images), face_count=len(matched),
            images=images, mean_sim=float(np.mean(similarities)) if similarities else None,
            min_margin=min(margins) if margins else None))
    abstained = [row for row in rows.faces if row.decision.character is None]
    cluster_groups = []
    for cluster in sorted({row.face.cluster_id for row in abstained}, key=lambda c: -1 if c is None else c):
        matched = [row for row in abstained if row.face.cluster_id == cluster]
        cluster_groups.append(ClusterGroup(cluster_id=cluster, face_count=len(matched),
                                          images=sorted({row.face.image_sha16 for row in matched})))
    known = {sha: {row.decision.character for row in rows.faces
                   if row.face.image_sha16 == sha and row.decision.character is not None} for sha in filenames}
    effective = EffectiveSources(references=references)
    save_model(out / "identity-group-references.json", effective)
    p = GroupProvenance(corpus_fingerprint=source.corpus_fingerprint,
        identities_sha256=file_digest(out / "identities.json"), embedding_sha256=file_digest(out / "identities.npy"),
        anchors_sha256=file_digest(out / "anchors.json"),
        effective_references_sha256=digest(effective.model_dump_json().encode()),
        reference_version=registry.reference_version, execution=anchors.execution, model=anchors.model,
        preprocess=anchors.preprocess, label_knowledge=anchors.label_knowledge, licenses=anchors.licenses,
        source_counts=dict(Counter(a.source for a in references)), images=len(filenames), faces=len(rows.faces),
        zero_face_images=sum(not image.faces for image in document.images),
        unassigned_images=sum(not names for names in known.values()),
        any_abstained_images=len({row.face.image_sha16 for row in abstained}),
        multi_character_images=sum(len(names) > 1 for names in known.values()),
        wall_seconds=time.perf_counter() - started)
    result = GroupDocument(provenance=p, thresholds=gates, characters=characters,
                            abstained=Abstained(face_count=len(abstained), cluster_groups=cluster_groups))
    export(out, result, rows)
    report(out, result, anchors)
    return result
