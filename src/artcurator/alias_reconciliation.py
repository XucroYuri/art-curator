"""Human-only namespace mutation. Proposals themselves are read-only evidence."""
from pathlib import Path
from typing import assert_never

from .alias_schema import AliasEnvelope, AliasError, AliasRecord
from .character_memory import load_memory, save_memory
from .identity_store import load_provenance, stage
from .memory_schema import Character, Memory, timestamp


def apply_decisions(out: Path, path: Path) -> Memory:
    """Validate the whole batch, persist aliases, then regenerate unverified advice."""
    from .alias_candidates import generate
    from .identity_candidates_v2 import emit

    envelope = AliasEnvelope.model_validate_json(path.read_bytes())
    with stage(out, "alias-reconciliation"):
        provenance = load_provenance(out)
        if (envelope.corpus_fingerprint, envelope.semantic_profile) != (
                provenance.corpus_fingerprint, provenance.semantic_profile):
            raise AliasError("alias decisions corpus/profile mismatch")
        proposed = generate(out)
        pairs = {(bank.reference_name, row.wd_tag) for bank in proposed.banks for row in bank.candidates}
        choices = [(choice.reference_name, choice.wd_tag) for choice in envelope.decisions]
        if len(choices) != len(set(choices)) or not set(choices) <= pairs:
            raise AliasError("alias batch contains duplicate or unobserved pairs")
        memory = load_memory(out)
        for choice in envelope.decisions:
            owner = next((char for char in memory.characters
                          if choice.reference_name in [char.name, *char.aliases]), None)
            char = owner or Character(name=choice.reference_name)
            aliases = set(char.aliases)
            match choice.decision:
                case "confirmed":
                    aliases.add(choice.wd_tag)
                case "rejected":
                    if choice.wd_tag == char.name:
                        raise AliasError("cannot reject the canonical name itself")
                    aliases.discard(choice.wd_tag)
                case unreachable:
                    assert_never(unreachable)
            record = AliasRecord(wd_tag=choice.wd_tag, decision=choice.decision, updated_at=timestamp())
            updated = char.model_copy(update={"aliases": sorted(aliases - {char.name}),
                "alias_decisions": [r for r in char.alias_decisions if r.wd_tag != choice.wd_tag] + [record],
                "updated_at": record.updated_at})
            memory = Memory(characters=[c for c in memory.characters if c.name != char.name] + [updated])
        save_memory(out, memory)
        emit(out)
        return memory
