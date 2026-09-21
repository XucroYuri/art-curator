"""Exact co-occurrence and fail-closed namespace tests."""
from pathlib import Path

import pytest

from artcurator.alias_candidates import Observation, generate, summarize
from artcurator.alias_schema import AliasRecord
from artcurator.character_memory import apply_alias_decisions, load_memory, save_memory
from artcurator.identity_anchor import load_anchors
from artcurator.identity_candidates_v2 import emit
from artcurator.identity_store import save_model
from artcurator.memory_curation import combine, import_memory
from artcurator.memory_schema import Character, Memory
from test_alias_reconciliation import decision_file, seed


def test_summary_when_multiple_crops_share_image() -> None:
    # Given two crops of one image plus independent images.
    rows = [Observation("a", "hero", .6, False), Observation("a", "hero", 1, True),
            Observation("b", "hero", .8, True), Observation("c", "hero", .9, False)]
    # When aggregating; then image maxima, not crop frequency, determine support.
    result = summarize(rows)
    assert result.images == 3
    assert result.top1_images == 2
    assert (result.minimum, result.p25, result.median, result.p75, result.maximum) == pytest.approx((.8, .85, .9, .95, 1))


def test_direct_when_full_image_digest_matches(tmp_path: Path) -> None:
    # Given reference A's content matches the query, while reference B has no WD evidence.
    seed(tmp_path)
    anchors, _ = load_anchors(tmp_path)
    save_model(tmp_path / "anchors.json", anchors.model_copy(update={"anchors": [
        anchors.anchors[0].model_copy(update={"image_sha256": "a" * 64}), anchors.anchors[1]]}))
    # When proposals are generated; then direct support and empty banks are explicit.
    result = generate(tmp_path)
    assert result.banks[0].candidates[0].direct.images == 1
    assert result.banks[0].tagged_reference_images == 1
    assert result.banks[1].candidates == []
    assert result.banks[1].tagged_reference_images == 0


def test_merge_when_decisions_conflict_refuses() -> None:
    # Given opposing human decisions attached to different character entries.
    yes = AliasRecord(wd_tag="hero", decision="confirmed", updated_at="2026-09-21T00:00:00Z")
    no = yes.model_copy(update={"decision": "rejected"})
    left = Character(name="A", aliases=["hero"], alias_decisions=[yes])
    right = Character(name="B", alias_decisions=[no])
    # When merging; then a decision is never silently overwritten.
    with pytest.raises(ValueError, match="conflicting alias"):
        combine(left, right)


def test_import_when_stale_confirmation_conflicts_with_rejection(tmp_path: Path) -> None:
    # Given a rejected pair and a stale confirmed export for the same character.
    seed(tmp_path)
    apply_alias_decisions(tmp_path, decision_file(tmp_path, "rejected"))
    before = load_memory(tmp_path)
    record = before.characters[0].alias_decisions[0].model_copy(update={"decision": "confirmed"})
    incoming = Memory(characters=[Character(name="A", aliases=["hero_tag"], alias_decisions=[record])])
    path = tmp_path / "stale.json"
    save_model(path, incoming)
    # When importing; then rejection and authoritative memory remain intact.
    with pytest.raises(ValueError, match="conflicting alias"):
        import_memory(tmp_path, path)
    assert load_memory(tmp_path) == before


def test_confirmation_when_tag_has_another_owner_refuses(tmp_path: Path) -> None:
    # Given a competing canonical owner.
    seed(tmp_path)
    save_memory(tmp_path, Memory(characters=[Character(name="B", aliases=["hero_tag"])]))
    before = load_memory(tmp_path)
    # When confirming A -> hero_tag; then there is no implicit character merge.
    with pytest.raises(ValueError, match="unique"):
        apply_alias_decisions(tmp_path, decision_file(tmp_path, "confirmed"))
    assert load_memory(tmp_path) == before


def test_confirmation_when_later_rejected_retracts(tmp_path: Path) -> None:
    # Given an explicitly confirmed pair.
    seed(tmp_path)
    apply_alias_decisions(tmp_path, decision_file(tmp_path, "confirmed"))
    # When a human explicitly reverses the decision; then demotion returns.
    apply_alias_decisions(tmp_path, decision_file(tmp_path, "rejected"))
    assert emit(tmp_path).faces[0].model_demoted
    assert load_memory(tmp_path).characters[0].alias_decisions[0].decision == "rejected"


def test_v1_when_read_migrates_without_inventing_decisions(tmp_path: Path) -> None:
    # Given an existing human-curated v1 alias.
    seed(tmp_path)
    save_model(tmp_path / "character-memory.json", Memory(version=1, characters=[Character(name="A", aliases=["hero_tag"])]))
    # When reading; then v2 retains the namespace without fabricated review records.
    memory = load_memory(tmp_path)
    assert memory.version == 2
    assert memory.characters[0].alias_decisions == []
    assert not emit(tmp_path).faces[0].model_demoted


def test_reference_when_alias_crop_names_overlap_preserves_support(tmp_path: Path) -> None:
    # Given one crop labelled by two curated spellings of the same character.
    import numpy as np
    from artcurator.identity_anchor import effective_references
    seed(tmp_path)
    save_memory(tmp_path, Memory(characters=[Character(name="A", aliases=["hero_tag"])]))
    anchors, vectors = load_anchors(tmp_path)
    duplicate = anchors.anchors[0].model_copy(update={"character": "hero_tag"})
    anchors = anchors.model_copy(update={"anchors": [*anchors.anchors, duplicate]})
    # When resolving duplicate crop supervision; then aliases are not false conflicts.
    refs, bank = effective_references(tmp_path, anchors, np.vstack([vectors, vectors[0]]))
    assert set(bank.labels) == {"A", "B"}
    assert len(refs) == 2
