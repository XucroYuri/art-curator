# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "Pillow", "psutil", "torch", "transformers==4.57.6", "pydantic>=2", "scikit-learn", "onnxruntime", "PyYAML"]
# ///
# How to run: uv run --no-project --python .venv-identity/Scripts/python.exe python tools/run_identity_gpu.py out/library out/review out/similarity
"""Fresh-profile corpus reruns, preserving old evidence and frozen legacy artifacts."""
import json
import shutil
import sys
import time
from pathlib import Path

from artcurator.config import Settings, confine_writes, environment
from artcurator.identity import run
from artcurator.identity_profiles import execution_profile
from artcurator.identity_schema import IdentityOptions
from artcurator.identity_store import atomic_bytes, file_digest, load_document, load_vectors


def main() -> None:
    outputs = [Path(arg).resolve() for arg in sys.argv[1:]]
    if len(outputs) != 3:
        raise ValueError("provide library, review and similarity outputs in that order")
    if execution_profile(IdentityOptions()).device != "cuda":
        raise ValueError("GPU corpus runner requires an admitted CUDA certificate before starting")
    receipts = []
    environment(outputs[0])
    confine_writes()
    for alias, out in zip(("library", "review", "similarity"), outputs, strict=True):
        before = {name: file_digest(out / name) for name in ("scores.csv", "families.json", "manifest.sqlite")}
        completed = out / "identity-gpu-run.json"
        if completed.exists():
            receipt = json.loads(completed.read_bytes())
            ledger = json.loads((out / "identity-embedding.json").read_bytes())
            load_vectors(out, load_document(out))
            if (receipt["legacy_after"] != before or receipt["namespace"] != ledger["namespace"]
                    or ledger["execution"] != execution_profile(IdentityOptions()).model_dump()
                    or receipt["ab"] != json.loads((out / "identity-ab.json").read_bytes())):
                raise ValueError("completed GPU receipt changed; refuse an ambiguous resume")
            receipts.append(receipt)
            print(f"{alias} preserved completed fresh-run receipt", flush=True)
            continue
        archive = out / "identity-cpu-baseline"
        archive.mkdir(exist_ok=True)
        for name in ("identities.json", "identities.npy", "identity-embedding.json", "identity-ab.json"):
            if (out / name).exists() and not (archive / name).exists():
                shutil.copyfile(out / name, archive / name)
        settings = Settings(input=out, references=out, posted=out, characters_root=out, out=out)
        started = time.perf_counter()
        for command in ("identity-embed", "identity-cluster", "identity-report"):
            stage_start = time.perf_counter()
            run(settings, command)
            print(f"{alias} {command} seconds={time.perf_counter() - stage_start:.3f}", flush=True)
        elapsed = time.perf_counter() - started
        after = {name: file_digest(out / name) for name in before}
        if before != after:
            raise ValueError("legacy artifacts changed during additive identity rerun")
        ledger = json.loads((out / "identity-embedding.json").read_bytes())
        if ledger["execution"]["device"] != "cuda":
            raise ValueError("GPU rerun did not select a certified CUDA profile")
        receipt = {"corpus": alias, "faces": load_document(out).face_count, "wall_seconds": elapsed,
                   "legacy_before": before, "legacy_after": after, "embedding": ledger["metrics"],
                   "namespace": ledger["namespace"], "ab": json.loads((out / "identity-ab.json").read_bytes())}
        receipts.append(receipt)
        atomic_bytes(out / "identity-gpu-run.json", json.dumps(receipt, indent=2).encode())
    atomic_bytes(outputs[0].parent / "identity-certification/corpus-runs.json", json.dumps(receipts, indent=2).encode())


if __name__ == "__main__":
    main()
