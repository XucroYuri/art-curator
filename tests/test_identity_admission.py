"""ADR-0004 admission distinguishes primary gates from strict diagnostics."""
from pathlib import Path

import pytest

from artcurator.identity_admission import (
    AdmissionEvidence, AdmissionReceipt, BatchEvidence, Comparison, CorpusEvidence,
    PrimaryBudget, issue_certificate,
)
from artcurator.identity_profiles import ExecutionProfile


@pytest.fixture
def evidence() -> AdmissionEvidence:
    """Synthetic evidence fails the diagnostic but passes primary gates."""
    check = Comparison(max_cosine_deviation=1.6e-8, max_component_error=2.6e-5,
        component_pass=True, cosine_pass=True, max_pairwise_cosine_error=3.2e-5,
        cluster_adjusted_rand=1., outlier_changes=0, probe_flips_outside_ambiguity=0,
        rank_inversions_outside_ambiguity=0, fp32_component_pass=False)
    return AdmissionEvidence(model="fixture", revision="immutable", preprocess="fixture-v1",
        execution=ExecutionProfile(device="cuda", precision="float32", batch_size=16, runtime={"threads": "4"}),
        selected_batch=16,
        gpu_batches=[BatchEvidence(batch_size=size, comparison=check) for size in (1, 8, 16, 32)],
        corpora=[CorpusEvidence.model_validate({**check.model_dump(), "corpus": alias, "faces": 128,
                 "batch_vs_serial": check, "stored_fp16": check}) for alias in ("library", "review", "similarity")],
        sample_manifest_sha256="a" * 64, cpu_reference_sha256="b" * 64, cpu_evidence_sha256="c" * 64)


def test_certificate_when_only_strict_diagnostic_fails(tmp_path: Path, evidence: AdmissionEvidence) -> None:
    # Given primary/decision/batch equivalence and a failed strict diagnostic.
    # When issuing the real certificate and receipt.
    certificate = issue_certificate(evidence, "d" * 64, tmp_path / "certificate.json")
    # Then admission succeeds and the diagnostic failure stays in the receipt.
    assert certificate.numerical_pass is True
    assert certificate.execution.batch_size == 16
    assert certificate.evidence_sha256 == "d" * 64
    receipt = AdmissionReceipt.model_validate_json((tmp_path / "admission-receipt.json").read_bytes())
    assert receipt.evidence.corpora[1].fp32_component_pass is False
    assert receipt.criterion == "ADR-0004"


@pytest.mark.parametrize("case", [
    ("component_pass", False), ("cosine_pass", False),
    ("max_cosine_deviation", 1.00001e-5), ("max_pairwise_cosine_error", .00201),
    ("cluster_adjusted_rand", .9899), ("probe_flips_outside_ambiguity", 1),
    ("rank_inversions_outside_ambiguity", 1), ("outlier_changes", 1),
    ("rank_inversions_outside_ambiguity", None), ("fp32_component_pass", None),
])
def test_reject_when_gate_fails_or_check_missing(
    tmp_path: Path, evidence: AdmissionEvidence, case: tuple[str, float | bool | None],
) -> None:
    # Given one failed gate or absent required measurement.
    field, value = case
    failed = evidence.corpora[1].model_copy(update={field: value})
    candidate = evidence.model_copy(update={"corpora": [evidence.corpora[0], failed, evidence.corpora[2]]})
    # When publishing; then no certificate is issued.
    with pytest.raises(ValueError, match="admission"):
        issue_certificate(candidate, "d" * 64, tmp_path / "certificate.json")
    assert not (tmp_path / "certificate.json").exists()


@pytest.mark.parametrize("section", ["batch_vs_serial", "stored_fp16"])
def test_reject_when_batch_or_storage_fails(
    tmp_path: Path, evidence: AdmissionEvidence, section: str,
) -> None:
    # Given a batch/storage failure, not a CPU-versus-GPU failure.
    failed = evidence.corpora[0].batch_vs_serial.model_copy(update={"component_pass": False})
    corpus = evidence.corpora[0].model_copy(update={section: failed})
    candidate = evidence.model_copy(update={"corpora": [corpus, *evidence.corpora[1:]]})
    # When publishing; then admission is rejected.
    with pytest.raises(ValueError, match="admission"):
        issue_certificate(candidate, "d" * 64, tmp_path / "cert.json")


@pytest.mark.parametrize("profile", [
    ExecutionProfile(device="cuda", precision="float16", batch_size=16, runtime={"threads": "4"}),
    ExecutionProfile(device="cuda", precision="float32", batch_size=8, runtime={"threads": "4"}),
    ExecutionProfile(device="cpu", precision="float32", batch_size=16, runtime={"threads": "4"}),
])
def test_reject_when_profile_is_not_adr_profile(
    tmp_path: Path, evidence: AdmissionEvidence, profile: ExecutionProfile,
) -> None:
    # Given an unadmitted execution profile, even with positive numerical claims.
    candidate = evidence.model_copy(update={"execution": profile})
    # When publishing; then FP16 and other profiles cannot inherit admission.
    with pytest.raises(ValueError, match="admission"):
        issue_certificate(candidate, "d" * 64, tmp_path / "cert.json")


def test_reject_when_batch_evidence_missing(tmp_path: Path, evidence: AdmissionEvidence) -> None:
    # Given incomplete measurement coverage.
    candidate = evidence.model_copy(update={"gpu_batches": evidence.gpu_batches[:-1]})
    # When publishing; then every required batch measurement remains mandatory.
    with pytest.raises(ValueError, match="admission"):
        issue_certificate(candidate, "d" * 64, tmp_path / "cert.json")


def test_budget_when_primary_tolerance_is_relaxed() -> None:
    # Given a post-hoc component relaxation.
    budget = PrimaryBudget(component_atol=.002, component_rtol=.001, max_cosine_deviation=1e-5,
        pairwise_cosine_atol=.002, cluster_ari_min=.99, probe_cosine_cutoff=.85, probe_ambiguity=.002)
    # When checking the primary budget; then the relaxation cannot pass.
    assert budget.unchanged() is False
