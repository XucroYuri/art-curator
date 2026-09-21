# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["Pillow", "pydantic>=2"]
# ///
# How to run (existing uv project environment, FROM repository root):
# .venv\Scripts\python.exe tools\ingest_evidence.py
"""Generate truthful local G1 evidence; never reads or writes a real image library."""
import json
import time
import uuid
from pathlib import Path

from PIL import Image

from artcurator import ingest
from artcurator.config import ROOT, Settings
from artcurator.identity_store import file_digest
from artcurator.ingest_adapters import Request, Result, execute
from artcurator.ingest_schema import Options, transition
from artcurator.ingest_storage import retained_bytes


def hashes(root: Path) -> dict[str, tuple[int, int, str]]:
    """Empirical proof includes all opaque source bytes and required filesystem metadata."""
    return {p.relative_to(root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns, file_digest(p))
            for p in root.rglob("*") if p.is_file()}


def main() -> None:
    bundle = ROOT / "out" / "ingest" / ("g1-evidence-" + uuid.uuid4().hex[:12])
    source, output, evidence = bundle / "source", bundle / "job", bundle / "evidence"
    evidence.mkdir(parents=True)
    recipe_path = ROOT / "tests" / "fixtures" / "album-flow.json"
    recipe = json.loads(recipe_path.read_bytes())
    for item in recipe["images"]:
        path = source / item["name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if "copy" in item:
            path.write_bytes((source / item["copy"]).read_bytes())
        else:
            Image.new("RGB", tuple(item["size"]), tuple(item["color"])).save(path)
    settings = Settings(input=source, out=output, references=source, posted=source,
                        characters_root=source, workers=1)
    options = Options(analysis=False, reserve_bytes=0)
    before = hashes(source)
    started = time.perf_counter()
    first = ingest.run(settings, options)
    first_wall = time.perf_counter() - started
    after = hashes(source)
    assert before == after
    snapshot = output / "revisions" / first.revision
    sealed_before = hashes(snapshot)
    started = time.perf_counter()
    replay = ingest.run(settings, options)
    warm_wall = time.perf_counter() - started
    assert first.revision == replay.revision and hashes(snapshot) == sealed_before
    assert all(r.outcome == "cached" for r in replay.receipts if r.action != "inventory-validation")
    Image.new("RGB", (39, 29), "green").save(source / "new.png")
    (source / "duplicate.png").write_bytes((source / "folder-a/red.png").read_bytes())
    added_before = hashes(source)
    started = time.perf_counter()
    incremental = ingest.run(settings, options)
    incremental_wall = time.perf_counter() - started
    fresh_scan = sum(r.items for r in incremental.receipts if r.action == "scan" and r.outcome == "completed")
    assert fresh_scan == 1 and hashes(source) == added_before
    resume_settings = settings.model_copy(update={"out": bundle / "resume-job"})
    def interrupt(request: Request) -> Result:
        if request.action == "detect":
            raise RuntimeError("intentional evidence cut after committed scan")
        return execute(request)
    try:
        ingest.run(resume_settings, options, execute=interrupt)
    except RuntimeError:
        pass  # The injected failure is followed by assertions on the resumed public result.
    resumed = ingest.run(resume_settings, options)
    assert resumed.progress.status == "complete"
    assert all(r.outcome == "cached" for r in resumed.receipts if r.action == "scan")
    guards = []
    for target in ("CONFIRM", "FIRST-PASS", "REVIEW", "ARCHIVE"):
        try:
            transition("PROPOSE", target)
        except NotImplementedError:
            guards.append(target)
    assert len(guards) == 4
    no_writes = {"method": "full SHA-256 + size + mtime_ns before/after complete G1 run",
                 "before": before, "after": after, "identical": before == after,
                 "incremental_originals_identical": added_before == hashes(source)}
    timing = {"fixture": "ALBUM-FLOW-v1", "boundary": "synthetic inventory-only G1, all model signals explicitly unavailable",
        "first_seconds": first_wall, "warm_validation_seconds": warm_wall,
        "incremental_seconds": incremental_wall, "first_seconds_per_unique_image": first_wall / 2,
        "unique_images_first": 2, "occurrences_first": 3, "new_unique_images": fresh_scan,
        "stage_receipts": [r.model_dump(mode="json") for r in first.receipts],
        "randomized_paired_gpu_runs": 0, "full_library_measured": False,
        "estimate": {"library_images": 26876, "hours": [2, 3], "wd_seconds_per_image": [.13, .22],
                     "hardware": "RTX 5060 Ti", "guarantee": False}}
    (evidence / "source-integrity.json").write_text(json.dumps(no_writes, indent=2), encoding="utf-8")
    (evidence / "fixture-throughput.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")
    (evidence / "progress-sample.json").write_text(first.progress.model_dump_json(indent=2), encoding="utf-8")
    requirements = {
        "AC-FR-ALBUM-INGEST-001-01": ("scoped-pass", "transition/barrier and source-integrity integration",
            "G1 barriers + four explicit guards; source size/mtime/hash identical", []),
        "AC-FR-ALBUM-INGEST-002-01": ("partial", "real detached-owner/client-exit and stage-deadline tests",
            "tests/test_ingest_process.py; tests/test_ingest_recovery.py",
            ["hardware-independent timing bounds and restart auto-recovery unqualified"]),
        "AC-FR-ALBUM-INGEST-003-01": ("scoped-pass", "incremental-add/copy plus rename/change/delete/replay tests",
            "one new unique image scanned; identical-copy inference reuse tested with synthetic predictors",
            ["G2-G6 human mapping mutation is guarded, not implemented"]),
        "AC-NFR-ALBUM-INGEST-001-01": ("inconclusive", "instrumented first/warm/incremental fixture trace",
            "fixture-throughput.json; component estimate disclosed separately",
            ["no ten randomized GPU pairs/full-library run; unmeasured stage ceilings"]),
        "AC-NFR-ALBUM-INGEST-002-01": ("partial", "storage admission and quota/reserve refusal tests",
            f"retained fixture job bytes={retained_bytes(output)}",
            ["hard per-write/native quotas and unknown face/matrix reservation unqualified"]),
        "AC-NFR-ALBUM-INGEST-003-01": ("scoped-pass", "eight stage cutpoints, resume and second replay",
            "tests/test_ingest_recovery.py; exact logical report comparison excluding costs",
            ["cross-file crash-atomicity and physical power-loss durability unverified"]),
        "AC-NFR-ALBUM-INGEST-004-01": ("partial", "per-action metered outcome and cached replay",
            "wall/coordinator CPU/source payload/net growth boundaries explicitly labelled",
            ["physical IO/subprocess CPU/GPU/energy/temporary/peak meters unavailable"]),
    }
    for identifier, (status, method, comparator, limitations) in requirements.items():
        receipt = {"id": identifier, "status": status, "method": method, "fixture": "ALBUM-FLOW-v1",
            "fixture_recipe_sha256": file_digest(recipe_path), "comparator": comparator,
            "limitations": limitations, "revision": first.revision, "new_revision": incremental.revision,
            "resume_status": resumed.progress.status, "idempotent_revision": replay.revision == first.revision,
            "source_integrity_sha256": file_digest(evidence / "source-integrity.json"),
            "evidence_scope": "generator assertions plus named pytest coverage; not full AC certification"}
        (evidence / (identifier + ".json")).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"bundle": str(bundle.relative_to(ROOT)), "evidence": str(evidence.relative_to(ROOT)),
        "first_seconds": first_wall, "warm_seconds": warm_wall, "incremental_seconds": incremental_wall,
        "source_identical": True, "incremental_unique_scanned": fresh_scan, "resume": resumed.progress.status,
        "guards": guards}, indent=2))


if __name__ == "__main__":
    main()
