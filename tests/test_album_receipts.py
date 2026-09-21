import json
import subprocess
import sys
from pathlib import Path


def test_receipt_refuses_pass_claim_when_suite_failed(tmp_path: Path) -> None:
    # Given an explicit failed pytest report.
    report = tmp_path / "result.xml"
    report.write_text('<testsuites><testsuite tests="2" failures="1" errors="0" skipped="0" time="1"/></testsuites>')
    # When generating receipts, then neither the run nor any AC is certified pass.
    result = subprocess.run([sys.executable, "tools/album_mapping_evidence.py", str(report),
        "--destination", str(tmp_path)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    receipt = json.loads((tmp_path / "album-mapping-run.json").read_text())
    assert receipt["pytest"]["failures"] == 1
    assert not receipt["g5_graduated"]
    assert json.loads((tmp_path / "AC-FR-ALBUM-MAP-001-01.json").read_text())["verdict"] == "inconclusive"
