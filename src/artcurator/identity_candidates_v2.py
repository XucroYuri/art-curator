"""Parallel model enumeration and saved-embedding visual-memory retrieval."""
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from .candidates_schema_v2 import CandidateDocumentV2, FaceOptions, Option, Suggested
from .character_memory import load_memory, save_memory, sync_labels
from .identity_group_math import ReferenceBank, decide, similarities, without_crop
from .identity_group_schema import Thresholds
from .identity_labels import load_registry
from .identity_store import load_document, load_provenance, load_vectors, save_model
from .model_suggestions import disagreement, propose
from .wd_schema import Attributes, TagDocument

BUCKETS: Final = ("普通人物", "新角色设计", "无法确定")


def merge_options(model: list[Option], memory: list[Option]) -> list[Option]:
    """Model-first enumeration; a duplicate preserves both incompatible score units."""
    rows = {row.name: row for row in model}
    for candidate in memory:
        if candidate.name in rows:
            previous = rows[candidate.name]
            rows[candidate.name] = previous.model_copy(update={"score_model": previous.score,
                                                               "score_memory": candidate.score})
        else:
            rows[candidate.name] = candidate
    evidence = [row for name, row in rows.items() if name not in {*BUCKETS, "其他", "新建角色"}]
    return [*evidence, *[Option(name=name, source="bucket") for name in BUCKETS],
            Option(name="其他", source="bucket"), Option(name="新建角色", source="action")]


def emit(out: Path, gates: Thresholds | None = None) -> CandidateDocumentV2:
    """No reference requirement; model logits never bypass the existing visual gates."""
    document, provenance = load_document(out), load_provenance(out)
    registry = load_registry(out)
    memory = load_memory(out)
    if not (out / "character-memory.json").exists():
        # One-time migration of confirmed assignments only, never model proposals.
        sync_labels(out, [event.label for event in registry.events])
        memory = load_memory(out)
    save_memory(out, memory)
    vectors = load_vectors(out, document)
    index = {face.face_id: i for i, face in enumerate(document.faces)}
    labels: list[str] = []
    crops: list[str] = []
    values: list[NDArray[np.float32]] = []
    for char in memory.characters:
        if char.name in {*BUCKETS, "其他", "新建角色"}:
            continue
        for face_id in sorted(char.face_ids):
            if face_id in index and face_id not in registry.excluded:
                labels.append(char.name)
                crops.append(provenance.crops[face_id])
                values.append(vectors[index[face_id]])
    bank = ReferenceBank(np.asarray(values, dtype=np.float32).reshape(-1, vectors.shape[1]), tuple(labels), tuple(crops))
    reference_bank = None
    if (out / "anchors.json").exists():
        from .identity_anchor import effective_references, load_anchors
        anchors, matrix = load_anchors(out)
        _, reference_bank = effective_references(out, anchors, matrix)
        gates = gates or anchors.calibration.defaults
    gates = gates or Thresholds(min_sim=.9, min_margin=.05)
    wd_path = out / "wd-tagger.json"
    wd = TagDocument.model_validate_json(wd_path.read_bytes()) if wd_path.exists() else None
    if wd and wd.corpus_fingerprint != provenance.corpus_fingerprint:
        raise ValueError("WD evidence corpus mismatch")
    tagged = {face.face_id: face for face in wd.faces} if wd else {}
    aliases = {alias: char.name for char in memory.characters for alias in [char.name, *char.aliases]}
    wd_names = {tag.tag for row in tagged.values() for tag in row.evidence.characters}
    resolved_references = {char.name for char in memory.characters if char.aliases or char.name in wd_names}
    faces: list[FaceOptions] = []
    for face, vector in zip(document.faces, vectors, strict=True):
        evidence = tagged.get(face.face_id)
        if evidence and (evidence.crop_sha256 != provenance.crops[face.face_id] or evidence.image_sha16 != face.image_sha16):
            raise ValueError("WD evidence face binding mismatch")
        model = [Option(name=aliases.get(tag.tag, tag.tag), display=aliases.get(tag.tag, tag.tag.replace("_", " ")),
                        source="model", score=tag.score) for tag in evidence.evidence.characters] if evidence else []
        # Curation may alias multiple model tags to one character; retain its strongest score.
        model = list({row.name: row for row in reversed(model)}.values())
        model.sort(key=lambda row: (-(row.score or 0), row.name))
        available = without_crop(bank, provenance.crops[face.face_id])
        names, _, individuals = similarities(vector, available)
        order = sorted(range(len(names)), key=lambda i: (-individuals[i], names[i]))
        retrieved = [Option(name=names[i], display=names[i], source="memory", score=float(individuals[i]))
                     for i in order[:5] if individuals[i] > .35]
        decision = decide(vector[None], available, gates)[0]
        suggested = None
        if (decision.character and decision.margin is not None and face.face_id not in registry.excluded
                and decision.character in {row.name for row in retrieved}):
            suggested = Suggested(name=decision.character, source="memory", margin_vs_runner_up=decision.margin)
        model_suggestion = propose(model) if face.face_id not in registry.excluded else None
        conflicts = disagreement(model_suggestion, retrieved, "memory")
        if reference_bank is not None:
            ref_names, _, ref_scores = similarities(vector, without_crop(reference_bank, provenance.crops[face.face_id]))
            reference = [Option(name=aliases.get(name, name), source="memory", score=float(score))
                         for name, score in zip(ref_names, ref_scores, strict=True)]
            reference_conflicts = disagreement(model_suggestion, reference, "reference")
            conflicts.extend(conflict.model_copy(update={"reason": "reference-namespace-unresolved"})
                if conflict.evidence_name not in resolved_references else conflict for conflict in reference_conflicts)
        confirmed = registry.references.get(face.face_id)
        if confirmed:
            conflicts.extend(disagreement(model_suggestion,
                [Option(name=aliases.get(confirmed, confirmed), source="memory", score=1)], "confirmed"))
        faces.append(FaceOptions(face_id=face.face_id, image_sha16=face.image_sha16,
            candidates=merge_options(model, retrieved), suggested=suggested, abstained=suggested is None,
            suggested_verified=suggested, suggested_model=model_suggestion,
            model_demoted=bool(conflicts), disagreements=conflicts,
            attributes=evidence.evidence.attributes if evidence else Attributes()))
    result = CandidateDocumentV2(faces=faces)
    save_model(out / "identity-candidates.json", result)
    from .alias_candidates import emit_alias_candidates
    emit_alias_candidates(out)
    return result
