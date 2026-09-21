"""Private corpus receipts: coverage and confusable occurrences, not accuracy labels."""
import argparse
from collections import Counter
from pathlib import Path

import numpy as np

from .candidates_schema_v2 import CandidateDocumentV2
from .identity_schema import Record
from .identity_store import file_digest, save_model
from .wd_schema import TagDocument


class Receipt(Record):
    corpus: str
    faces: int
    model_candidate_faces: int
    model_candidate_coverage: float
    memory_candidate_faces: int
    memory_candidate_entries: int
    suggested: int
    abstained: int
    confusable: str
    confusable_faces: int
    confusable_images: int
    confusable_top1: int
    confusable_above_085: int
    attribute_tags: dict[str, int]
    hair_colors: dict[str, int]
    gpu_inference_seconds: float
    gpu_load_seconds: float
    wall_seconds: float
    uncached_crops: int
    artifact_sha256: dict[str, str]
    model_suggestions: int
    model_primary: int
    model_demoted: int
    demotion_sources: dict[str, int]
    suggested_verified: int
    confusable_model_suggestions: int
    confusable_model_demoted: int
    model_scores: dict[str, float]
    model_margins: dict[str, float]
    margin_bases: dict[str, int]


def distribution(values: list[float]) -> dict[str, float]:
    """Compact quantile receipt; empty evidence is not a fabricated zero score."""
    if not values:
        return {}
    return dict(zip(("min", "p25", "median", "p75", "p95", "max"),
                    map(float, np.quantile(values, [0, .25, .5, .75, .95, 1])), strict=True))


def report(out: Path, confusable: str) -> Receipt:
    document = CandidateDocumentV2.model_validate_json((out / "identity-candidates.json").read_bytes())
    wd = TagDocument.model_validate_json((out / "wd-tagger.json").read_bytes())
    models = sum(any(c.source == "model" or c.score_model is not None for c in f.candidates) for f in document.faces)
    memory = [sum(c.source == "memory" or c.score_memory is not None for c in f.candidates) for f in document.faces]
    confused = [f for f in wd.faces if any(t.tag == confusable for t in f.evidence.characters)]
    proposals = [f for f in document.faces if f.suggested_model is not None]
    confusable_proposals = [f for f in proposals if f.suggested_model and f.suggested_model.name == confusable]
    result = Receipt(corpus=out.name, faces=len(document.faces), model_candidate_faces=models,
        model_candidate_coverage=models / len(document.faces) if document.faces else 0,
        memory_candidate_faces=sum(n > 0 for n in memory), memory_candidate_entries=sum(memory),
        suggested=sum(not f.abstained for f in document.faces), abstained=sum(f.abstained for f in document.faces),
        confusable=confusable, confusable_faces=len(confused), confusable_images=len({f.image_sha16 for f in confused}),
        confusable_top1=sum(f.evidence.characters[0].tag == confusable for f in confused),
        confusable_above_085=sum(any(t.tag == confusable and t.score > .85 for t in f.evidence.characters) for f in confused),
        attribute_tags=dict(Counter(t.tag for f in document.faces for t in f.attributes.tags).most_common(20)),
        hair_colors=dict(Counter(f.attributes.hair_color for f in document.faces if f.attributes.hair_color)),
        gpu_inference_seconds=sum(b.inference_seconds for b in wd.batches),
        gpu_load_seconds=sum(b.load_seconds for b in wd.batches), wall_seconds=wd.wall_seconds,
        uncached_crops=sum(len(b.input_ids) for b in wd.batches),
        model_suggestions=len(proposals),
        model_primary=sum(not f.model_demoted and f.suggested_verified is None for f in proposals),
        model_demoted=sum(f.model_demoted for f in proposals),
        demotion_sources=dict(Counter(source for f in proposals for source in {d.source for d in f.disagreements})),
        suggested_verified=sum(f.suggested_verified is not None for f in document.faces),
        confusable_model_suggestions=len(confusable_proposals),
        confusable_model_demoted=sum(f.model_demoted for f in confusable_proposals),
        model_scores=distribution([f.suggested_model.score for f in proposals if f.suggested_model]),
        model_margins=distribution([f.suggested_model.margin_vs_runner_up for f in proposals if f.suggested_model]),
        margin_bases=dict(Counter(f.suggested_model.margin_basis for f in proposals if f.suggested_model)),
        artifact_sha256={name: file_digest(out / name) for name in ("wd-tagger.json", "identity-candidates.json", "character-memory.json")})
    save_model(out / "identity-candidates-report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--confusable", required=True)
    args = parser.parse_args()
    print(report(args.out, args.confusable).model_dump_json(indent=2))
