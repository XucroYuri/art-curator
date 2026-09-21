"""Negotiation is copied intact and never applied by the offline builder."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import build_gallery
from artcurator.negotiation_consent import Decision

FIXTURE = Path(__file__).parent / "fixtures" / "negotiation-report.example.json"


def test_report_when_embedded_keeps_copy_and_bindings(tmp_path: Path) -> None:
    # Given the authoritative report, with no image ledger required.
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    (tmp_path / "negotiation-report.json").write_text(json.dumps(report), encoding="utf-8")
    # When the existing payload boundary encodes negotiation.
    payload = build_gallery.build_payload(tmp_path, (), ())
    compact = build_gallery.compact_payload(payload)
    # Then no copy, digest, missing value or evidence is rewritten.
    assert payload["negotiation"] == report
    assert compact["ng"] == report


def test_report_when_absent_remains_explicitly_unavailable(tmp_path: Path) -> None:
    # Given an image-only directory; when building; then no report is invented.
    payload = build_gallery.build_payload(tmp_path, (), ())
    assert payload["negotiation"] is None
    assert build_gallery.compact_payload(payload)["ng"] is None


@pytest.mark.parametrize("content", ["{", "[]", '{"schema_version":"future"}'])
def test_report_when_invalid_fails_build_closed(tmp_path: Path, content: str) -> None:
    # Given a malformed/unsupported report; when building; then refuse silently hiding it.
    (tmp_path / "negotiation-report.json").write_text(content, encoding="utf-8")
    with pytest.raises(build_gallery.GalleryInputError):
        build_gallery.build_payload(tmp_path, (), ())


def test_representatives_when_external_or_missing_are_not_embedded(tmp_path: Path) -> None:
    # Given hostile and missing refs; when embedding; then no URL is fetched or fabricated.
    report = {"clusters": [{"representatives": [
        {"image_ref": "https://example.invalid/a.png", "crop_ref": "../outside.png"},
        {"image_ref": "missing.png", "crop_ref": None},
    ]}]}
    assert build_gallery.negotiation_assets(tmp_path, report) == {}


def test_copy_when_embedded_is_data_not_module_literals() -> None:
    # Given the normative data and authored modules.
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    modules = Path(__file__).parents[1] / "tools"
    source = "\n".join((modules / name).read_text(encoding="utf-8") for name in (
        "gallery_negotiation.js", "gallery_negotiation_report.js"))
    # When inspecting literal ownership; then the contract is not duplicated into JS.
    for text in report["presentation"]["text"].values():
        assert text not in source


@pytest.mark.parametrize("name", ["gallery_negotiation.js", "gallery_negotiation_report.js"])
def test_module_when_parsed_has_valid_javascript(name: str) -> None:
    # Given an injected module; when parsed by Node; then syntax is valid without DOM execution.
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable; browser QA also parses the module")
    result = subprocess.run([node, "--check", str(Path(__file__).parents[1] / "tools" / name)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("mode", ["human-first", "auto-first", "inherit-only"])
@pytest.mark.parametrize("scope", ["all", "selected", "none"])
def test_browser_export_when_consumed_matches_exact_decision(mode: str, scope: str) -> None:
    # Given a real-browser download and its frozen synthetic input (never apply).
    root = Path(__file__).parents[1]
    report = json.loads((root / "tests/fixtures/gallery/negotiation-report.json").read_text(encoding="utf-8"))
    path = root / "docs/assets/negotiation" / f"decision-{mode}-{scope}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    # When parsing with the CLI's strict wire model, not a reimplementation.
    decision = Decision.model_validate(raw)
    # Then fields and scope are exact and carry the input's limitations and bindings.
    assert set(raw) == set(Decision.model_fields)
    assert decision.mode == mode and decision.inheritance == scope
    assert decision.affirmative is True
    assert decision.report_digest == report["report_digest"]
    assert decision.snapshot_digest == report["snapshot_digest"]
    assert decision.profile_digest == report["profile_digest"]
    assert list(decision.acknowledged) == report["limitations"]
    expected = report["folders"] if scope == "all" else report["folders"][:1] if scope == "selected" else []
    assert [folder.folder_id for folder in decision.folders] == [folder["folder_id"] for folder in expected]
    assert decision.threshold_overrides == ()


def test_browser_exports_when_repeated_get_fresh_operation_ids() -> None:
    # Given independent explicit browser confirmations; when reading their IDs; then none collide.
    directory = Path(__file__).parents[1] / "docs/assets/negotiation"
    ids = [json.loads(path.read_text(encoding="utf-8"))["operation_id"] for path in directory.glob("decision-*.json")]
    assert len(ids) == len(set(ids)) == 9
