# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = []
# ///
# Run: uv run --no-project --python .venv/Scripts/python.exe python tools/check_identity_grouping.py
"""Run the full regression gate once and retain scoped grouping evidence."""
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "out/identity-grouping-evidence"
    out.mkdir(parents=True, exist_ok=True)
    junit = out / "pytest.xml"
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={junit}"], cwd=root, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    subprocess.run(["uv", "build", "--wheel", "--out-dir", "dist"], cwd=root, check=True)
    suites = ET.parse(junit).getroot()
    cases = list(suites.iter("testcase"))
    sources = [*root.glob("src/artcurator/identity_anchor*.py"),
               *root.glob("src/artcurator/identity_group*.py"),
               *root.glob("tests/test_identity_grouping*.py")]
    source_digests = {path.relative_to(root).as_posix(): sha(path) for path in sources}
    line_counts = {path.relative_to(root).as_posix(): sum(bool(line.strip()) and not line.lstrip().startswith("#")
                   for line in path.read_text(encoding="utf-8").splitlines()) for path in sources}
    if any(count > 250 for count in line_counts.values()):
        raise SystemExit("grouping source exceeds 250 pure LOC")
    requirements = {
        "AC-FR-GROUP-001-01": "sampling",
        "AC-FR-GROUP-002-01": "assignment",
        "AC-FR-GROUP-003-01": "export",
        "AC-FR-GROUP-004-01": "confirmation",
        "AC-NFR-GROUP-001-01": "visual_input",
        "AC-NFR-GROUP-002-01": "integrity",
    }
    for criterion, match in requirements.items():
        receipt = {"criterion": criterion, "status": "synthetic-regression-pass",
                   "fixture": "GROUP-SYN-v1", "fixture_source_sha256": source_digests,
                   "junit_sha256": sha(junit), "full_suite_passed": len(cases),
                   "matching_tests": [case.attrib["name"] for case in cases if match in case.attrib["name"]],
                   "pure_line_counts": line_counts, "wheel_build": "passed",
                   "limitations": ["No held-out accuracy qualification", "LSP unavailable: installation previously declined",
                                   "Global quality gates not certified", "Real timings retained in per-output receipts"]}
        (out / f"{criterion}.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"passed": len(cases), "build": "passed", "pure_line_counts": line_counts}, indent=2))


if __name__ == "__main__":
    main()
