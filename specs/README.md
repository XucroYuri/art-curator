> 中文摘要
> 本目录是规范入口，明确区分现状、目标与验证证据。
> 每条要求绑定验收标准；没有证据就不能宣称认证。
> 变更先审查语义与安全影响，再实现与发布。

# SPEC-driven development

Baseline inspected: 2026-09-20. These specifications encode the supplied architecture spine, grounded in the local implementation. They do not retroactively certify it. English is normative; summaries are explanatory.

## Index

| Document | Responsibility |
|---|---|
| [000-CONSTITUTION](000-CONSTITUTION.md) | Four invariants and precedence |
| [001-VISION](001-VISION.md) | Product scope and comparator lineage |
| [010-ARCHITECTURE](010-ARCHITECTURE.md) | Three identities, passes, tiers, failures |
| [011-CONTRACTS](011-CONTRACTS.md) | Scorers, workers, identities and persistence |
| [012-PERFORMANCE](012-PERFORMANCE.md) | Measured record, admission and hot paths |
| [030-UX](030-UX.md) | Human decisions and offline review |
| [040-QUALITY-GATES](040-QUALITY-GATES.md) | Nine gates, fixtures and worked requirement |
| [050-ROADMAP](050-ROADMAP.md) | Dependencies and graduation |
| [Identity v2](features/FR-IDENTITY-V2.md) | Profile-bound CPU/GPU character references |
| [Semantic search spike](features/FR-SEMANTIC-SEARCH.md) | Query-only Chinese search; WeMM vs SigLIP-crop preregistration |
| [Curation protocol](features/FR-CURATION-PROTOCOL.md) | Content-bound human decisions |
| [Interop](features/FR-INTEROP.md) | Explicit loss-aware exchange |
| [ADR-0001](adr/ADR-0001-isolated-scorer-environments.md), [ADR-0002](adr/ADR-0002-dry-run-first-moves.md), [ADR-0003](adr/ADR-0003-columnar-gzip-review.md) | Retrospective decisions, not new certification |
| [ADR-0004](adr/ADR-0004-gpu-fp32-admission-criterion.md) | Scoped CUDA FP32 admission with unchanged primary budgets |
| [FEATURE](templates/FEATURE.md), [ADR](templates/ADR.md), [BENCHMARK](templates/BENCHMARK.md), [CERTIFICATION](templates/CERTIFICATION.md), [ADVERSARIAL-REVIEW](templates/ADVERSARIAL-REVIEW.md), [RELEASE-EVIDENCE](templates/RELEASE-EVIDENCE.md) | Authoring forms |

## Requirement grammar and evidence convention

A normative record starts `### <ID> — <title>`, followed by an EARS sentence, scope/status, and `AC-<ID>-NN`. Supporting lists/tables in that record are part of its observable contract, not independently orphaned requirements. Elsewhere, descriptions are informative or explicitly inherit named records. `INV-*`, `FR-*`, `NFR-*` are requirement prefixes; `AC-*` are criteria, not requirements. Templates use placeholders, not allocated IDs.

`S:* / E:* / T0–T4` means all semantic profiles, all execution profiles and all resource tiers, including experimental ones. Unless overridden, records have this scope and status **proposed**. A proposed safety obligation still constrains future qualification; it is not a claim of implementation. Fixture aliases are defined in 040. `evidence/<AC-ID>.json` is the mandatory future artifact for each AC unless another artifact is explicitly named. These paths are logical release-bundle destinations, not files created by this documentation task. Missing artifacts mean unverified. Private evidence can be access-controlled, but the public manifest carries its digest, method and limitations without personal paths.

### NFR-SPEC-001 — Change and traceability lifecycle
When a normative behavior or claim changes, the maintainer shall update its stable requirement record, linked acceptance criteria, evidence manifest and impacted profile versions before release.

Scope: S:* / E:* / T0–T4. Status: proposed.
- Lifecycle: proposed → implemented (code/test links) → verified (passing scoped evidence); experimental means usable without a qualified claim; deferred means intentionally unscheduled. Regressions revoke verified status. Never recycle IDs; supersede with links.
- Changes include motivation, source-code gap, semantic versus execution impact, fixtures, predeclared comparators, adversarial review and ADR for architectural choices. Review precedes implementation; evidence follows execution; release checks the affected gates.
- Each feature/architecture rule traces to an AC, test method, immutable fixture identity/digest, comparator/budget, artifact and status. A source link or passing test count alone is not certification. `fast`, `robust`, `seamless`, `state-of-the-art` cannot stand alone as acceptance criteria.
- AC-NFR-SPEC-001-01: statically audit this tree and a candidate release manifest using fixture SPEC-TREE-v1; zero missing IDs, scope/status/AC/method/fixture/comparator/artifact fields and zero unbound normative rules; evidence `evidence/AC-NFR-SPEC-001-01.json`.

## Grounding and known discrepancies

Read sources: `src/artcurator/`, `tools/`, all seven test modules, `README.md`, `DESIGN.md`, `config.example.yaml`, `docs/apply.md`, `docs/pipeline/{wave2,hpsv3}.md`, `out/review/summary.md`. The 70-test result is historical, not rerun here.

| Current record | Reconciliation / target |
|---|---|
| README architecture and pass list say four scorers and omit HPSv3 | Code, HPS documentation and summary have five quality means; sigma is not a sixth scorer |
| Missing-score surviving-scorer renormalization | **Closed (scoped code gap)** — fixed explicit four/five-mean roster; missing required evidence has per-row `signal_unavailable:<field>` flags, and unknown completion bounds invalidate cohort quality statistics/tiers rather than reweight survivors. Tests: `tests/test_signal_degradation.py::test_missing_scorer_cannot_promote_queue`, `::test_conflicting_completion_grid_abstains`, and partial HPS tests. Evidence: [four-gap-regressions.json](evidence/four-gap-regressions.json), GAP-1; AC-FR-DEGRADE-001-02 subset. Resource-pressure scheduling/certified execution fallback remains unqualified under AC-FR-DEGRADE-001-01. |
| Requested SigLIP variant substitution | **Closed (scoped code gap)** — `models.load` records unavailable model/revision and re-raises the original failure; no alternate artifact is loaded. Tests: `tests/test_model_refusal.py::test_siglip_refuses_substitution` (three failure types), `::test_siglip_success_clears_previous_failure`. Evidence: [four-gap-regressions.json](evidence/four-gap-regressions.json), GAP-2; no-substitution subset of AC-FR-ARCH-001-01, not full profile/resume certification. |
| Cache filenames/dedup use `sha16`; CSV lacks full SHA | FR-STABLE-001 and FR-CACHE-001 require authoritative full hashes throughout |
| Worker success is process exit; workers write SQLite directly | FR-WORKER-001/FR-SCORER-001 require handshake and coordinator-owned state |
| Current PNG decoder discards ancillary ICC/EXIF | Not a certified orientation/color-managed canonicalizer; new rendering profile requires paired evidence |
| Count-bounded prefetch; 85% physical VRAM HPS allocator cap | Not the byte-bounded queues and availability-aware 80%/85% admission contract |
| Sequential family IDs | **Closed (scoped code gap)** — family IDs are full SHA256 digests of version-pinned grouping-profile ID plus sorted unique full member content IDs; `families.json` exports the digest inputs/schema. Tests: `tests/test_family_ids.py::test_family_ids_survive_unrelated_addition`, `::test_family_digest_uses_unique_full_hashes`, permutation/duplicate/profile/member-change cases. Evidence: [four-gap-regressions.json](evidence/four-gap-regressions.json), GAP-3; fixed-member subset of AC-FR-STABLE-001-01. |
| Transitive grouping / no blocked-search budget | **Still open** — bridges can merge member sets and necessarily change snapshot IDs; no stable-membership or bounded-search claim. FR-STABLE-001 and NFR-DATA-001 limitations remain explicit. |
| JSONL truncation fails closed with manual recovery; SQLite view/default migration | Not ordered journal recovery or versioned migrations under FR-PERSIST-001 |
| Raw HPS mu/sigma omitted from gallery | **Closed (scoped code gap)** — `build_gallery.py` preserves raw values in `hm`/`hs`, renders Chinese-labelled inspector/table/detail fields and legend, distinguishes missing from zero, and derives detail field counts. Unknown fields remain tolerated, row counts unchanged. Tests: `tests/test_gallery_hps.py::test_gallery_hps_round_trip`, `::test_legacy_gallery_exposes_missing_hps`, `::test_hps_detail_and_inspector_dom`. Evidence: [four-gap-regressions.json](evidence/four-gap-regressions.json), GAP-4; HPS visibility subset of AC-FR-UX-001-01, not browser visual/accessibility certification. |
| 0.09513 → 0.04149 s/img quoted alongside 4.02× | Different baselines: their ratio is about 2.29×; paired 300-image baseline is 0.16683 s/img |

The original documentation baseline did not change code or output artifacts. The
scoped repairs above change authored code/tests/docs only; no corpus or existing
run artifacts were regenerated. The evidence receipt distinguishes unit/DOM
regressions from the broader proposed acceptance criteria and release gates.
