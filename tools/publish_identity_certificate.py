# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "Pillow", "torch", "transformers==4.57.6", "pydantic>=2", "onnxruntime", "scikit-learn", "psutil"]
# ///
# How to run: uv run --no-project --python .venv-identity/Scripts/python.exe python tools/publish_identity_certificate.py
"""Issue ADR-0004 admission from immutable measurements, without rerunning inference."""
import numpy as np

from artcurator.config import ROOT
from artcurator.identity_admission import (
    AdmissionEvidence, AdmissionRejected, BatchEvidence, Comparison, CorpusEvidence,
    OriginalEvidence, PrimaryBudget, issue_certificate,
)
from artcurator.identity_profiles import CERTIFICATE, PREPROCESS, execution_profile
from artcurator.identity_schema import IdentityOptions
from artcurator.identity_store import file_digest, save_model
from certify_identity_fp32 import strict_comparison


def main() -> None:
    directory = ROOT / "out/identity-certification"
    source = directory / "fp32-results.json"
    result = AdmissionEvidence.model_validate_json(source.read_bytes())
    for expected, name in ((result.cpu_evidence_sha256, "results.json"),
                           (result.sample_manifest_sha256, "sample-manifest.json"),
                           (result.cpu_reference_sha256, "cpu-fp32.npy")):
        if expected != file_digest(directory / name):
            raise AdmissionRejected(f"changed evidence: {name}")
    prior = OriginalEvidence.model_validate_json((directory / "results.json").read_bytes())
    budget = PrimaryBudget.model_validate_json((directory / "predeclared-budgets.json").read_bytes())
    if prior.budget != budget or not budget.unchanged():
        raise AdmissionRejected("primary predeclared budgets changed")
    if (prior.model, prior.revision, prior.preprocess, prior.sample_manifest_sha256) != (
        result.model, result.revision, result.preprocess, result.sample_manifest_sha256
    ):
        raise AdmissionRejected("CPU/GPU semantic identity or sample mismatch")
    # Recheck saved vectors, not GPU inference. Also fill previously unmeasured
    # stored-FP16 rank/strict diagnostics; never treat a missing rank count as zero.
    reference = np.load(directory / "cpu-fp32.npy", allow_pickle=False)
    serial = np.load(directory / "gpu-fp32-b1.npy", allow_pickle=False)
    candidate = np.load(directory / "gpu-fp32-b16.npy", allow_pickle=False)
    if reference.shape != (384, 1152) or candidate.shape != reference.shape or serial.shape != reference.shape:
        raise AdmissionRejected("unexpected sample dimensions")
    array_hashes: dict[str, str] = {}
    batches = []
    for batch in result.gpu_batches:
        name = f"gpu-fp32-b{batch.batch_size}.npy"
        values = np.load(directory / name, allow_pickle=False)
        batches.append(BatchEvidence(batch_size=batch.batch_size,
            comparison=Comparison.model_validate(strict_comparison(reference, values))))
        array_hashes[name] = file_digest(directory / name)
    corpora = []
    for index, corpus in enumerate(result.corpora):
        interval = slice(index * 128, (index + 1) * 128)
        corpora.append(CorpusEvidence.model_validate({"corpus": corpus.corpus, "faces": corpus.faces,
            **strict_comparison(reference[interval], candidate[interval]),
            "batch_vs_serial": strict_comparison(serial[interval], candidate[interval]),
            "stored_fp16": strict_comparison(reference[interval], candidate[interval].astype(np.float16))}))
    evidence = result.model_copy(update={"gpu_batches": batches, "corpora": corpora, "array_sha256": array_hashes})
    if evidence.execution != execution_profile(IdentityOptions(device="cuda")) or evidence.preprocess != PREPROCESS:
        raise AdmissionRejected("live runtime does not match measured profile")
    certificate = issue_certificate(evidence, file_digest(source), directory / "candidate-certificate.json")
    save_model(CERTIFICATE, certificate)
    print(certificate.model_dump_json(indent=2), flush=True)


if __name__ == "__main__":
    main()
