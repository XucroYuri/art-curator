"""Observable image co-occurrence, with direct and weak retrieved cohorts separated."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .alias_schema import AliasBank, AliasCandidate, AliasDocument, AliasError, Support
from .character_memory import load_memory
from .identity_anchor import effective_references, load_anchors
from .identity_group_math import ReferenceBank, similarities, without_crop
from .identity_group_schema import Anchor, AnchorDocument
from .identity_labels import load_registry
from .identity_store import file_digest, load_document, load_provenance, load_vectors, save_model
from .wd_schema import Evidence, TagDocument


@dataclass(frozen=True, slots=True)
class Observation:
    image: str
    tag: str
    score: float
    top1: bool


def observations_for(image: str, evidence: Evidence) -> list[Observation]:
    """One row per character tag; multi-crop images stay one support unit downstream."""
    top = max((tag.score for tag in evidence.characters), default=0)
    return [Observation(image, tag.tag, tag.score, tag.score == top) for tag in evidence.characters]


def summarize(rows: list[Observation]) -> Support:
    """Count each full image digest once; a multi-face image is not independent support."""
    scores: dict[str, float] = {}
    for row in rows:
        scores[row.image] = max(scores.get(row.image, 0), row.score)
    if not scores:
        return Support()
    minimum, p25, median, p75, maximum = np.quantile(list(scores.values()), [0, .25, .5, .75, 1])
    return Support(images=len(scores), top1_images=len({r.image for r in rows if r.top1}),
        minimum=float(minimum), p25=float(p25), median=float(median), p75=float(p75), maximum=float(maximum))


def generate(out: Path) -> AliasDocument:
    """Read saved evidence only; generate proposals without applying or persisting memory."""
    document, provenance = load_document(out), load_provenance(out)
    registry, memory = load_registry(out), load_memory(out)
    vectors = load_vectors(out, document)
    references: list[Anchor] = []
    bank = ReferenceBank(np.empty((0, vectors.shape[1]), dtype=np.float32), (), ())
    anchor_document: AnchorDocument | None = None
    if (out / "anchors.json").exists():
        anchor_document, matrix = load_anchors(out)
        references, bank = effective_references(out, anchor_document, matrix)
    else:
        # Session names remain explicit human events; query paths never supply labels.
        selected = [i for i, face in enumerate(document.faces) if face.face_id in registry.references]
        references = [Anchor(character=registry.references[document.faces[i].face_id], source="human-confirmed",
            source_folder="", image_sha256=provenance.contents[document.faces[i].image_sha16],
            crop_sha256=provenance.crops[document.faces[i].face_id], bbox=document.faces[i].bbox,
            det_score=document.faces[i].det_score, phash="") for i in selected]
        bank = ReferenceBank(vectors[selected], tuple(r.character for r in references),
                             tuple(r.crop_sha256 for r in references))
    wd_path = out / "wd-tagger.json"
    wd = TagDocument.model_validate_json(wd_path.read_bytes()) if wd_path.exists() else None
    if wd and wd.corpus_fingerprint != provenance.corpus_fingerprint:
        raise AliasError("WD evidence corpus mismatch")
    tagged = {face.face_id: face for face in wd.faces} if wd else {}
    faces = {face.face_id: face for face in document.faces}
    for face in tagged.values():
        if (face.face_id not in faces or face.image_sha16 != faces[face.face_id].image_sha16
                or provenance.crops.get(face.face_id) != face.crop_sha256):
            raise AliasError("WD evidence face binding mismatch")
    observations: list[Observation] = []
    cohorts: dict[str, set[str]] = {name: set() for name in bank.labels}
    cohort_rows: dict[str, list[Observation]] = {name: [] for name in bank.labels}
    for face, vector in zip(document.faces, vectors, strict=True):
        if face.face_id in registry.excluded:
            continue
        image = provenance.contents[face.image_sha16]
        rows = observations_for(image, tagged[face.face_id].evidence) if face.face_id in tagged else []
        observations.extend(rows)
        names, _, scores = similarities(vector, without_crop(bank, provenance.crops[face.face_id]))
        strongest = max(scores, default=0)
        leaders = [name for name, score in zip(names, scores, strict=True) if score == strongest]
        if strongest > .35 and len(leaders) == 1:
            cohorts[leaders[0]].add(image)
            cohort_rows[leaders[0]].extend(rows)
    if wd and anchor_document is not None and wd.anchors:
        # Reference crops join by full source-image digest; crop similarity alone is not evidence.
        bound = {(anchor.image_sha256, anchor.crop_sha256) for anchor in anchor_document.anchors}
        for anchor in wd.anchors:
            if (anchor.image_sha256, anchor.crop_sha256) not in bound:
                raise AliasError("WD anchor evidence is not bound to the saved reference anchors")
            observations.extend(observations_for(anchor.image_sha256, anchor.evidence))
    banks: list[AliasBank] = []
    for name in sorted(set(bank.labels)):
        images = {r.image_sha256 for r in references if r.character == name}
        direct = [row for row in observations if row.image in images]
        indirect = cohort_rows[name]
        tagged_direct = len({r.image for r in direct})
        owner = next((char for char in memory.characters if name in [char.name, *char.aliases]), None)
        decisions = {r.wd_tag: r.decision for r in owner.alias_decisions} if owner else {}
        candidates: list[AliasCandidate] = []
        for tag in sorted({row.tag for row in [*direct, *indirect]}):
            support = summarize([row for row in direct if row.tag == tag])
            cohort = summarize([row for row in indirect if row.tag == tag])
            strong = support.images >= 3 and support.images / max(tagged_direct, 1) >= .8 and (support.median or 0) >= .85
            candidates.append(AliasCandidate(wd_tag=tag, rank=1, direct=support, cohort=cohort,
                strength="relatively-strong" if strong else "weak",
                decision=decisions.get(tag, "confirmed" if owner and tag in [owner.name, *owner.aliases] else "unconfirmed")))
        candidates.sort(key=lambda row: (-row.direct.images, -row.cohort.images,
                                         -(row.direct.median or row.cohort.median or 0), row.wd_tag))
        banks.append(AliasBank(reference_name=name, sources=sorted({r.source for r in references if r.character == name}),
            reference_images=len(images), tagged_reference_images=tagged_direct,
            cohort_images=len(cohorts[name]), tagged_cohort_images=len({r.image for r in indirect}),
            candidates=[row.model_copy(update={"rank": i}) for i, row in enumerate(candidates, 1)]))
    inputs = ("anchors.json", "anchors.npy", "characters.json", "character-memory.json", "wd-tagger.json",
              "identities.json", "identities.npy", "identity-provenance.json", "identity-embedding.json")
    return AliasDocument(corpus_fingerprint=provenance.corpus_fingerprint, semantic_profile=provenance.semantic_profile,
        input_digests={name: file_digest(out / name) for name in inputs if (out / name).exists()}, banks=banks)


def emit_alias_candidates(out: Path) -> AliasDocument:
    """Publish the proposal sidecar; authoritative memory is never written here."""
    result = generate(out)
    save_model(out / "alias-candidates.json", result)
    return result
