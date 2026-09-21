"""Frozen G2 client contract built from sealed PROPOSE inputs plus scoped human labels."""
from pathlib import Path, PurePosixPath
from typing import Literal

from .identity_store import digest, file_digest
from .ingest_schema import Frozen, IngestError, Receipt
from .negotiation_clusters import ClusterReport, clusters
from .negotiation_consent import Member, Prediction
from .negotiation_copy import COPY, Presentation
from .negotiation_folders import FolderPopulation, FolderReport, measure
from .negotiation_metrics import Labels, Proportion, proportion
from .negotiation_sources import Evidence


class GlobalEvidence(Frozen):
    files: int
    unique_images: int
    faces: int | None
    processed_images: int
    unavailable_occurrences: int
    decode_failed_images: int
    scope: str = "G1 census inventory; per-folder prospective SRS capped at 100"
    whole_image_denominator: int = 0
    whole_image_unknown: None = None
    whole_image_conflict: None = None
    crop_candidate_denominator: int
    crop_unknown: Proportion
    crop_conflict: Proportion
    missing_vocabulary: str = "Unknown: G1 supplies no corpus-wide vocabulary coverage measurement"
    unavailable_signals: tuple[str, ...]
    model_profiles: tuple[str, ...]
    costs: tuple[Receipt, ...]


class Recommendations(Frozen):
    eligible_clusters: int
    covered_images: int
    valid_images: int
    cluster_coverage: float | None
    identity_folder_coverage: float | None
    highlight_human_first: bool
    highlight_inheritance: bool
    thresholds: str = "clusters>=3 and coverage>=0.20; eligible identity folders coverage>=0.50"
    selects_for_user: Literal[False] = False


class NegotiationReport(Frozen):
    schema_version: Literal["album-negotiation-v1"] = "album-negotiation-v1"
    report_digest: str = ""
    snapshot_digest: str
    profile_digest: str
    analysis_profile_digest: str
    seal_digest: str
    g1_report_ref: str
    labels: Labels
    labels_digest: str
    global_evidence: GlobalEvidence
    folders: tuple[FolderReport, ...]
    clusters: tuple[ClusterReport, ...]
    eligible_cluster_ids: tuple[int, ...]
    remaining_cluster_ids: tuple[int, ...]
    all_clusters_route: str = "#/clusters"
    members: tuple[Member, ...]
    prediction: Prediction = Prediction()
    recommendations: Recommendations
    presentation: Presentation
    limitations: tuple[str, ...] = (
        "heuristic-unvalidated-not-identity-accuracy",
        "G1-whole-image-vectors-unavailable-crop-evidence-separate",
        "human-label-independence-is-an-attestation",
        "context-disabled-G2-does-not-implement-grouping",
        "G4-G5-mapping-execution-unavailable-no-source-writes",
        "cost-and-tier-estimates-unavailable-not-zero",
    )


def policy_digest() -> str:
    """Semantic implementation and copy changes invalidate old proposals, not G1 evidence."""
    files = sorted(Path(__file__).parent.glob("negotiation*.py"))
    return digest("\n".join(f"{p.name}:{file_digest(p)}" for p in files).encode())


def report_digest(report: NegotiationReport) -> str:
    return digest(report.model_dump_json(exclude={"report_digest"}).encode())


def build_report(evidence: Evidence, labels: Labels) -> NegotiationReport:
    if labels.snapshot_digest != evidence.job.revision:
        raise IngestError("human-label snapshot digest mismatch")
    known = {i.image_id for i in evidence.images}
    if len({label.image_id for label in labels.labels}) != len(labels.labels) or any(
            label.image_id not in known or not label.actor.strip() or not label.evidence_ref.strip() for label in labels.labels):
        raise IngestError("duplicate, unbound or unattributed human labels")
    directories = {"."}
    for row in evidence.inventory.occurrences:
        directories.update(str(p) for p in PurePosixPath(row.path).parents)
    folder_ids = {path: digest(("directory-v1:" + path).encode()) for path in sorted(directories)}
    if not set(labels.targets).issubset(folder_ids.values()) or not set(labels.target_types).issubset(folder_ids.values()):
        raise IngestError("target references unknown folder")
    members = tuple(Member(image_id=r.sha256, path=r.path,
        occurrence_id=digest(("occurrence-v1:" + r.path + ":" + r.sha256).encode()),
        folder_id=folder_ids[str(PurePosixPath(r.path).parent)])
        for r in evidence.inventory.occurrences if r.sha256 and r.status != "unavailable")
    folders = []
    for path, folder_id in folder_ids.items():
        rows = [r for r in evidence.inventory.occurrences if str(PurePosixPath(r.path).parent) == path]
        hashes = {r.sha256 for r in rows if r.status != "unavailable"}
        folders.append(measure(FolderPopulation(folder_id=folder_id, path=path,
            images=tuple(i for i in evidence.images if i.image_id in hashes), occurrences=len(rows),
            unavailable_occurrences=sum(r.status == "unavailable" for r in rows)), labels))
    cluster_reports = clusters(evidence)
    qualifying = tuple(c for c in cluster_reports if c.eligible)
    covered = {sha for c in qualifying for sha in c.image_ids}
    valid = {i.image_id for i in evidence.images if i.vector is not None
             and measure_vector_valid(i.vector)}
    inherited = {sha for f in folders if f.identity_recommendation for sha in f.population_ids}
    options = evidence.candidates.faces if evidence.candidates else []
    denominator = len(options)
    global_evidence = GlobalEvidence(files=evidence.g1.occurrences,
        unique_images=evidence.g1.unique_images, faces=evidence.g1.detected_faces,
        processed_images=evidence.g1.unique_images-len(evidence.g1.decode_failed),
        unavailable_occurrences=sum(r.status == "unavailable" for r in evidence.inventory.occurrences),
        decode_failed_images=len(evidence.g1.decode_failed), crop_candidate_denominator=denominator,
        crop_unknown=proportion(sum(not any(c.source in {"model", "memory"} for c in f.candidates) for f in options)
                                if options else None, denominator, denominator),
        crop_conflict=proportion(sum(f.model_demoted for f in options) if options else None, denominator, denominator),
        unavailable_signals=evidence.g1.unavailable_signals,
        model_profiles=(evidence.job.profile_digest, *((evidence.vector_profile,) if evidence.vector_profile else ())),
        costs=evidence.g1.costs)
    recommendations = Recommendations(eligible_clusters=len(qualifying), covered_images=len(covered),
        valid_images=len(valid), cluster_coverage=len(covered & valid)/len(valid) if valid else None,
        identity_folder_coverage=len(inherited & valid)/len(valid) if valid else None,
        highlight_human_first=len(qualifying) >= 3 and bool(valid) and len(covered & valid)/len(valid) >= .20,
        highlight_inheritance=bool(valid) and len(inherited & valid)/len(valid) >= .50)
    text = {k: v for k, v in COPY.items() if "{" not in v}
    text["coherent_clusters"] = COPY["coherent_clusters"].format(count=len(qualifying), images=len(covered))
    text["confirmation"] = COPY["confirmation"].format(changed="未知", review="未知", none="未知")
    presentation = Presentation(text=text, folder_text={f.folder_id: COPY["measured_evidence"].format(
        method=f.coherence.method, sample=f.sample, population=f.population,
        coverage=f"{f.coherence.valid}/{f.sample} 有效向量", confidence="描述性视觉统计；非身份准确率") for f in folders})
    report = NegotiationReport(snapshot_digest=evidence.job.revision, profile_digest=policy_digest(),
        analysis_profile_digest=evidence.job.profile_digest, seal_digest=evidence.seal_digest,
        g1_report_ref=f"revisions/{evidence.job.revision}/analysis-report.json", labels=labels,
        labels_digest=digest(labels.model_dump_json().encode()), global_evidence=global_evidence,
        folders=tuple(folders), clusters=cluster_reports, members=members,
        eligible_cluster_ids=tuple(c.cluster_id for c in qualifying),
        remaining_cluster_ids=tuple(c.cluster_id for c in cluster_reports if not c.eligible),
        recommendations=recommendations, presentation=presentation)
    return report.model_copy(update={"report_digest": report_digest(report)})


def measure_vector_valid(vector: tuple[float, ...]) -> bool:
    import math
    return bool(vector) and all(math.isfinite(v) for v in vector) and sum(v*v for v in vector) > 1e-24
