"""ADR-0004: fixed primary budgets and decision-equivalent CUDA FP32 admission."""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field

from .identity_profiles import Certificate, ExecutionProfile
from .identity_schema import Digest, Record
from .identity_store import save_model


@dataclass
class AdmissionRejected(ValueError):
    reason: str

    def __str__(self) -> str:
        return f"GPU FP32 admission rejected: {self.reason}"


class Comparison(Record):
    max_cosine_deviation: float
    max_component_error: float = Field(ge=0)
    component_pass: bool
    cosine_pass: bool
    max_pairwise_cosine_error: float = Field(ge=0)
    cluster_adjusted_rand: float = Field(ge=-1, le=1)
    outlier_changes: int = Field(ge=0)
    probe_flips_outside_ambiguity: int = Field(ge=0)
    rank_inversions_outside_ambiguity: int | None = Field(default=None, ge=0)
    fp32_component_pass: bool | None = None

    def admitted(self) -> bool:
        """Strict FP32 component agreement is reported, never used as a gate."""
        return (self.component_pass and self.cosine_pass
                and self.max_cosine_deviation <= 1e-5
                and self.max_pairwise_cosine_error <= .002
                and self.cluster_adjusted_rand >= .99
                and self.outlier_changes == 0
                and self.probe_flips_outside_ambiguity == 0
                and self.rank_inversions_outside_ambiguity == 0)


class BatchEvidence(Record):
    batch_size: int
    comparison: Comparison


class CorpusEvidence(Comparison):
    corpus: str
    faces: Literal[128]
    batch_vs_serial: Comparison
    stored_fp16: Comparison


class AdmissionEvidence(Record):
    model: str
    revision: str
    preprocess: str
    execution: ExecutionProfile
    selected_batch: int
    gpu_batches: list[BatchEvidence]
    corpora: list[CorpusEvidence]
    sample_manifest_sha256: Digest
    cpu_reference_sha256: Digest
    cpu_evidence_sha256: Digest
    array_sha256: dict[str, Digest] = Field(default_factory=dict)


class PrimaryBudget(Record):
    component_atol: float
    component_rtol: float
    max_cosine_deviation: float
    pairwise_cosine_atol: float
    cluster_ari_min: float
    probe_cosine_cutoff: float
    probe_ambiguity: float

    def unchanged(self) -> bool:
        """Do not inherit mutable tolerances from an observed candidate failure."""
        return (self.component_atol, self.component_rtol, self.max_cosine_deviation,
                self.pairwise_cosine_atol, self.cluster_ari_min,
                self.probe_cosine_cutoff, self.probe_ambiguity) == (.001, .001, 1e-5, .002, .99, .85, .002)


class OriginalEvidence(Record):
    model: str
    revision: str
    preprocess: str
    budget: PrimaryBudget
    sample_manifest_sha256: Digest


class AdmissionReceipt(Record):
    criterion: Literal["ADR-0004"] = "ADR-0004"
    strict_fp32_role: Literal["reported-diagnostic-only"] = "reported-diagnostic-only"
    certificate: Certificate
    evidence: AdmissionEvidence


def issue_certificate(evidence: AdmissionEvidence, evidence_sha256: str, destination: Path) -> Certificate:
    """Publish only the measured profile, with the full diagnostic receipt first."""
    profile = evidence.execution
    if (profile.device, profile.precision, profile.batch_size, evidence.selected_batch) != (
        "cuda", "float32", 16, 16
    ) or profile.runtime.get("threads") != "4" or profile.kernel != "sdpa-auto-tf32-off":
        raise AdmissionRejected("execution is outside ADR-0004 scope")
    if (sorted(batch.batch_size for batch in evidence.gpu_batches) != [1, 8, 16, 32]
            or len(evidence.corpora) != 3 or len({c.corpus for c in evidence.corpora}) != 3):
        raise AdmissionRejected("incomplete or duplicate measurement coverage")
    checks = [batch.comparison for batch in evidence.gpu_batches]
    for corpus in evidence.corpora:
        checks.extend((corpus, corpus.batch_vs_serial, corpus.stored_fp16))
    if not all(check.admitted() for check in checks):
        raise AdmissionRejected("primary, decision, batch or storage gate failed")
    if any(check.fp32_component_pass is None for check in checks):
        raise AdmissionRejected("strict diagnostic was not recorded")
    certificate = Certificate(version=1, model=evidence.model, revision=evidence.revision,
        preprocess=evidence.preprocess, execution=profile, numerical_pass=True, evidence_sha256=evidence_sha256)
    save_model(destination.with_name("admission-receipt.json"), AdmissionReceipt(
        certificate=certificate, evidence=evidence))
    save_model(destination, certificate)
    return certificate
