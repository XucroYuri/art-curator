> 中文摘要
> 九项门禁覆盖视觉不变性、数值、恢复、资源与许可证。
> 每项门禁都有触发条件、方法、验收标准和证据位置。
> 噪声结果为无法判定；数值通过不能覆盖安全与来源失败。

# Quality gates

All gate records: scope S:* / E: changed profile and certified references / T0–T4; status **proposed**. Method, fixture and pass/fail budget are in each AC. Evidence is mandatory even for failure/inconclusive outcomes. Gate “verified” only applies to the named profile/corpus/hardware, never every tier. INV-3/INV-4 failures veto numerical passes.

Foundation batch 2 adds synthetic HASH/PROTOCOL/RESOURCE/MOVE seeds in
`tests/test_architecture_{identity,worker,resources,persistence}.py`, including
real foreground stub-process exchanges and actual SQLite migration interruption.
The scoped receipt is [architecture-gap-regressions.json](evidence/architecture-gap-regressions.json).
It does not qualify numerical invariance, performance, physical durability,
external contention or resource tiers; affected gates remain proposed.

## Fixture registry

Aliases identify planned versioned suites, **not existing committed new fixtures**. Before a gate runs, its manifest binds generated seeds/source revisions and full fixture hashes. Any TBD digest or budget makes qualification inconclusive. Existing tests are seeds for suites, not replacements for immutable fixtures.

| Fixture ID | Definition / current seed |
|---|---|
| SPEC-TREE-v1 | This 21-file tree plus release manifest; digest produced per candidate |
| CLAIMS-v1 | Positive and deliberately incomplete claim/evidence manifests; new, digest TBD |
| VISUAL-v1 | Renames, metadata-only variants, EXIF rotations, ICC goldens, corrupt decodes; seeds `test_contract.py`, `test_pipeline_edges.py`; digest TBD |
| HASH-v1 | Prefix collisions, duplicates, reordered members and mutated sources; synthetic, digest TBD |
| PROFILE-v1 | Semantic/execution/tier/resume combinations and missing signals; synthetic, digest TBD |
| NUMERIC-v1 | Pinned varied-resolution images, near-threshold pairs, grouping bridges and exact reference outputs; corpus/digest TBD |
| GAMING-v1 | Original versus JPEG-q68 and saturation×1.15 plus adversarial variants; from `score.py` transformations, labels/digest TBD |
| MOVE-SYN-v1 | Synthetic CJK paths, collisions, disk-full, torn records, external edits and crash cutpoints; seed `test_apply.py`; digest TBD |
| RESOURCE-v1 | Large native images, contention, queue cancellation, 10k/100k synthetic embeddings; digest TBD |
| PROTOCOL-v1 | Fake workers, malformed sidecars/cache/DB versions and interrupted migrations; digest TBD |
| BENCH-v1 | Frozen representative stratified slices plus full-run snapshot, cold/warm repeats; digests TBD; historical 300-row slice is not sufficient alone |
| LICENSE-v1 | Inventory of code, weights, processors, calibration datasets and distribution channels; digest TBD |
| SYN-STUDIO-v1 | `tests/fixtures/gallery` 60-row synthetic corpus plus new missing/degraded cases; exact file digests TBD |
| ID-SYN-v1 | Consent/licensed labelled character crops, confusables, unknowns and repeat naming sessions; new, digest/labels TBD |
| CANDIDATES-SYN-v1 | Deterministic vectors and synthetic studio records for ranked identity options; seed `tests/test_identity_candidates.py`, `tests/test_gallery_candidates.py`; digest TBD |

### NFR-GATE-001 — Visual-input invariance
When decoding, preprocessing or a model artifact changes, the evaluator shall test visual-input invariance before qualification.
- AC-NFR-GATE-001-01: VISUAL-v1 paired rename/metadata/rendering tests; exact canonical-pixel digests under pinned profiles and NFR-NUM-001 score budgets, zero metadata evidence leakage; evidence `evidence/AC-NFR-GATE-001-01.json`. Links INV-2, FR-STABLE-001.

### NFR-GATE-002 — Batch invariance
When batch size, prefetch or worker concurrency changes, the evaluator shall compare item outputs and decisions against serial execution.
- AC-NFR-GATE-002-01: NUMERIC-v1 serial versus every admitted batch including ragged resolutions and cancellation; per-scorer NFR-NUM-001 bounds, exact content association, zero decision changes outside declared ambiguity set; evidence `evidence/AC-NFR-GATE-002-01.json`.

### NFR-GATE-003 — Cross-device consistency
When provider, precision, device, kernel or export changes, the evaluator shall certify the candidate against a named reference before declaring compatibility.
- AC-NFR-GATE-003-01: NUMERIC-v1 all-value/embedding comparisons, boundary decisions, rank inversions and family changes; NFR-NUM-001 budgets plus predeclared family/embedding thresholds, zero unsupported actionable flips; evidence `evidence/AC-NFR-GATE-003-01.json`. Average error alone fails; ONNX export success is insufficient.

### NFR-GATE-004 — Score-gaming audit
When quality models, preprocessing or decision thresholds change, the evaluator shall audit counterfactual score gaming and report audit coverage.
- AC-NFR-GATE-004-01: GAMING-v1 blinded paired labels and transformations; disclose signed score changes, ranking/route flips and unaudited rows, zero claims of safety for empty deltas; tolerated harmful preference/flip rates TBD before quality qualification; evidence `evidence/AC-NFR-GATE-004-01.json`. Current gaming_suspect=0.35 is a legacy threshold, not calibrated success.

### NFR-GATE-005 — Move crash recovery
When move planning, persistence, locking or undo changes, the evaluator shall inject crashes and verify recoverability before release.
- AC-NFR-GATE-005-01: MOVE-SYN-v1 all durability cutpoints including truncation and user edits; zero unverified source deletion, unrelated overwrite or unexplained ledger/filesystem mismatch; evidence `evidence/AC-NFR-GATE-005-01.json`. Links INV-3 and FR-PERSIST-001; current tests do not establish physical power-loss or mounted cross-volume certification.

### NFR-GATE-006 — Resource safety
When a tier, runtime or resource estimate changes, the evaluator shall stress admission, provider placement, queues and cancellation under contention.
- AC-NFR-GATE-006-01: RESOURCE-v1 sampled host/board memory plus allocator/thread instrumentation; NFR-RESOURCE-001 caps and NFR-DATA-001 ownership/bounds satisfied, no hidden provider fallback/paging fit; evidence `evidence/AC-NFR-GATE-006-01.json`.

### NFR-GATE-007 — Performance regression
When releasing a performance-affecting change, the evaluator shall run paired representative benchmarks with fixed semantic outputs and report noisy results as inconclusive rather than pass.
- AC-NFR-GATE-007-01: BENCH-v1 stratified paired randomized-order cold/warm repeats (minimum 10 pairs, retain raw samples); median ≤1.10× baseline, p95 ≤1.15×, peak memory ≤1.10× **and** within absolute admitted ceiling; evidence `evidence/AC-NFR-GATE-007-01.json`. Predeclare sampling and confidence method; confidence interval crossing a budget is inconclusive; lower bound beyond budget is fail. Small samples/unstable p95 need more data, not selective removal. Include load/decode/persist/export and actual provider, not only GPU kernel time.

### NFR-GATE-008 — Protocol/cache integrity
When worker, cache, sidecar or database formats change, the evaluator shall reject invalid/stale evidence and demonstrate migration and round-trip integrity.
- AC-NFR-GATE-008-01: HASH-v1/PROTOCOL-v1 corruption, unknown majors, reordered results and interrupted migrations; zero unauthorized actions/cache hits, exact unknown-field preservation and logical-row recovery; evidence `evidence/AC-NFR-GATE-008-01.json`. Links FR-WORKER-001, FR-CACHE-001, FR-PERSIST-001, FR-PROTOCOL-001.

### NFR-GATE-009 — License and distribution
When adding or redistributing an artifact, the maintainer shall separately clear source, dependency, weight, dataset and documentation rights for the intended channel.
- AC-NFR-GATE-009-01: audit LICENSE-v1 inventory/digests against terms and notices; zero unlicensed or incompatible distributed artifacts, unresolved rights block that channel; evidence `evidence/AC-NFR-GATE-009-01.json`.
- Known hazards: pyiqa PolyForm Noncommercial; InsightFace pretrained models non-commercial; deepghs CCIP OpenRAIL restrictions; dlib 68-point landmark model non-commercial; `lbpcascade_animeface` no license; aesthetic-predictor-v2-5 AGPL. AGPL project source does not grant model redistribution rights. HPS card Apache-2.0 does not clear the rest of the stack.

## Worked requirement (canonical reusable example)

### FR-DEGRADE-001 — Safe signal degradation
When an admitted run cannot provide a requested signal within its resource budget, the coordinator shall reduce batch and prefetch first, switch only to a certified execution profile if needed, and otherwise mark the signal unavailable and widen abstention without silently renormalizing the ensemble over surviving scorers.

Scope: S: fixed requested signal roster / E: requested and explicitly certified alternatives / T0–T4. Status: proposed.

An actionable recommendation is emitted **only if every admissible completion of unavailable or uncertain evidence yields that same recommendation**. Let C be all completions allowed by the declared signal ranges, intervals and corpus-statistic uncertainty; authorize r only when `{decision(c): c in C} = {r}`. Otherwise output review/abstain and a reason. Unknown/unbounded completion ranges do not justify a plug-in mean. Missing evidence may change corpus z-normalization/quantiles, so completion analysis includes those changes, not just the affected row. A request for human assessment is not a positive quality claim.

- AC-FR-DEGRADE-001-01: inject memory pressure on PROFILE-v1 with five requested means and no HPS-compatible certificate; trace batch/prefetch reduction before any fallback, requested roster unchanged, HPS unavailable, zero surviving-scorer renormalization, actual provider and each event recorded; evidence `evidence/AC-FR-DEGRADE-001-01.json`.
- AC-FR-DEGRADE-001-02: use a finite synthetic completion grid plus analytically bounded continuous intervals on PROFILE-v1; if any admissible completion changes the recommendation, expect review; unanimous completions may emit that recommendation with proof bounds; zero unauthorized actionable outputs; evidence `evidence/AC-FR-DEGRADE-001-02.json`.

Implementation note (scoped repair): `cluster.py` now uses the explicit
`five-means-v1` roster by default (four historical means plus HPS mean and required
sigma evidence), or explicitly requested `four-means-v1`. The roster is not
inferred from observed values. Under `completion-abstain-v1`, any missing required
quality output makes cohort consensus, disagreement and quality quantiles null;
all quality dispositions abstain because completion ranges/population effects
are unbounded. No surviving-scorer mean is computed. Per-row
`signal_unavailable:<field>` flags and cohort reasons survive CSV/report export.
Incomplete identity populations similarly suppress identity quantiles/quality
authorization. Observed safety/identity routes remain requests for human
assessment, not positive quality claims. Re-scoring clears stale missingness.

Evidence: [four-gap-regressions.json](evidence/four-gap-regressions.json), GAP-1.
The finite conflicting-completion regression checks the conservative rejection
path; continuous bounded unanimous authorization, memory-pressure scheduling and
certified execution switching are not certified by these tests. All-abstain is
sound without proof bounds, but no useful-coverage floor is claimed.
