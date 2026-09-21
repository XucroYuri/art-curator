"""identity-alias CLI wiring over the alias-reconciliation tier."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from artcurator.identity_candidates_v2 import emit
from test_alias_reconciliation import decision_file, seed

ROOT = Path(__file__).resolve().parents[1]


def run_cli(command: str, out: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the real command boundary; output stays inside the project write boundary."""
    return subprocess.run([sys.executable, "-m", "artcurator.cli", command, "--out", str(out),
        "--config", str(ROOT / "config.example.yaml"), *arguments],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=180)


def test_alias_when_proposed_via_cli_writes_candidates() -> None:
    # Given saved reference and WD evidence inside the write boundary.
    with tempfile.TemporaryDirectory(dir=ROOT / ".test-tmp") as directory:
        out = Path(directory)
        seed(out)
        # When the CLI proposes aliases.
        result = run_cli("identity-alias", out, "--alias-op", "propose")
        # Then the observable sidecar is published with the ranked pair.
        assert result.returncode == 0, result.stderr
        candidates = json.loads((out / "alias-candidates.json").read_text(encoding="utf-8"))
        assert candidates["banks"][0]["candidates"][0]["wd_tag"] == "hero_tag"


def test_alias_when_confirmed_via_cli_becomes_eligible() -> None:
    # Given a proposal demoted solely by a reference namespace mismatch.
    with tempfile.TemporaryDirectory(dir=ROOT / ".test-tmp") as directory:
        out = Path(directory)
        seed(out)
        assert emit(out).faces[0].model_demoted
        # When a human explicitly applies a confirm decision through the CLI.
        result = run_cli("identity-alias", out, "--alias-op", "apply",
                         "--alias-file", str(decision_file(out, "confirmed")))
        assert result.returncode == 0, result.stderr
        # Then the suggestion resolves without inventing verification.
        face = json.loads((out / "identity-candidates.json").read_text(encoding="utf-8"))["faces"][0]
        assert face["model_demoted"] is False
        assert face["suggested_model"]["name"] == "A"
        assert face["suggested_model"]["verified"] is False
        assert face["suggested_verified"] is None


def test_alias_when_rejected_via_cli_persists() -> None:
    # Given a proposal a human rejects through the CLI.
    with tempfile.TemporaryDirectory(dir=ROOT / ".test-tmp") as directory:
        out = Path(directory)
        seed(out)
        result = run_cli("identity-alias", out, "--alias-op", "apply",
                         "--alias-file", str(decision_file(out, "rejected")))
        assert result.returncode == 0, result.stderr
        # Then rejection is recorded and cannot activate the alias.
        candidates = json.loads((out / "alias-candidates.json").read_text(encoding="utf-8"))
        assert candidates["banks"][0]["candidates"][0]["decision"] == "rejected"
        character = json.loads((out / "character-memory.json").read_text(encoding="utf-8"))["characters"][0]
        assert character["alias_decisions"][0]["decision"] == "rejected"
        assert character["aliases"] == []
        face = json.loads((out / "identity-candidates.json").read_text(encoding="utf-8"))["faces"][0]
        assert face["model_demoted"] is True


@pytest.mark.parametrize("kind", ["invalid-op", "missing-file-arg", "absent-file", "malformed-file"])
def test_alias_when_request_is_invalid_exits_nonzero(kind: str) -> None:
    # Given a corpus directory inside the write boundary.
    with tempfile.TemporaryDirectory(dir=ROOT / ".test-tmp") as directory:
        out = Path(directory)
        seed(out)
        malformed = out / "alias-decisions.json"
        malformed.write_text("{not json", encoding="utf-8")
        arguments = {
            "invalid-op": ("--alias-op", "bogus"),
            "missing-file-arg": ("--alias-op", "apply"),
            "absent-file": ("--alias-op", "apply", "--alias-file", str(out / "missing.json")),
            "malformed-file": ("--alias-op", "apply", "--alias-file", str(malformed)),
        }[kind]
        # When each documented invalid invocation runs; then none silently succeeds.
        result = run_cli("identity-alias", out, *arguments)
        assert result.returncode != 0, f"unexpected success for {arguments}: {result.stdout}"
