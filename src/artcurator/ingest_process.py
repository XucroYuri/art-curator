"""Independent local owner and interruptible subprocess stages; no hidden-window launch."""
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from threading import Event, Thread

import psutil

from .config import ROOT
from .identity_store import save_model
from .ingest_adapters import Request, Result, execute
from .ingest_runtime import requested
from .ingest_schema import IngestError, Launch
from .ingest_storage import protect_sources


def kill_tree(process: subprocess.Popen[bytes]) -> None:
    """Stop descendants too (including the persistent WD worker), then reap the child."""
    try:
        descendants = psutil.Process(process.pid).children(recursive=True)
        for child in reversed(descendants):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                continue
    except psutil.NoSuchProcess:
        descendants = []
    if process.poll() is None:
        process.kill()
    process.wait()


def execute_process(request: Request) -> Result:
    root = request.settings.out.parent.parent
    exchange = root / "exchange"
    exchange.mkdir(exist_ok=True)
    key = uuid.uuid4().hex
    source, response = exchange / (key + ".json"), exchange / (key + "-result.json")
    save_model(source, request)
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    stopping_at: float | None = None
    started = time.monotonic()
    with (root / "stages.log").open("ab") as log:
        with subprocess.Popen([sys.executable, "-m", "artcurator.ingest_process", "stage", str(source),
                               str(response), str(os.getpid())], cwd=ROOT, env=env,
                              stdin=subprocess.DEVNULL, stdout=log, stderr=log) as process:
            try:
                while process.poll() is None:
                    if time.monotonic() - started >= request.options.stage_deadline_seconds:
                        kill_tree(process)
                        return Result(outcome="failed", reason="interrupted: declared stage deadline expired")
                    if requested(root) in {"pause", "cancel"}:
                        stopping_at = stopping_at or time.monotonic()
                    if stopping_at is not None and time.monotonic() - stopping_at >= request.options.deadline_seconds:
                        kill_tree(process)
                        return Result(outcome="failed", reason="interrupted: in-flight pause deadline expired")
                    time.sleep(0.1)
            finally:
                if process.poll() is None:
                    kill_tree(process)
    if not response.is_file():
        return Result(outcome="failed", reason=f"stage process exited {process.returncode} without validated response")
    result = Result.model_validate_json(response.read_bytes())
    if process.returncode and result.outcome != "failed":
        raise IngestError("nonzero worker exit cannot report successful completion")
    return result


def launch(document: Launch) -> int:
    """The owner outlives this CLI/client. Output/log handles never depend on its terminal."""
    root = document.settings.out
    root.mkdir(parents=True, exist_ok=True)
    destination = root / "launch.json"
    save_model(destination, document)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with (root / "owner.log").open("ab") as log:
        process = subprocess.Popen([sys.executable, "-m", "artcurator.ingest_process", "owner", str(destination)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags,
            start_new_session=os.name != "nt", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return process.pid


def _parent_watch(parent: int, done: Event) -> None:
    """Interrupted owner cannot leave an unowned inference process continuing writes."""
    try:
        owner = psutil.Process(parent)
        while not done.wait(0.5):
            if not owner.is_running():
                break
        else:
            return
    except psutil.NoSuchProcess:
        owner = None
    for child in psutil.Process().children(recursive=True):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            continue
    os._exit(75)


def main() -> None:
    mode = sys.argv[1]
    if mode == "owner":
        import logging
        from .ingest import run
        from .config import environment
        document = Launch.model_validate_json(Path(sys.argv[2]).read_bytes())
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        environment(document.settings.out)
        run(document.settings, document.options, execute=execute_process)
        return
    request = Request.model_validate_json(Path(sys.argv[2]).read_bytes())
    response = Path(sys.argv[3])
    done = Event()
    watcher = Thread(target=_parent_watch, args=(int(sys.argv[4]), done), daemon=True)
    watcher.start()
    try:
        with protect_sources(request.settings, request.options.profile_from):
            result = execute(request)
        save_model(response, result)
    except Exception as error:
        # Worker boundary: return the failure reason and nonzero exit, never a partial success.
        import logging
        logging.exception("ingest stage failed action=%s", request.action)
        save_model(response, Result(outcome="failed", reason=f"{type(error).__name__}: {error}"))
        raise
    finally:
        done.set()
        watcher.join()


if __name__ == "__main__":
    main()
