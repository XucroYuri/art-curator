"""Full-content occurrence snapshots; filenames never become inference features."""
import json
from collections.abc import Callable
from pathlib import Path

from .identity_store import digest, file_digest
from .ingest_schema import Inventory, Occurrence
from .scan import image_paths


def discover(root: Path, notify: Callable[[int], None], sample: int | None = None) -> tuple[Occurrence, ...]:
    """Select the case-sensitive POSIX-relative lexical prefix before reading bytes."""
    records: list[Occurrence] = []
    seen: set[str] = set()
    paths = sorted(image_paths(root), key=lambda path: path.relative_to(root).as_posix())
    for index, path in enumerate(paths[:sample]):
        relative = path.relative_to(root).as_posix()
        try:
            before = path.stat()
            content = file_digest(path)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                records.append(Occurrence(path=relative, status="unavailable", reason="changed during snapshot"))
            else:
                records.append(Occurrence(path=relative, sha256=content, size=after.st_size,
                    mtime_ns=after.st_mtime_ns, status="duplicate" if content in seen else "indexed"))
                seen.add(content)
        except OSError as error:
            records.append(Occurrence(path=relative, status="unavailable", reason=str(error)))
        notify(index + 1)
    return tuple(records)


def freeze(records: tuple[Occurrence, ...], prior: Inventory | None, profile: str) -> Inventory:
    current = {r.path: r for r in records}
    old = {r.path: r for r in prior.occurrences if r.status != "unavailable"} if prior else {}
    removed = tuple(sorted(old.keys() - current.keys()))
    missing = tuple(old[p].model_copy(update={"status": "unavailable", "reason": "missing from snapshot"})
                    for p in removed)
    # Metadata is retained as evidence but only content/location/status selects semantic revisions.
    signature = [(r.path, r.sha256, r.status) for r in records]
    revision = digest(json.dumps([profile, signature], separators=(",", ":")).encode())
    return Inventory(revision=revision, parent_revision=prior.revision if prior else None,
        occurrences=records + missing, selected_paths=tuple(r.path for r in records),
        added=tuple(sorted(current.keys() - old.keys())),
        changed=tuple(sorted(p for p in current.keys() & old.keys() if current[p].sha256 != old[p].sha256)),
        removed=removed)


def verify_sources(root: Path, records: tuple[Occurrence, ...]) -> None:
    """Reject revoked access or mutation of frozen members; new paths wait for next ingestion."""
    from .ingest_schema import IngestError
    for record in records:
        if record.sha256 and record.status != "unavailable":
            path = root / record.path
            if not path.is_file() or file_digest(path) != record.sha256:
                raise IngestError(f"frozen source changed/unavailable: {record.path}")
