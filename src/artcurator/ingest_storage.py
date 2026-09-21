"""G1 filesystem admission, integrity and process-released single-writer lease."""
import os
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .config import Settings
from .identity_store import file_digest
from .ingest_schema import Artifact, IngestError, Options


def long_path(path: Path) -> Path:
    """Use Win32 extended paths for nested full-SHA cache namespaces, without registry changes."""
    absolute = path.resolve()
    if os.name == "nt" and not str(absolute).startswith("\\\\?\\"):
        text = str(absolute)
        return Path("\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text)
    return absolute


def validate_paths(settings: Settings) -> None:
    destination = long_path(settings.out)
    for source in (settings.input, settings.references, settings.posted, settings.characters_root):
        root = long_path(source)
        if destination.is_relative_to(root) or root.is_relative_to(destination):
            raise IngestError(f"source/output overlap: {root}")
    if not settings.input.is_dir():
        raise IngestError("source root unavailable; access must be revalidated before resume")
    # A linked derived directory could otherwise redirect writes into originals.
    if destination.exists() and any(p.is_symlink() or p.is_junction() for p in destination.rglob("*")):
        raise IngestError("linked derived storage is not admitted")


def retained_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def admit(root: Path, reservation: int, options: Options) -> int:
    """Reserve prospective bytes including previous revisions, caches and replacements."""
    retained = retained_bytes(root) if root.exists() else 0
    if retained + reservation > options.quota_bytes:
        raise IngestError(f"derived quota exceeded: retained={retained} reservation={reservation}")
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < reservation + options.reserve_bytes:
        raise IngestError("free-disk reserve would be violated")
    return retained


def artifacts(root: Path, paths: tuple[Path, ...]) -> tuple[Artifact, ...]:
    return tuple(Artifact(path=p.relative_to(root).as_posix(), sha256=file_digest(p),
                          size=p.stat().st_size) for p in paths)


def valid(root: Path, entries: tuple[Artifact, ...]) -> bool:
    for entry in entries:
        path = (root / entry.path).resolve()
        if not path.is_relative_to(root.resolve()):
            raise IngestError("artifact escapes derived root")
        if not path.is_file() or path.stat().st_size != entry.size or file_digest(path) != entry.sha256:
            return False
    return True


@contextmanager
def lease(root: Path) -> Iterator[None]:
    """OS byte lock releases on process death; stale lock files need no unsafe unlink."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / "owner.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise IngestError("ingestion already has an owner") from error
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def protect_sources(settings: Settings, profile: Path | None = None) -> Iterator[None]:
    """Python write interception, not an OS/native-code sandbox; installed in workers too."""
    roots = tuple(long_path(p) for p in (settings.input, settings.references,
                                       settings.posted, settings.characters_root))
    if profile:
        roots = (*roots, long_path(profile))
    enabled = [True]

    def audit(event: str, args: tuple) -> None:
        if not enabled[0]:
            return
        paths = ()
        if event == "open":
            path, mode, flags = args
            if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                paths = (path,)
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime"}:
            paths = args[:1]
        elif event in {"os.rename", "os.link", "os.symlink"}:
            paths = args[:2]
        for raw in paths:
            if isinstance(raw, (str, bytes)):
                path = long_path(Path(os.fsdecode(raw)))
                if any(path.is_relative_to(root) for root in roots):
                    raise PermissionError(f"G1 source write prohibited: {path}")

    sys.addaudithook(audit)
    try:
        yield
    finally:
        enabled[0] = False
