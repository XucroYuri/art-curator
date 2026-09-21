"""Alias evidence crosses the compressed single-file boundary intact."""
import base64
import gzip
import json
from pathlib import Path

from tools import build_gallery


def test_aliases_when_gallery_embeds_sidecar(tmp_path: Path) -> None:
    # Given a synthetic bound proposal, including a rejected pair.
    proposal = {"version": 1, "corpus_fingerprint": "c" * 64, "semantic_profile": "d" * 64,
                "banks": [{"reference_name": "人物甲", "candidates": [{"wd_tag": "hero_tag", "decision": "rejected"}]}]}
    (tmp_path / "identities.json").write_text(json.dumps({"faces": []}), encoding="utf-8")
    (tmp_path / "alias-candidates.json").write_text(json.dumps(proposal), encoding="utf-8")
    # When encoding a gallery; then no evidence or rejected state is lost.
    encoded, _ = build_gallery.encode_payload(build_gallery.build_payload(tmp_path, []))
    decoded = json.loads(gzip.decompress(base64.b64decode(encoded)))
    assert decoded["y"]["alias_reconciliation"] == proposal
