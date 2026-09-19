"""Frozen CSV export and auditable Markdown report, no corpus actions."""
import csv
import json
from collections import Counter

from . import db
from .config import Settings


def report(settings: Settings) -> None:
    rows = db.load_rows(settings.out)
    with (settings.out / "scores.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=db.COLUMNS, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(row.model_dump() for row in rows)
    with db.connection(settings.out) as connection:
        metadata = dict(connection.execute("SELECT key,value FROM meta"))
        timings = list(connection.execute("SELECT pass,seconds,images,cached,load_seconds FROM timings"))
    tiers = Counter(row.proposed_tier for row in rows)
    flags = Counter(flag for row in rows for flag in row.flags.split("|") if flag)
    family_sizes = Counter(Counter(row.family_id for row in rows).values())
    distribution = {"1": family_sizes[1], "2": family_sizes[2],
                    "3-5": sum(n for size, n in family_sizes.items() if 3 <= size <= 5),
                    "6-10": sum(n for size, n in family_sizes.items() if 6 <= size <= 10),
                    "10+ (>10)": sum(n for size, n in family_sizes.items() if size > 10)}
    summary = ["# Read-only image curation report", "", "## Corpus",
               f"- Input: `{settings.input}`", f"- Scored file rows: **{len(rows)}**",
               f"- Unique SHA256: {len({r.sha256 for r in rows})}",
               f"- Families: {len({r.family_id for r in rows})}",
               f"- Total bytes: {sum(r.filesize for r in rows)}",
               f"- Dimensions: {dict(Counter(f'{r.width}x{r.height}' for r in rows))}",
               f"- Gaming sample: {sum(r.gaming_delta is not None for r in rows)}", "",
               "## Tier counts", *[f"- {k}: {v}" for k, v in sorted(tiers.items())], "",
               "## Human-review workload",
               f"- review / total: **{tiers['review']} / {len(rows)}** ({tiers['review'] / max(len(rows), 1):.2%})",
               f"- Additional routed assessments: {tiers['route_nsfw'] + tiers['route_identity']}",
               f"- Audit samples promoted from would-be archive candidates: {flags['audit_sample']}", "",
               "## Family size distribution (number of families; disjoint bins)",
               *[f"- {k}: {v}" for k, v in distribution.items()], "",
               "## CSV scorer schema",
               "`qrealign` immediately follows `topiq_nr`; `hpsv3_mu`, `hpsv3_sigma` follow `qrealign`. "
               "All existing columns retain their relative order. "
               "Q-ReAlign-Mini (0.8B), official pyiqa quality task, higher is better [0,1]; "
               "Five quality means contribute equally after population standardization (legacy missing scores skipped). "
               "HPSv3 sigma is exp(raw head channel 1), not a sixth score. "
               "disagreement = sqrt(population variance of available scorer z-values + "
               "(hpsv3_sigma / population_sd(hpsv3_mu))^2 / number_of_available_scorers). "
               "Native variance is omitted when HPS is absent or its population SD <= 1e-12. "
               "The unchanged uncertain threshold applies once to this combined signal.",
               "Conservative: queue >= P90 with unchanged gates; review >= P75 or flagged; "
               "unflagged below P75 are archive candidates. Routes take precedence. "
               "Would-be archive candidates with int(sha16[:8],16) % 20 == 0 get audit_sample and review.", "",
               "## Flag counts", *[f"- {k}: {v}" for k, v in sorted(flags.items())], "",
               "## Quantile thresholds actually used", "```json", metadata.get("thresholds", "{}"), "```", "",
               "## Effective configuration", "```json", settings.model_dump_json(indent=2), "```", "",
               "## Per-pass timings (inference includes decode/cache I/O; load/download separate)",
               "Completed invocations retained in chronological order. Interrupted prefixes are not in this table; "
               "see wall-clock/deviations. Cached counts include duplicate-content reuse within an invocation.",
               "| Pass | seconds | images | cached | s/img | load/download seconds |",
               "|---|---:|---:|---:|---:|---:|"]
    summary.extend(f"| {name} | {sec:.3f} | {n} | {cached} | {sec / max(n, 1):.5f} | {load:.3f} |"
                   for name, sec, n, cached, load in timings)
    summary += ["", "## Wall clock", *[f"- {k}: {v}" for k, v in metadata.items() if "wall" in k], "",
                 "## HPSv3 cost, VRAM and paired tier shifts", "```json",
                 json.dumps(json.loads(metadata.get("hpsv3_measurements", "{}")), indent=2), "```", "",
                 "## Model names, immutable revisions, preprocessing",
                *[f"- {k}: `{v}`" for k, v in metadata.items() if k.startswith("model_")], "",
                "## License", "pyiqa: PolyForm Noncommercial 1.0.0; personal/research pilot only. "
                "Applicable NTU S-Lab components and individual model licenses also apply.", "",
                "## Honesty / abstention semantics",
                "No calibrated precision, recall, identity verification, or safety guarantee can be claimed without labels. "
                "This is a ranking-first, zero-training pilot. Cosine identity can encode clothing, background, and composition. "
                "Safety and aesthetics may have domain bias on illustrations. Quantiles are corpus-relative, not absolute quality.",
                "Every tier is a PROPOSAL. review is abstention; route_* requests human assessment, not a verified classification. "
                "No moves, renames, or corpus copies are performed. Empty gaming_delta means unaudited, not safe. "
                "The SHA-based gaming sample is deterministic but not necessarily exactly 20%.",
                "Union-find is transitive: endpoints in a family need not satisfy a direct merge condition. "
                "near_dup_runnerup applies to ALL non-champions. Literal 'no flags' queue gating therefore excludes them, "
                "even when within champion_slack. Gaming delta is a signed maximum drop (negative if both variants improve).", "",
                "## Read-only / pixel-only evidence",
                "Python audit hook rejects filesystem writes outside the project. PNG ancillary payloads are seek-skipped "
                "before Pillow decode; only critical chunks and tRNS pixel transparency reach Pillow. "
                 "Models receive RGB pixels/tensors, never source paths, names, metadata, or image-specific text. "
                 "HPSv3 uses an empty image-specific prompt plus its fixed upstream instruction/reward token. Raw-file SHA is only an I/O "
                "identity and prescribed sampling/tie-break key. Library caches and temporary files stay inside out/cache.", "",
                "## Fallbacks / deviations",
                "- Main environment retains transformers<5 for measured aesthetic-score compatibility; "
                "Q-ReAlign uses isolated Transformers 5 (dependency path b).",
                "- TOPIQ uses native-resolution FP32 microbatch=1 inside batches to avoid padding or distortion changes.",
                "- pyiqa installs pandas transitively; pipeline code uses stdlib csv only, never pandas.",
                "- Identity references use deterministic greedy pHash<=4 dedup, keeping mutually distinct representatives.",
                *[f"- {k}: {v}" for k, v in metadata.items() if "fallback" in k or "deviation" in k]]
    reference_file = settings.out / "cache/reference_manifest.json"
    if reference_file.exists():
        refs = json.loads(reference_file.read_text(encoding="utf-8"))
        summary += ["", "## References", f"- Own: {refs['own_before_dedup']} -> {refs['own_after_dedup']} deduped",
                    *[f"- {key}: {len(value)}" for key, value in refs["groups"].items()],
                    f"- Other reference folders: {refs['other_folders']}"]
    (settings.out / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
