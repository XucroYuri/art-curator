"""Validated scan microbatch commits and current-manifest assembly."""
import shutil
from pathlib import Path

from . import db
from .identity_store import atomic_bytes, digest, file_digest, save_model
from .ingest_adapters import Rows
from .ingest_schema import Artifact, Frozen, IngestError, Inventory
from .ingest_storage import valid


class Content(Frozen):
    sha256: str
    profile: str
    row: db.Row | None
    payload_digest: str
    artifacts: tuple[Artifact, ...]
    reason: str = ""


def scan_profile() -> str:
    return digest("".join(file_digest(Path(__file__).with_name(name + ".py"))
                          for name in ("scan", "previews")).encode())


def lookup(root: Path, content: str) -> Content | None:
    path = root / "content" / (content + ".json")
    if not path.exists():
        return None
    record = Content.model_validate_json(path.read_bytes())
    if record.profile != scan_profile():
        return None
    payload = record.row.model_dump_json() if record.row else "decode-failed"
    if record.payload_digest != digest(payload.encode()):
        raise IngestError("scan row payload digest mismatch")
    if record.sha256 != content or not valid(root, record.artifacts):
        raise IngestError("scan commit corrupted; preserve evidence and repair explicitly")
    return record


def publish(root: Path, inventory: Inventory, batch: tuple[Artifact, ...]) -> None:
    rows_path = next(root / a.path for a in batch if a.path.endswith("/rows.json"))
    document = Rows.model_validate_json(rows_path.read_bytes())
    rows = {r.sha256: r for r in document.rows}
    (root / "content").mkdir(exist_ok=True)
    for occurrence in inventory.occurrences:
        sha = occurrence.sha256
        if occurrence.status == "unavailable" or not sha:
            continue
        row = rows.get(sha)
        # Only publish contents in this microbatch, including decode failures.
        if sha in document.contents:
            relevant = tuple(a for a in batch if a.path.endswith(("/rows.json", "/scan-rejected.json", f"/{sha}.jpg")))
            payload = row.model_dump_json() if row else "decode-failed"
            save_model(root / "content" / (sha + ".json"), Content(sha256=sha, profile=scan_profile(), row=row,
                       payload_digest=digest(payload.encode()), artifacts=relevant,
                       reason="" if row else "decode/thumbnail failed; see scan-rejected.json"))


def assemble(root: Path, inventory: Inventory, source: Path) -> None:
    out = root / "revisions" / inventory.revision
    rows: list[db.Row] = []
    seen: set[str] = set()
    for occurrence in inventory.occurrences:
        sha = occurrence.sha256
        if not sha or sha in seen or occurrence.status == "unavailable":
            continue
        seen.add(sha)
        content = lookup(root, sha)
        if content is None or content.row is None:
            continue
        row = content.row.model_copy(update={"abs_path": str(source / occurrence.path),
            "path_rel": occurrence.path, "filename": Path(occurrence.path).name})
        rows.append(row)
        for directory in ("thumbs", "previews"):
            suffix = f"/{directory}/{sha}.jpg"
            entry = next((a for a in content.artifacts if a.path.endswith(suffix)), None)
            if entry:
                target = out / directory / (sha + ".jpg")
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(root / entry.path, target)
    db.save_rows(out, sorted(rows, key=lambda r: r.sha256))
    atomic_bytes(out / "manifest-order.sha256", digest("\n".join(r.sha256 for r in sorted(rows, key=lambda r: r.sha256)).encode()).encode())
