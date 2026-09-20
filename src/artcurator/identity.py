"""Identity stage coordinator, intentionally independent of score/run-all."""
import json
import logging
import time
from pathlib import Path

from .config import Settings
from .identity_detector import load_detector
from .identity_store import atomic_bytes, file_digest, manifest, record_environment, stage
from .scan import pixels


def benchmark(settings: Settings) -> None:
    """Paired fixed-hash twelve-image n/s feasibility sample, not qualification."""
    rows = sorted(manifest(settings.out), key=lambda r: r.sha256)[:12]
    measurements = []
    for variant in ("n", "s"):
        options = settings.identity.model_copy(update={"variant": variant, "detector": "anime_face_detection"})
        load_start = time.perf_counter()
        adapter = load_detector(options)
        load_seconds = time.perf_counter() - load_start
        for repeat in range(2):
            started = time.perf_counter()
            count = 0
            for row in rows:
                if file_digest(Path(row.abs_path)) != row.sha256:
                    raise ValueError("benchmark source changed")
                with pixels(Path(row.abs_path)) as image:
                    count += len(adapter.predict(image))
            measurements.append({"variant": variant, "repeat": repeat, "seconds": time.perf_counter() - started,
                                 "images": len(rows), "faces": count, "load_seconds": load_seconds,
                                 "revision": adapter.info.revision, "artifact_sha256": adapter.artifact_sha256})
    atomic_bytes(settings.out / "identity-detector-benchmark.json", json.dumps({
        "method": "first 12 sorted full hashes, two repeats, n then s; decode/hash included; unlabelled feasibility only",
        "contents": [r.sha256 for r in rows], "measurements": measurements}, indent=2).encode())


def run(settings: Settings, command: str, labels: Path | None = None) -> None:
    from .identity_cluster import cluster
    from .identity_detect import detect
    from .identity_embed import embed
    from .identity_labels import apply_labels
    from .identity_report import assignments, report
    record_environment(settings.out)
    commands = ["identity-detect", "identity-embed", "identity-cluster", "identity-report"] if command == "identity" else [command]
    for selected in commands:
        with stage(settings.out, selected):
            match selected:
                case "identity-detect":
                    detect(settings.out, settings.identity)
                case "identity-embed":
                    embed(settings.out, settings.identity)
                case "identity-cluster":
                    cluster(settings.out, settings.identity)
                case "identity-report":
                    report(settings.out, settings.identity)
                case "identity-apply":
                    if labels is None:
                        raise ValueError("identity-apply requires --labels")
                    has_embeddings = (settings.out / "identity-embedding.json").exists()
                    before = assignments(settings.out, settings.identity)[0] if has_embeddings else {}
                    result = apply_labels(settings.out, labels)
                    logging.info("identity labels applied faces=%d clusters=%d unknown=%d conflicts=%d",
                                 result.faces_changed, result.clusters_changed,
                                 len(result.unknown_face_ids), len(result.conflicting_clusters))
                    if has_embeddings:
                        after = assignments(settings.out, settings.identity)[0]
                        changes = [{"image_sha16": key, "before": before.get(key), "after": after.get(key)}
                                   for key in sorted(before.keys() | after.keys()) if before.get(key) != after.get(key)]
                        atomic_bytes(settings.out / "identity-assignment-changes.json", json.dumps({
                            "method": "leave-one-out-target-centroid-v1", "changed_images": len(changes),
                            "changes": changes}, indent=2, allow_nan=False).encode())
                        report(settings.out, settings.identity)
                case "identity-benchmark":
                    benchmark(settings)
                case _:
                    raise ValueError("unknown identity command")
