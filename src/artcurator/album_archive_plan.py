"""Read-only deterministic selection and filesystem conflict classification."""
from collections import Counter
from pathlib import Path
import shutil
import stat

from ._moves import MoveError, confined, safe_path, sha256
from .album_archive_schema import (
    CONFLICTS, NAMESPACES, ArchivePlan, ArchiveRequest, Conflict, Item, Selection, Stamp, Summary,
)
from .album_map_protocol import Snapshot
from .album_map_schema import DecisionFields, MappingError


def existing_parent(path: Path) -> Path:
    return next(p for p in (path, *path.parents) if p.exists())


def same_volume(source: Path, target: Path) -> bool:
    return existing_parent(source).stat().st_dev == existing_parent(target).stat().st_dev


def free_bytes(target: Path) -> int:
    return shutil.disk_usage(existing_parent(target)).free


def case_hazard(path: Path) -> bool:
    """Compare actual directory spellings even on a case-sensitive test filesystem."""
    for part in (path, *path.parents):
        if part.parent != part and part.parent.is_dir():
            if any(p.name.casefold() == part.name.casefold() and p.name != part.name
                   for p in part.parent.iterdir()):
                return True
    return False


def eligible(decision: DecisionFields) -> bool:
    return (decision.verified and decision.source == "human" and
            decision.disposition in {"assigned", "original-design", "ordinary", "non-character"})


def classify(item: Item) -> Item:
    """Accumulate overlapping classes; never suffix, deduplicate or overwrite."""
    conflicts: list[Conflict] = []
    stamp = None
    try:
        safe_path(item.src)
        safe_path(item.dst)
        if any(len(str(p).encode("utf-16-le")) // 2 >= 260 for p in (item.src, item.dst)):
            conflicts.append("path_length")
        if any(p.is_reserved() or p.name.endswith((".", " ")) for p in (item.dst, *item.dst.parents)):
            conflicts.append("unsafe_path")
        if case_hazard(item.src) or case_hazard(item.dst):
            conflicts.append("case_hazard")
        if not same_volume(item.src, item.dst):
            conflicts.append("cross_volume")
        if not item.src.is_file():
            conflicts.append("missing")
        else:
            stamp = Stamp.capture(item.src)
            if sha256(item.src) != item.sha256:
                conflicts.append("changed_source")
            if not item.src.stat().st_mode & stat.S_IWRITE:
                conflicts.append("unreadable")
        if item.src == item.dst:
            conflicts.append("already_correct")
        elif item.dst.exists():
            conflicts.append("name_collision")
            if not item.dst.is_file() or sha256(item.dst) != item.sha256:
                conflicts.append("different_target")
    except OSError:
        conflicts.append("unreadable")
    except MoveError:
        conflicts.append("unsafe_path")
    return item.model_copy(update={"stamp": stamp, "conflicts": tuple(sorted(set(conflicts)))})


def layout(snapshot: Snapshot, request: ArchiveRequest) -> ArchivePlan:
    """Only a published root supplies authority; default excludes uncertain/multi-member rows."""
    if not snapshot.history or snapshot.root.revision != snapshot.history[-1].revision:
        raise MappingError("archive-committed-revision-required")
    for root in (request.source_root, request.export_root, request.ledger_root):
        safe_path(root)
    if any(request.ledger_root.is_relative_to(p) or p.is_relative_to(request.ledger_root)
           for p in (request.source_root, request.export_root)):
        raise MappingError("archive-ledger-must-be-separate")
    selected = {(s.image_id, s.occurrence_id): s for s in request.selections}
    if len(selected) != len(request.selections):
        raise MappingError("archive-one-destination-per-occurrence")
    seen: set[tuple[str, str]] = set()
    items: list[Item] = []
    excluded: list[str] = []
    for record in sorted(snapshot.records, key=lambda r: r.image_id):
        relations = (*record.relations, *(r for s in record.subjects for r in s.relations))
        for occurrence in sorted(record.occurrences, key=lambda o: o.occurrence_id):
            key = (record.image_id, occurrence.occurrence_id)
            choice = selected.get(key)
            if request.selections and choice is None:
                excluded.append(f"{occurrence.occurrence_id}:not-selected")
                continue
            candidates = [r for r in relations if (r.relation_id == choice.relation_id if choice else eligible(r))]
            if len(candidates) != 1:
                if choice:
                    raise MappingError("archive-selected-relation-missing")
                excluded.append(f"{occurrence.occurrence_id}:ambiguous-or-unverified")
                continue
            relation = candidates[0]
            owner = next((s for s in record.subjects if s.subject_id == relation.subject_id), record)
            reviewed = choice is not None and choice.reviewed_inclusion
            if not reviewed and not all(eligible(d) for d in (record, owner, relation)):
                excluded.append(f"{occurrence.occurrence_id}:reviewed-inclusion-required")
                seen.add(key)
                continue
            entity = relation.entity_id
            if (entity in {".", ".."} or any(c in entity for c in '/\\:<>"|?*')
                    or entity.endswith((".", " "))):
                raise MappingError("archive-entity-id-not-folder-safe")
            target = NAMESPACES[relation.entity_type] + "/" + entity
            source = confined(Path(occurrence.locator), request.source_root)
            destination = confined(request.export_root / target / source.name, request.export_root)
            selection = choice or Selection(image_id=record.image_id, occurrence_id=occurrence.occurrence_id,
                                            relation_id=relation.relation_id)
            items.append(classify(Item(selection=selection, src=source, dst=destination, target=target,
                                       sha256=record.image_id, stamp=None)))
            seen.add(key)
    if set(selected) - seen:
        raise MappingError("archive-selected-occurrence-missing")
    targets = Counter(str(i.dst).casefold() for i in items)
    sources = Counter(str(i.src).casefold() for i in items)
    spellings: dict[str, set[str]] = {}
    for item in items:
        for path in (item.dst, *item.dst.parents):
            spellings.setdefault(str(path).casefold(), set()).add(str(path))
    needed = sum(i.stamp.size for i in items if i.stamp and not i.conflicts)
    capacity = free_bytes(request.export_root) < needed
    resolved = []
    for item in items:
        conflicts = set(item.conflicts)
        if any(len(spellings[str(p).casefold()]) > 1 for p in (item.dst, *item.dst.parents)):
            conflicts.add("case_hazard")
        if targets[str(item.dst).casefold()] > 1 or sources[str(item.src).casefold()] > 1:
            conflicts.add("name_collision")
        if capacity:
            conflicts.add("capacity")
        resolved.append(item.model_copy(update={"conflicts": tuple(sorted(conflicts))}))
    summary = Summary(targets=dict(Counter(i.target for i in resolved)),
        conflicts={c: sum(c in i.conflicts for i in resolved) for c in CONFLICTS},
        ready=sum(not i.conflicts for i in resolved), excluded=tuple(excluded), required_bytes=needed)
    plan = ArchivePlan(request=request, mapping=snapshot.root, snapshot_digest=snapshot.fingerprint(),
                       items=tuple(resolved), summary=summary)
    return plan.model_copy(update={"digest": plan.fingerprint()})
