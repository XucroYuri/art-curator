# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pydantic>=2"]
# ///
# How to run (project installed in the existing environment):
# uv run --no-project --python .venv/Scripts/python.exe python tools/alias_receipt.py OUT_PILOT OUT_REVIEW OUT_SIMILARITY
"""Regenerate saved-evidence galleries without confirming any real aliases."""
from __future__ import annotations

import sys
from pathlib import Path

from artcurator.alias_candidates import generate
from artcurator.candidates_schema_v2 import CandidateDocumentV2
from artcurator.character_memory import load_memory
from artcurator.identity_candidates_v2 import emit
from artcurator.identity_schema import Record
from artcurator.identity_store import file_digest, save_model
from build_gallery import build_gallery_with_metrics


class Counts(Record):
    demoted: int
    eligible: int
    proposals: int
    confusable: int


def counts(document: CandidateDocumentV2) -> Counts:
    return Counts(demoted=sum(face.model_demoted for face in document.faces),
        eligible=sum(face.suggested_model is not None and not face.model_demoted for face in document.faces),
        proposals=sum(face.suggested_model is not None for face in document.faces),
        confusable=sum(face.suggested_model is not None and face.suggested_model.name == "2b_(nier:automata)"
                       for face in document.faces))


class Receipt(Record):
    corpus: str
    before: Counts
    after: Counts
    alias_proposals: int
    banks: int
    direct_supported_pairs: int
    relatively_strong_pairs: int
    confirmed_aliases: int
    gallery_rows: int
    input_digests: dict[str, str]
    gallery_sha256: str


class Bundle(Record):
    method: str = "Saved evidence only; no human confirmations, no accuracy estimate"
    receipts: list[Receipt]


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Provide three output directories in pilot/review/similarity order")
    receipts: list[Receipt] = []
    for label, argument, expected in zip(("pilot", "review", "similarity"), sys.argv[1:], (1013, 2885, 267), strict=True):
        out = Path(argument)
        before = counts(CandidateDocumentV2.model_validate_json((out / "identity-candidates.json").read_bytes()))
        if (before.demoted, before.eligible) != (expected, 0):
            raise SystemExit(f"{label}: baseline differs: {before}")
        after = counts(emit(out))
        aliases = generate(out)
        pairs = [pair for bank in aliases.banks for pair in bank.candidates]
        built = build_gallery_with_metrics(out)
        receipt = Receipt(corpus=label, before=before, after=after, alias_proposals=len(pairs), banks=len(aliases.banks),
            direct_supported_pairs=sum(pair.direct.images > 0 for pair in pairs),
            relatively_strong_pairs=sum(pair.strength == "relatively-strong" for pair in pairs),
            confirmed_aliases=sum(record.decision == "confirmed" for char in load_memory(out).characters
                                  for record in char.alias_decisions),
            gallery_rows=built.rows, input_digests=aliases.input_digests, gallery_sha256=file_digest(built.path))
        save_model(out / "alias-reconciliation-report.json", receipt)
        receipts.append(receipt)
        print(receipt.model_dump_json())
    save_model(Path("specs/evidence/alias-reconciliation.json"), Bundle(receipts=receipts))


if __name__ == "__main__":
    main()
