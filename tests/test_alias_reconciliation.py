"""ALIAS-SYN-v1: human decisions, not model accuracy labels."""
import json
from pathlib import Path

import pytest

from artcurator import character_memory
from artcurator.identity_candidates_v2 import emit
from artcurator.identity_store import save_model
from artcurator.memory_curation import curate, export_memory, import_memory
from artcurator.memory_schema import Character, Memory
from artcurator.wd_schema import Evidence, Handshake, Tag, TagDocument, TaggedFace
from test_identity_grouping_exports import fixture


def seed(out: Path) -> None:
    fixture(out)
    save_model(out / "wd-tagger.json", TagDocument(
        handshake=Handshake(build="a" * 64, model_sha256="b" * 64, tags_sha256="c" * 64, packages={}),
        corpus_fingerprint="c" * 64, faces=[TaggedFace(face_id="f_00000001", image_sha16="a" * 16,
            crop_sha256="1" * 64, evidence=Evidence(characters=[Tag(tag="hero_tag", score=.99)]))]))


def decision_file(out: Path, decision: str) -> Path:
    path = out / "alias-decisions.json"
    path.write_text(json.dumps({"version": 1, "source": "review-studio",
        "corpus_fingerprint": "c" * 64, "semantic_profile": "d" * 64,
        "decisions": [{"reference_name": "A", "wd_tag": "hero_tag", "decision": decision}]}), encoding="utf-8")
    return path


def test_pair_when_confirmed_becomes_eligible(tmp_path: Path) -> None:
    # Given a proposal demoted solely by a reference namespace mismatch.
    seed(tmp_path)
    assert emit(tmp_path).faces[0].model_demoted
    # When a human explicitly confirms the proposed alias.
    character_memory.apply_alias_decisions(tmp_path, decision_file(tmp_path, "confirmed"))
    # Then the actual producer resolves both names, without inventing verification.
    face = emit(tmp_path).faces[0]
    assert not face.model_demoted
    assert face.suggested_model.name == "A"
    assert face.suggested_model.verified is False
    assert face.suggested_verified is None


def test_pair_when_unconfirmed_stays_demoted(tmp_path: Path) -> None:
    # Given saved evidence but no human decision.
    seed(tmp_path)
    # When proposals and suggestions are emitted.
    face = emit(tmp_path).faces[0]
    proposals = json.loads((tmp_path / "alias-candidates.json").read_text(encoding="utf-8"))
    # Then a weak cohort proposal exists but never promotes or creates memory.
    pair = proposals["banks"][0]["candidates"][0]
    assert pair["wd_tag"] == "hero_tag"
    assert pair["cohort"]["images"] == 1
    assert pair["direct"]["images"] == 0
    assert pair["strength"] == "weak"
    assert face.model_demoted
    assert face.disagreements[0].reason == "reference-namespace-unresolved"
    assert character_memory.load_memory(tmp_path).characters == []


def test_pair_when_rejected_persists_across_runs(tmp_path: Path) -> None:
    # Given a proposed pair explicitly rejected by a human.
    seed(tmp_path)
    emit(tmp_path)
    character_memory.apply_alias_decisions(tmp_path, decision_file(tmp_path, "rejected"))
    # When regenerating from disk, including label synchronization.
    character_memory.sync_labels(tmp_path, [])
    face = emit(tmp_path).faces[0]
    proposals = json.loads((tmp_path / "alias-candidates.json").read_text(encoding="utf-8"))
    # Then rejection survives and cannot activate an alias.
    assert proposals["banks"][0]["candidates"][0]["decision"] == "rejected"
    assert character_memory.load_memory(tmp_path).characters[0].aliases == []
    assert face.model_demoted


@pytest.mark.parametrize("decision", ["confirmed", "rejected"])
def test_decision_when_export_import_round_trips(tmp_path: Path, decision: str) -> None:
    # Given persisted alias decisions.
    seed(tmp_path)
    character_memory.apply_alias_decisions(tmp_path, decision_file(tmp_path, decision))
    path = tmp_path / "export.json"
    export_memory(tmp_path, path)
    before = character_memory.load_memory(tmp_path)
    # When importing the exported memory.
    result = import_memory(tmp_path, path)
    # Then versioned decision records and aliases round-trip exactly.
    assert result.version == 2
    assert result.characters[0].alias_decisions == before.characters[0].alias_decisions
    assert result.characters[0].aliases == before.characters[0].aliases


def test_no_alias_when_other_character_conflicts_stays_demoted(tmp_path: Path) -> None:
    # Given a known canonical reference with a different WD alias.
    seed(tmp_path)
    character_memory.save_memory(tmp_path, Memory(characters=[Character(name="A", aliases=["other_tag"])]))
    # When the unchanged WD gate passes hero_tag.
    face = emit(tmp_path).faces[0]
    # Then known contradictory identity evidence still demotes.
    assert face.model_demoted
    assert face.disagreements[0].reason == "visual-evidence-disagrees"


def test_decision_when_renamed_merged_deleted(tmp_path: Path) -> None:
    # Given a confirmed name-only alias.
    seed(tmp_path)
    character_memory.apply_alias_decisions(tmp_path, decision_file(tmp_path, "confirmed"))
    curate(tmp_path, "rename", "A", "renamed")
    memory = character_memory.load_memory(tmp_path)
    character_memory.save_memory(tmp_path, Memory(characters=[*memory.characters, Character(name="target")]))
    # When merging the renamed character, then its decision and old names survive.
    merged = curate(tmp_path, "merge", "renamed", "target")
    assert merged.characters[0].alias_decisions[0].decision == "confirmed"
    assert {"A", "renamed", "hero_tag"} <= set(merged.characters[0].aliases)


def test_decision_when_deleted_retracts_alias(tmp_path: Path) -> None:
    # Given a confirmed name-only alias.
    seed(tmp_path)
    character_memory.apply_alias_decisions(tmp_path, decision_file(tmp_path, "confirmed"))
    # When deleting its character.
    curate(tmp_path, "delete", "A")
    # Then alias activation is removed and the raw model proposal demotes again.
    assert character_memory.load_memory(tmp_path).characters == []
    assert emit(tmp_path).faces[0].model_demoted


def test_batch_when_foreign_refused_without_write(tmp_path: Path) -> None:
    # Given an otherwise valid batch bound to another corpus.
    seed(tmp_path)
    emit(tmp_path)
    before = (tmp_path / "character-memory.json").read_bytes()
    path = decision_file(tmp_path, "confirmed")
    path.write_text(path.read_text().replace("c" * 64, "e" * 64))
    # When applying; then the entire batch fails before mutation.
    with pytest.raises(ValueError, match="corpus/profile"):
        character_memory.apply_alias_decisions(tmp_path, path)
    assert (tmp_path / "character-memory.json").read_bytes() == before
