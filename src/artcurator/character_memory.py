"""Local memory persistence and label synchronization; no image writes."""
from pathlib import Path

from .identity_schema import Label
from .identity_store import load_provenance, save_model
from .memory_schema import Character, Memory, Variant, timestamp


def load_memory(out: Path) -> Memory:
    path = out / "character-memory.json"
    return Memory.model_validate_json(path.read_bytes()).model_copy(update={"version": 2}) if path.exists() else Memory()


def save_memory(out: Path, memory: Memory) -> None:
    validated = Memory.model_validate(memory.model_dump()).model_copy(update={"version": 2})
    valid = set(load_provenance(out).crops)
    if any(not char.face_ids <= valid for char in validated.characters):
        raise ValueError("memory contains faces outside this corpus")
    save_model(out / "character-memory.json", validated)


def remember(memory: Memory, label: Label, model_names: set[str]) -> Memory:
    """Reattribution removes old visual support; an absent mark preserves an existing mark."""
    target = next((c for c in memory.characters if label.character in [c.name, *c.aliases]), None)
    name = target.name if target else (label.character or "").strip()
    chars: list[Character] = []
    for char in memory.characters:
        if char.name == name and label.action in {"confirm", "new"}:
            chars.append(char)
            continue
        chars.append(char.model_copy(update={
            "assigned_faces": [f for f in char.assigned_faces if f != label.face_id],
            "baseline_faces": [f for f in char.baseline_faces if f != label.face_id],
            "variant_faces": [v for v in char.variant_faces if v.face_id != label.face_id],
            "updated_at": timestamp() if label.face_id in char.face_ids else char.updated_at}))
    if label.action in {"confirm", "new"}:
        char = target or Character(name=name, origin="mixed" if name in model_names else "user")
        baseline = char.baseline_faces.copy()
        variants = char.variant_faces.copy()
        if label.mark is not None:
            baseline = [f for f in baseline if f != label.face_id]
            variants = [v for v in variants if v.face_id != label.face_id]
            if label.mark == "baseline":
                baseline.append(label.face_id)
            else:
                variants.append(Variant(face_id=label.face_id))
        updated = char.model_copy(update={"baseline_faces": sorted(set(baseline)), "variant_faces": variants,
            "assigned_faces": sorted(set([*char.assigned_faces, label.face_id])), "updated_at": timestamp(),
            "origin": "mixed" if char.origin == "model" or name in model_names else char.origin})
        chars = [c for c in chars if c.name != name] + [updated]
    return Memory(characters=sorted(chars, key=lambda c: c.name))


def sync_labels(out: Path, labels: list[Label]) -> None:
    from .wd_schema import TagDocument
    memory = load_memory(out)
    if not (out / "character-memory.json").exists():
        from .identity_labels import load_registry
        labels = [event.label for event in load_registry(out).events]
    wd_path = out / "wd-tagger.json"
    wd = TagDocument.model_validate_json(wd_path.read_bytes()) if wd_path.exists() else None
    names: set[str] = {tag.tag for face in wd.faces for tag in face.evidence.characters} if wd else set()
    for label in labels:
        memory = remember(memory, label, names)
    if wd:
        attributes = {face.face_id: face.evidence.attributes for face in wd.faces}
        updated: list[Character] = []
        for char in memory.characters:
            colors: dict[str, float] = {}
            observed = [attributes[f].hair_color for f in char.face_ids if f in attributes and attributes[f].hair_color]
            for color in observed:
                if color is not None:
                    colors[color] = colors.get(color, 0) + 1 / len(observed)
            updated.append(char.model_copy(update={"attribute_profile": {"hair_color": colors} if colors else {}}))
        memory = Memory(characters=updated)
    save_memory(out, memory)


def curate(out: Path, operation: str, name: str, target: str = "") -> Memory:
    """Public curation facade; the service also updates assignment journals."""
    from .memory_curation import curate as execute
    return execute(out, operation, name, target)


def apply_alias_decisions(out: Path, path: Path) -> Memory:
    """Apply an explicit studio alias envelope under the identity stage lock."""
    from .alias_reconciliation import apply_decisions
    return apply_decisions(out, path)
