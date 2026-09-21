"""Namespace operations with append-only assignment re-attribution."""
from pathlib import Path

from .character_memory import load_memory, save_memory
from .identity_labels import apply_labels, load_registry
from .identity_schema import Label, LabelEnvelope
from .identity_store import load_document, load_provenance, save_model, stage
from .memory_schema import Character, Memory, timestamp


def combine(left: Character, right: Character) -> Character:
    """Union visual support without discarding variant notes or aliases."""
    variants = {v.face_id: v for v in [*left.variant_faces, *right.variant_faces]}
    baseline = sorted(set(left.baseline_faces + right.baseline_faces))
    profile = {key: dict(value) for key, value in left.attribute_profile.items()}
    for key, values in right.attribute_profile.items():
        profile.setdefault(key, {}).update(values)
    return left.model_copy(update={
        "aliases": sorted((set(left.aliases + right.aliases + [right.name])) - {left.name}),
        "baseline_faces": baseline, "variant_faces": [variants[k] for k in sorted(variants) if k not in baseline],
        "assigned_faces": sorted(set(left.assigned_faces + right.assigned_faces)),
        "origin": left.origin if left.origin == right.origin else "mixed", "attribute_profile": profile,
        "updated_at": timestamp()})


def reattribute(out: Path, source: Character, target: str | None) -> None:
    document = load_document(out)
    registry = load_registry(out)
    ids = source.face_ids | {f for f, name in registry.references.items() if name in [source.name, *source.aliases]}
    labels = [Label(face_id=f.face_id, image_sha16=f.image_sha16, character=target,
                    action="confirm" if target else "ignore") for f in document.faces if f.face_id in ids]
    envelope = LabelEnvelope(version=1, source="review-studio", corpus_fingerprint=registry.corpus_fingerprint,
                             labels=labels)
    path = out / "memory-reattribution-labels.json"
    save_model(path, envelope)
    apply_labels(out, path)


def curate(out: Path, operation: str, name: str, target: str = "") -> Memory:
    """Rename/merge/delete without rewriting history; output lock excludes other coordinators."""
    with stage(out, "character-memory-" + operation):
        memory = load_memory(out)
        chars = {char.name: char for char in memory.characters}
        source = chars[name]
        match operation:
            case "rename":
                if target in chars or not target.strip():
                    raise ValueError("rename target must be a new nonempty name")
                changed = source.model_copy(update={"name": target.strip(),
                    "aliases": sorted(set([*source.aliases, source.name]) - {target.strip()}), "updated_at": timestamp()})
                chars.pop(name)
                chars[changed.name] = changed
            case "merge":
                if target == name:
                    raise ValueError("merge requires distinct characters")
                chars[target] = combine(chars[target], source)
                chars.pop(name)
            case "delete":
                chars.pop(name)
            case _:
                raise ValueError("unknown memory operation")
        result = Memory.model_validate({"characters": [c.model_dump() for c in sorted(chars.values(), key=lambda c: c.name)]})
        # Validate the complete new namespace before appending assignment events.
        reattribute(out, source, None if operation == "delete" else target.strip())
        save_memory(out, result)
        from .identity_candidates_v2 import emit
        emit(out)
        return result


def export_memory(out: Path, path: Path) -> None:
    """Export content-bound references; saved embeddings are deliberately not duplicated."""
    provenance = load_provenance(out)
    memory = load_memory(out).model_copy(update={"corpus_fingerprint": provenance.corpus_fingerprint,
                                              "semantic_profile": provenance.semantic_profile})
    save_model(path, memory)


def import_memory(out: Path, path: Path) -> Memory:
    """Merge a same-corpus export; reject conflicting face owners before any write."""
    incoming = Memory.model_validate_json(path.read_bytes())
    provenance = load_provenance(out)
    extras = incoming.model_extra or {}
    if (extras.get("corpus_fingerprint", provenance.corpus_fingerprint) != provenance.corpus_fingerprint
            or extras.get("semantic_profile", provenance.semantic_profile) != provenance.semantic_profile):
        raise ValueError("memory import corpus/profile mismatch")
    if any(not char.face_ids <= set(provenance.crops) for char in incoming.characters):
        raise ValueError("import has unresolved face references; embeddings are corpus-local")
    with stage(out, "character-memory-import"):
        chars = {char.name: char for char in load_memory(out).characters}
        for char in incoming.characters:
            chars[char.name] = combine(chars[char.name], char) if char.name in chars else char
        result = Memory(characters=sorted(chars.values(), key=lambda c: c.name))
        for char in incoming.characters:
            reattribute(out, char, char.name)
        save_memory(out, result)
        from .identity_candidates_v2 import emit
        emit(out)
        return result
