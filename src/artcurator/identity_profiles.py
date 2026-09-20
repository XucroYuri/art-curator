"""Execution identities and conservative, evidence-bound automatic placement."""
import importlib.metadata
import json
from pathlib import Path
from typing import Final, Literal, assert_never

from pydantic import Field

from .identity_schema import IdentityOptions, Record
from .identity_store import digest

PREPROCESS: Final = "crop-jpeg-v1-siglip-official"
CERTIFICATE: Final = Path(__file__).with_name("identity-certification.json")


class ExecutionProfile(Record):
    device: Literal["cpu", "cuda"]
    precision: Literal["float32", "float16"]
    batch_size: int = Field(ge=1, le=32)
    runtime: dict[str, str]
    kernel: str = "sdpa-auto-tf32-off"


class Certificate(Record):
    version: Literal[1]
    model: str
    revision: str
    preprocess: str
    execution: ExecutionProfile
    numerical_pass: bool
    evidence_sha256: str


def embedding_namespace(profile: ExecutionProfile, model_identity: str, preprocess: str) -> str:
    """Full profile hash; the final key additionally contains the full crop SHA-256."""
    return digest(json.dumps({"execution": profile.model_dump(), "model": model_identity,
                              "preprocess": preprocess}, sort_keys=True).encode())


def execution_profile(options: IdentityOptions) -> ExecutionProfile:
    """Explicit CUDA is experimental until certified; auto never guesses compatibility."""
    import torch
    runtime = {name: importlib.metadata.version(name) for name in
               ("torch", "transformers", "Pillow", "numpy", "onnxruntime")}
    runtime["threads"] = str(options.threads)
    cpu = ExecutionProfile(device="cpu", precision="float32", batch_size=1, runtime=runtime)
    if options.device == "cpu":
        return cpu
    if options.embedder == "ccip":
        if options.device == "cuda":
            raise ValueError("CCIP CUDA execution is not implemented; choose CPU explicitly")
        return cpu
    if not torch.cuda.is_available():
        if options.device == "cuda":
            raise ValueError("CUDA requested but unavailable; no CPU substitution")
        return cpu
    runtime = {**runtime, "gpu": torch.cuda.get_device_name(), "cuda": str(torch.version.cuda),
               "capability": str(torch.cuda.get_device_capability())}
    gpu = ExecutionProfile(device="cuda", precision=options.precision, batch_size=options.batch_size, runtime=runtime)
    match options.device:
        case "cuda":
            return gpu
        case "auto":
            if CERTIFICATE.exists():
                certificate = Certificate.model_validate_json(CERTIFICATE.read_bytes())
                if certificate.numerical_pass and certificate.execution == gpu:
                    return gpu
            return cpu
        case "cpu":
            return cpu
        case unreachable:
            assert_never(unreachable)


def certify_model(profile: ExecutionProfile, model: tuple[str, str]) -> None:
    """Auto admission must match immutable weights as well as the runtime."""
    certificate = Certificate.model_validate_json(CERTIFICATE.read_bytes())
    if (certificate.model, certificate.revision, certificate.preprocess, certificate.execution) != (
        *model, PREPROCESS, profile
    ):
        raise ValueError("automatic CUDA certificate does not cover this model/profile")
