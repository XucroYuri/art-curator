"""Long-lived, deadline-bounded subprocess exchange, polled at most every 60 seconds."""
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

from .wd_schema import Request, Response


class Exchange:
    """Own one inference process and its stdout reader; coordinator owns all evidence files."""

    def __init__(self, process: subprocess.Popen[str], reader: ThreadPoolExecutor) -> None:
        self.process = process
        self.reader = reader

    def request(self, request: Request) -> Response:
        stdin, stdout = self.process.stdin, self.process.stdout
        if stdin is None or stdout is None:
            raise RuntimeError("worker pipes unavailable")
        stdin.write(request.model_dump_json() + "\n")
        stdin.flush()
        future = self.reader.submit(stdout.readline)
        while True:
            remaining = request.deadline - time.time()
            if remaining <= 0:
                self.process.kill()
                raise TimeoutError("WD worker deadline exceeded")
            try:
                line = future.result(timeout=min(60, remaining))
                break
            except TimeoutError:
                print(f"WD worker pending pid={self.process.pid} remaining={remaining:.0f}s", flush=True)
        response = Response.model_validate_json(line)
        if (response.handshake != request.handshake or response.run_id != request.run_id
                or response.request_id != request.request_id or response.input_ids != request.input_ids
                or len(response.evidence) != len(request.input_ids)
                or (response.raw is not None and len(response.raw) != len(request.input_ids))
                or time.time() >= request.deadline
                or not response.providers_active or response.providers_active[0] != request.handshake.provider):
            raise ValueError("WD response lineage mismatch")
        return response


@contextmanager
def worker(python: Path, error_log: TextIO) -> Iterator[Exchange]:
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONUTF8": "1"}
    with subprocess.Popen([str(python), "-m", "artcurator.wd_worker"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=error_log, encoding="utf-8", cwd=root, env=env) as process:
        with ThreadPoolExecutor(max_workers=1) as reader:
            try:
                yield Exchange(process, reader)
            finally:
                if process.stdin:
                    process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
