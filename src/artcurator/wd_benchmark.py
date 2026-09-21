"""Paired compact-evidence CPU/GPU throughput receipts, not accuracy certification."""
import argparse
import time
import uuid
from pathlib import Path

from pydantic import Field

from .identity_schema import Record
from .identity_store import load_document, save_model
from .wd_exchange import worker
from .wd_schema import Request, Response, TagDocument


class Benchmark(Record):
    method: str = "same first eight saved crops; CPU then CUDA; two repeats each; includes first-inference warmup"
    samples: list[Response] = Field(default_factory=list)
    total_seconds: float = 0


def benchmark(out: Path, dlls: Path | None) -> Benchmark:
    root = Path(__file__).resolve().parents[2]
    wd = TagDocument.model_validate_json((out / "wd-tagger.json").read_bytes())
    faces = load_document(out).faces[:8]
    crop_ids = {f.face_id: f.crop_sha256 for f in wd.faces}
    result: list[Response] = []
    started = time.perf_counter()
    for provider in ("CPUExecutionProvider", "CUDAExecutionProvider"):
        handshake = wd.handshake.model_copy(update={"provider": provider})
        with (out / "wd-benchmark-worker.log").open("a", encoding="utf-8") as errors, worker(
                root / ".venv-wdtagger/Scripts/python.exe", errors) as exchange:
            for _ in range(2):
                request = Request(handshake=handshake, run_id="benchmark", request_id=uuid.uuid4().hex,
                    deadline=time.time() + 240, model_dir=str(root / "out/zero-shot-candidates/model"),
                    crops=[str((out / f.crop_rel).resolve()) for f in faces],
                    input_ids=[crop_ids[f.face_id] for f in faces],
                    cuda_dll_directory=str(dlls.resolve()) if dlls else None)
                result.append(exchange.request(request))
    receipt = Benchmark(samples=result, total_seconds=time.perf_counter() - started)
    save_model(out / "wd-throughput.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cuda-dlls", type=Path)
    args = parser.parse_args()
    print(benchmark(args.out, args.cuda_dlls).model_dump_json(indent=2, exclude={"samples": {"__all__": {"evidence"}}}))
