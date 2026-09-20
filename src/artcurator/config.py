"""Validated settings and process-wide write confinement."""
import os
import sys
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .identity_schema import IdentityOptions

ROOT: Final = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    """Filesystem paths select datasets, never scoring features."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    input: Path
    references: Path
    posted: Path
    characters_root: Path
    out: Path = ROOT / "out/library"
    batch_size: int = Field(default=16, ge=1, le=64)
    workers: int = Field(default=8, ge=1, le=12)
    prefetch_batches: int = Field(default=2, ge=0, le=4)
    uncertain: float = 1.2
    gaming_suspect: float = 0.35
    nsfw_route: float = Field(default=0.65, ge=0, le=1)
    nsfw_queue: float = Field(default=0.35, ge=0, le=1)
    identity_route_quantile: float = Field(default=0.1, ge=0, le=1)
    identity_queue_quantile: float = Field(default=0.2, ge=0, le=1)
    queue_quantile: float = Field(default=0.9, ge=0, le=1)
    review_quantile: float = Field(default=0.75, ge=0, le=1)
    confusable_margin: float = 0.05
    champion_slack: float = 0.15
    identity: IdentityOptions = Field(default_factory=IdentityOptions)


def output_path(path: Path) -> Path:
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError(f"Writes outside project prohibited: {resolved}")
    return resolved


def load(path: Path) -> Settings:
    with path.open(encoding="utf-8") as handle:
        return Settings.model_validate(yaml.safe_load(handle))


def environment(out: Path) -> None:
    """Keep model, temporary, plotting, and compiler caches inside the project."""
    cache = output_path(out) / "cache"
    for name, relative in {
        "HF_HOME": "huggingface", "TORCH_HOME": "torch", "XDG_CACHE_HOME": "xdg",
        "MPLCONFIGDIR": "matplotlib", "TEMP": "temp", "TMP": "temp",
        "TORCHINDUCTOR_CACHE_DIR": "inductor", "TRITON_CACHE_DIR": "triton",
        "NUMBA_CACHE_DIR": "numba", "CUDA_CACHE_PATH": "cuda",
    }.items():
        directory = (ROOT / "out/library/cache" if name in {"HF_HOME", "TORCH_HOME"} else cache) / relative
        directory.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(directory)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["PYTHONUTF8"] = "1"
    sys.dont_write_bytecode = True


def confine_writes() -> None:
    """Deny Python-level filesystem writes outside ROOT, including library calls."""
    def audit(event: str, args: tuple) -> None:
        if event == "open":
            path, mode, flags = args
            writing = (mode and any(c in mode for c in "wax+")) or (
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            )
            if writing and isinstance(path, (str, bytes)):
                name = os.fsdecode(path)
                if name.lower() != os.devnull.lower():
                    output_path(Path(name))
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime"}:
            output_path(Path(os.fsdecode(args[0])))
        elif event in {"os.rename", "os.link", "os.symlink"}:
            output_path(Path(os.fsdecode(args[0])))
            output_path(Path(os.fsdecode(args[1])))
    sys.addaudithook(audit)
