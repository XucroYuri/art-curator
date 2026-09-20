"""Additive A/B ranking evidence, not a calibrated identity/false-kill claim."""
import csv
import io
import json
from collections import Counter
from pathlib import Path
from typing import Final

import numpy as np
from scipy.stats import rankdata
from numpy.typing import NDArray

from .identity_labels import load_registry
from .identity_schema import IdentityOptions
from .identity_store import atomic_bytes, load_document, load_provenance, load_vectors, manifest

COLUMNS: Final = ("face_id", "image_sha16", "filename", "bbox_x", "bbox_y", "bbox_w", "bbox_h",
                  "det_score", "cluster_id", "cluster_prob", "is_outlier", "cluster_margin",
                  "identity_sim_old", "image_best_face_sim")


def loo_scores(vectors: NDArray, groups: list[NDArray]) -> NDArray[np.float64]:
    """Max cosine to target centroids excluding the query itself; NaN is unavailable."""
    result = np.full(len(vectors), np.nan)
    for indices in groups:
        total = vectors[indices].sum(axis=0, dtype=np.float64)
        members = set(indices.tolist())
        for index, vector in enumerate(vectors):
            center = total - vector if index in members else total
            length = np.linalg.norm(center)
            if length <= 1e-12:
                continue
            score = float(np.clip(center @ vector / length, -1, 1))
            result[index] = score if np.isnan(result[index]) else max(result[index], score)
    return result


def assignments(out: Path, options: IdentityOptions) -> tuple[dict[str, float], list[int], str]:
    document = load_document(out)
    vectors = load_vectors(out, document)
    registry = load_registry(out)
    named = {c.confirmed_character for c in document.clusters if c.confirmed_character is not None}
    target_name = options.target_character
    if target_name is None and len(named) == 1:
        target_name = next(iter(named))
    targets = [c.cluster_id for c in document.clusters if target_name and c.confirmed_character == target_name]
    reason = "confirmed character" if targets else "unavailable target"
    if not registry.references and document.clusters:
        targets = [max(document.clusters, key=lambda c: (c.size, -c.cluster_id)).cluster_id]
        reason = "largest cluster (unlabeled ranking proxy)"
    groups = []
    for cluster_id in targets:
        indices = [i for i, f in enumerate(document.faces) if f.cluster_id == cluster_id and f.face_id not in registry.excluded]
        if indices:
            groups.append(np.array(indices))
    if not groups:
        return {}, targets, reason
    scores = loo_scores(vectors, groups)
    result: dict[str, float] = {}
    for face, similarity in zip(document.faces, scores, strict=True):
        if face.face_id in registry.excluded or np.isnan(similarity):
            continue
        result[face.image_sha16] = max(result.get(face.image_sha16, -1.), float(similarity))
    return result, targets, reason


def report(out: Path, options: IdentityOptions) -> None:
    document = load_document(out)
    rows = manifest(out)
    provenance = load_provenance(out)
    if {r.sha16: r.sha256 for r in rows} != provenance.contents:
        raise ValueError("manifest no longer matches identity content snapshot")
    values, targets, reason = assignments(out, options)
    by_hash = {row.sha16: row for row in rows}
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for face in document.faces:
        row = by_hash[face.image_sha16]
        writer.writerow((face.face_id, face.image_sha16, row.filename, *face.bbox, face.det_score,
                         face.cluster_id, face.cluster_prob, face.is_outlier, face.cluster_margin,
                         row.identity_sim, values.get(face.image_sha16)))
    atomic_bytes(out / "identity-faces.csv", buffer.getvalue().encode("utf-8"))
    pairs = np.asarray([(r.identity_sim, values[r.sha16]) for r in rows
                        if r.identity_sim is not None and r.sha16 in values], dtype=float).reshape(-1, 2)
    pearson = spearman = None
    if len(pairs) > 1 and np.all(np.std(pairs, axis=0) > 1e-12):
        pearson = float(np.corrcoef(pairs.T)[0, 1])
        spearman = float(np.corrcoef(rankdata(pairs, axis=0).T)[0, 1])
    old = [r.identity_sim for r in rows if r.identity_sim is not None]
    thresholds = {}
    for quantile in (.1, .2, .9):
        if not old:
            continue
        threshold = float(np.quantile(old, quantile))
        old_pass = pairs[:, 0] >= threshold
        new_pass = pairs[:, 1] >= threshold
        thresholds[f"P{int(quantile * 100)}"] = {
            "old_threshold": threshold, "agreement": int(np.sum(old_pass == new_pass)),
            "disagreement": int(np.sum(old_pass != new_pass)),
            "old_below_new_above": int(np.sum(~old_pass & new_pass)),
            "old_above_new_below": int(np.sum(old_pass & ~new_pass)), "paired_rows": len(pairs)}
    excluded = set(load_registry(out).excluded)
    target_images = {f.image_sha16 for f in document.faces
                     if f.cluster_id in targets and not f.is_outlier and f.face_id not in excluded}
    outliers = sum(f.is_outlier for f in document.faces)
    receipt = {"similarity_method": "leave-one-out-target-centroid-v1",
        "corpus_fingerprint": provenance.corpus_fingerprint, "images": len(rows),
        "faces": document.face_count, "clusters": document.cluster_count,
        "size_distribution": dict(Counter(c.size for c in document.clusters)),
        "outlier_rate": outliers / max(document.face_count, 1), "paired_rows": len(pairs),
        "pearson": pearson, "spearman": spearman, "thresholds": thresholds,
        "candidate_false_kills_if_culled_corpus": len(target_images), "target_clusters": targets,
        "target_reason": reason, "unavailable_images": sum(r.sha16 not in values for r in rows)}
    atomic_bytes(out / "identity-ab.json", json.dumps(receipt, indent=2, allow_nan=False).encode())
    text = ["# Identity v2 LOO A/B — experimental", "", f"Corpus fingerprint: `{provenance.corpus_fingerprint}`",
            f"Detector: `{document.detector.model}` @ `{document.detector.revision}`",
            f"Embedder: `{document.embedder.model}` @ `{document.embedder.revision}`", "",
            f"Images: {len(rows)}; faces: {document.face_count}; clusters: {document.cluster_count}; outliers: {outliers}.",
             f"Target: {reason}; cluster IDs: {targets}.",
             "Similarity: leave-one-out target centroid; query face excluded from its own target. "
             "Singleton/zero-norm centers are unavailable. Image score is max over available faces.",
            f"Pearson: {pearson}; Spearman: {spearman}; paired rows: {len(pairs)}.", "",
            "## Old numeric thresholds (same cosine cutoff; not calibrated across representations)",
            "| Cut | Old threshold | Agree | Disagree | Old below/new above | Old above/new below |",
            "|---|---:|---:|---:|---:|---:|"]
    for key, item in thresholds.items():
        text.append(f"| {key} | {item['old_threshold']:.6f} | {item['agreement']} | {item['disagreement']} | "
                    f"{item['old_below_new_above']} | {item['old_above_new_below']} |")
    text += ["", f"Unavailable image scores: {receipt['unavailable_images']} (excluded, never filled with zero).",
             "", "## Candidate false kills (conditional on this being the culled corpus)",
             f"{len(target_images)} unique images have a non-outlier target-cluster face. This is a review candidate count, "
             "not measured false positives of the incumbent. Cluster membership is an uncalibrated plausibility proxy.",
             "", "## Largest 20 clusters", "| Cluster | Size | Representative crops |", "|---|---:|---|"]
    for cluster in sorted(document.clusters, key=lambda c: (-c.size, c.cluster_id))[:20]:
        crops = ", ".join(f"`faces/{face}.jpg`" for face in cluster.representative_faces)
        text.append(f"| {cluster.cluster_id} | {cluster.size} | {crops} |")
    text += ["", "## Costs", "See identity-timings.jsonl: stage seconds and process peak RAM; "
              "divide detection seconds by images and embedding seconds by faces. "
              "identity-embedding.json records actual execution, cache hits, inference time and allocator VRAM peaks.",
             "", "## Limitations", "No labels ⇒ ranking evidence only; no precision/recall or identity-verification claim. "
              "LOO removes direct self-inclusion, but cluster selection still uses the full corpus. "
              "Background, hair and clothing remain in crops. "
             "CPU detection misses small, occluded, stylized or profile faces; no face is unavailable, not a negative match. "
             "HDBSCAN confidence is membership persistence, not identity accuracy. DBSCAN/CW confidence is binary core membership. "
             "cluster_margin is nearest-other-centroid cosine (higher means more confusable), NOT a calibrated target margin. "
             "Single-cluster margins are null. Unknown faces remain outliers even when a similarity is reported. "
             "CCIP is optional OpenRAIL-restricted; cosine is not its learned metric. "
             "YuNet is an explicit separate profile, never automatic substitution. Legacy PNG rendering strips ICC/EXIF; "
             "canonical rendering qualification, labeled hard negatives, model-specific threshold calibration, "
             "merge/split/undo UI and cross-profile equivalence remain unqualified. No legacy scores/routes were changed."]
    atomic_bytes(out / "identity-ab-report.md", ("\n".join(text) + "\n").encode("utf-8"))
