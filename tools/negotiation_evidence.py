# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["Pillow", "pydantic>=2"]
# ///
# How to run (existing uv project environment, FROM repository root):
# .venv\Scripts\python.exe tools\negotiation_evidence.py
"""Generate truthful local G2 evidence over the synthetic ALBUM-FLOW-v1 recipe only."""
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from artcurator.config import ROOT, Settings
from artcurator.identity_store import digest, file_digest
from artcurator.ingest import run
from artcurator.ingest_schema import IngestError, Options, transition
from artcurator.negotiation import authorize, confirm, prepare, retract
from artcurator.negotiation_consent import Decision, FolderSelection
from artcurator.negotiation_metrics import HumanLabel, Labels
from artcurator.negotiation_report import report_digest

RECIPE = ROOT / "tests" / "fixtures" / "album-flow.json"
EVIDENCE = ROOT / "specs" / "evidence"


def hashes(root: Path) -> dict[str, tuple[int, str]]:
    return {p.relative_to(root).as_posix(): (p.stat().st_size, file_digest(p))
            for p in root.rglob("*") if p.is_file()}


def make_corpus(source: Path) -> None:
    recipe = json.loads(RECIPE.read_bytes())
    for item in recipe["images"]:
        path = source / item["name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if "copy" in item:
            path.write_bytes((source / item["copy"]).read_bytes())
        else:
            Image.new("RGB", tuple(item["size"]), tuple(item["color"])).save(path)


def request(report, mode: str, scope: str, operation: str) -> Decision:
    folders = () if scope == "none" else tuple(FolderSelection(
        folder_id=folder.folder_id, relation_type="undetermined") for folder in report.folders)
    return Decision(actor="local:evidence", operation_id=operation, affirmative=True,
                    report_digest=report.report_digest, snapshot_digest=report.snapshot_digest,
                    profile_digest=report.profile_digest, mode=mode, inheritance=scope, folders=folders,
                    cost_ceiling_seconds=0, acknowledged=report.limitations)


def receipt(identifier: str, status: str, method: str, comparator: str, limitations: list[str],
            extra: dict) -> dict:
    return {"id": identifier, "status": status, "method": method,
            "fixture": "ALBUM-FLOW-v1 synthetic inventory-only (two rectangles + one duplicate)",
            "fixture_recipe_sha256": file_digest(RECIPE),
            "comparator": comparator, "limitations": limitations,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reproduction": "python tools/negotiation_evidence.py; "
                            "python -m pytest tests/test_negotiation_*.py",
            "scope_note": "generator assertions plus named pytest coverage; "
                          "not full AC certification", **extra}


def write(name: str, body: dict) -> None:
    (EVIDENCE / (name + ".json")).write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")


def condition(status: str, *evidence: str) -> dict:
    return {"status": status, "evidence": list(evidence)}


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="g2-evidence-"))
    source, out = work / "source", work / "job"
    make_corpus(source)
    settings = Settings(input=source, out=out, references=source, posted=source,
                        characters_root=source, workers=1)
    options = Options(analysis=False, reserve_bytes=0)
    before = hashes(source)
    job = run(settings, options)
    after_initial = hashes(source)
    assert after_initial == before

    # Missing evidence must be reported, never defaulted to zero.
    bare = prepare(out)
    assert all(folder.purity.method == "unavailable" for folder in bare.folders)
    assert bare.global_evidence.crop_unknown.method == "unavailable"
    assert bare.recommendations.cluster_coverage is None
    assert bare.prediction.auto is None and bare.report_digest == report_digest(bare)

    # One declared target + independent label exercises the measured path.
    folder_a = next(folder for folder in bare.folders if folder.path == "folder-a")
    labelled_member = next(member for member in bare.members if member.folder_id == folder_a.folder_id)
    labels = Labels(snapshot_digest=job.revision,
                    labels=(HumanLabel(image_id=labelled_member.image_id, identity="示例角色",
                                       actor="local:evidence", evidence_ref="human:evidence",
                                       independent=True),),
                    targets={folder_a.folder_id: "示例角色"}, target_types={folder_a.folder_id: "character"})
    report = prepare(out, labels)
    measured = next(folder for folder in report.folders if folder.path == "folder-a")
    assert measured.target_purity.value is not None and measured.unresolved_labels == 0
    assert next(f for f in report.folders if f.path == "folder-b").purity.value is None

    # All nine mode/scope combinations are recordable, replayable and non-operative.
    consequences: dict[str, list[str]] = {}
    for mode in ("human-first", "auto-first", "inherit-only"):
        for scope in ("all", "selected", "none"):
            choice = request(report, mode, scope, f"{mode}:{scope}")
            receipt_value = confirm(out, choice)
            assert confirm(out, choice) == receipt_value, "replay must return one receipt"
            assert receipt_value.context_enabled is False and receipt_value.mapping_mutations == 0
            assert "context-disabled" in receipt_value.consequences
            if mode == "inherit-only" and scope == "none":
                assert "browse-only-not-classification" in receipt_value.consequences
            consequences[f"{mode}+{scope}"] = list(receipt_value.consequences)
            retract(out, "local:evidence")
    live = confirm(out, request(report, "auto-first", "all", "stale-check"))
    assert authorize(out, (live.members[0].path,)) == live

    # A newly added member invalidates the receipt and advances the snapshot.
    Image.new("RGB", (10, 10), "green").save(source / "future.png")
    before_delta = hashes(source)
    advanced = run(settings, options)
    assert advanced.revision != report.snapshot_digest
    revisions_before = hashes(out / "revisions")
    stale_refused = "stale" in str(_failure(authorize, out, ("folder-a/red.png",)))
    retract(out, "local:evidence")

    # Retraction leaves no operative residue in the derived tree.
    assert hashes(out / "revisions") == revisions_before
    revoked_refused = "consent" in str(_failure(authorize, out, ("folder-a/red.png",)))
    job_after = json.loads((out / "job.json").read_bytes())
    assert job_after["negotiation"]["active"] is None
    assert all(r["status"] == "revoked" for r in job_after["negotiation"]["history"])
    guards = [target for target in ("FIRST-PASS", "REVIEW", "ARCHIVE") if _guarded(target)]
    assert len(guards) == 3 and hashes(source) == before_delta

    write("AC-FR-ALBUM-NEGOTIATE-001-01", receipt(
        "AC-FR-ALBUM-NEGOTIATE-001-01", "partial",
        "real sealed inventory-only report plus analytic cluster/metrics tests",
        "mandatory fields/denominators present; zero unlabelled purity; boundary eligibility and "
        "representative exactness reproduce analytically; unavailable never zero",
        ["no labelled ALBUM-FOLDER-v1/ALBUM-CONFUSABLE-v1 population run; no whole-image denominators; "
         "cluster quality uncalibrated"],
        {"report_digest": report.report_digest, "snapshot_digest": report.snapshot_digest,
         "no_label_report_digest": bare.report_digest,
         "purity_available_folders": [f.path for f in report.folders if f.purity.value is not None],
         "purity_unavailable_folders": [f.path for f in report.folders if f.purity.value is None]}))
    write("AC-FR-ALBUM-NEGOTIATE-002-01", receipt(
        "AC-FR-ALBUM-NEGOTIATE-002-01", "partial",
        "analytic detector boundary/missingness tests plus fixture folder measurement",
        "exact tie/overlap/unavailable table outcomes; no invented probability; path rename changes "
        "no measured value",
        ["no independently labelled regime fixture; artist-portfolio needs human artist labels; "
         "thresholds are engineering policy, not calibrated optima"],
        {"folder_regimes": {f.path: f.regimes.status for f in report.folders}}))
    write("AC-FR-ALBUM-NEGOTIATE-003-01", receipt(
        "AC-FR-ALBUM-NEGOTIATE-003-01", "partial",
        "all nine mode/scope combinations, replay, dismissal, stale snapshot and future-file refusal",
        "exact recorded consequences; zero pre-consent mutations; one receipt per confirmation; "
        "new member and stale digest fail closed",
        ["no rendered client prompt/dismissal; predicted tier counts and cost enforcement unavailable; "
         "inheritance effects recorded, not materialized (G5)"],
        {"combos": consequences, "stale_refused": stale_refused, "revoked_refused": revoked_refused,
         "guarded": guards, "receipt_id": live.receipt_id}))
    write("AC-FR-ALBUM-NEGOTIATE-004-01", receipt(
        "AC-FR-ALBUM-NEGOTIATE-004-01", "partial",
        "string snapshot of required literals and bound counts on the measured report",
        "all applicable literals exact; zero unresolved placeholders; unavailable renders 未知; "
        "defaults are human-first/none with mapping_action_available=false",
        ["no rendered client/DOM snapshot; no 520/900/1440 width or keyboard-only verification; "
         "owned by the visual task (FR-ALBUM-NEGOTIATE-004-01 remains unverified client-side)"],
        {"presentation_sha256": digest(report.presentation.model_dump_json().encode()),
         "locales": [report.presentation.locale], "visual_verification": "not performed"}))
    summary = {
        "id": "g2-mode-negotiation",
        "status": "partial",
        "fixture": "ALBUM-FLOW-v1 synthetic inventory-only",
        "fixture_recipe_sha256": file_digest(RECIPE),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ac_verdicts": {"AC-FR-ALBUM-NEGOTIATE-001-01": "partial",
                        "AC-FR-ALBUM-NEGOTIATE-002-01": "partial",
                        "AC-FR-ALBUM-NEGOTIATE-003-01": "partial",
                        "AC-FR-ALBUM-NEGOTIATE-004-01": "partial"},
        "adr_0005_conditions": {
            "measured-admission-reported-before-consent": condition(
                "pass-scoped", "tools/negotiation_evidence.py", "tests/test_negotiation_folders.py",
                "tests/test_negotiation_adr.py"),
            "snapshot-bound-affirmative-consent": condition(
                "pass-scoped", "tests/test_negotiation_adr.py", "tests/test_negotiation_consent.py",
                "tests/test_negotiation_flow.py"),
            "consent-alone-does-not-authorize-use": condition(
                "pass-scoped", "receipt.context_enabled=false; receipt.mapping_mutations=0; "
                "G4 execution remains guarded"),
            "residue-free-retraction": condition(
                "pass-scoped", "revisions tree identical after retraction; history revoked-only; "
                "stale evidence retraction tested"),
            "weak-prior-loses-to-visual-contradiction": condition(
                "inconclusive", "contextual grouping layer is not implemented (context_enabled=false); "
                "no use can be admitted or vetoed yet"),
            "manual-human-path-always-available": condition(
                "partial", "manual_collection_available=true recorded; no rendered action (G5)"),
            "identity-oriented-prior-minima": condition(
                "partial", "analytic >=30 labels and Wilson lower >=0.90 tests; no labelled fixture run")},
        "guards": {"first_pass_review_archive": guards,
                   "context_enabled": False, "mapping_mutations": 0},
        "source_integrity": {
            "method": "size + full SHA-256 before/after each ingest run, including the added member",
            "identical_after_initial_run": after_initial == before,
            "identical_after_delta_run": hashes(source) == before_delta},
        "consequence_tokens": sorted({token for values in consequences.values() for token in values}),
        "reproduction": "python tools/negotiation_evidence.py; python -m pytest tests/test_negotiation_*.py"}
    write("g2-mode-negotiation", summary)
    written = ["g2-mode-negotiation", *(f"AC-FR-ALBUM-NEGOTIATE-00{index}-01" for index in (1, 2, 3, 4))]
    print(json.dumps({"evidence": [f"specs/evidence/{name}.json" for name in written],
                      "report_digest": report.report_digest, "combos": len(consequences),
                      "stale_refused": stale_refused, "source_identical": True},
                     indent=2, ensure_ascii=False))
    shutil.rmtree(work, ignore_errors=True)


def _failure(operation, *args) -> BaseException:
    try:
        operation(*args)
    except IngestError as error:
        return error
    raise AssertionError(f"{operation.__name__} unexpectedly succeeded")


def _guarded(target: str) -> bool:
    try:
        transition("PROPOSE", target)
    except NotImplementedError:
        return True
    return False


if __name__ == "__main__":
    main()
