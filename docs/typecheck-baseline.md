# Type-check baseline (basedpyright)

Status: **measurement only — the gate is not clean and no source file was modified.**
First full-project basedpyright run for this repository. Created 2026-09-22 after the
maintainer approved installing basedpyright (all earlier receipts recorded "LSP
diagnostics unavailable — basedpyright is not installed; the previous decline was
respected"). This note records the environment, the configuration, the observed
baseline, a triage of the findings, and a phased plan.

## How to reproduce

Run from the repository root (PowerShell):

```powershell
# 1. runner environment (isolated; do NOT install into .venv)
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv venv --python 3.12 .venv-typecheck
uv pip install --python .venv-typecheck\Scripts\python.exe basedpyright==1.40.1

# 2. the gate
.venv-typecheck\Scripts\basedpyright.exe

# 3. machine-readable baseline (used for the counts below)
.venv-typecheck\Scripts\basedpyright.exe --outputjson > baseline.json

# 4. optional ad-hoc subset run (first target, see plan)
.venv-typecheck\Scripts\basedpyright.exe src\artcurator
```

The CLI exits non-zero (1) because errors exist; a clean gate is exit code 0.
Configuration is resolved from `pyproject.toml` (`[tool.basedpyright]`); no
`pyrightconfig.json` exists (a JSON config would silently take precedence over the
`pyproject.toml` block, so the project keeps a single source of truth).

## Environment

- **Runner**: `.venv-typecheck\` (gitignored by the `.venv*/` pattern), basedpyright
  **1.40.1** (based on pyright 1.1.414), Python 3.12.13, installed with `uv` following
  the repository convention (`uv venv --python 3.12 .venv-<name>` as in
  `CONTRIBUTING.md`). The only packages in that environment are `basedpyright` and
  its `nodejs-wheel-binaries` dependency.
- **Import-resolution environment**: `.venv` (the pinned main environment, Python
  3.12.13, see `environment-versions.json` → `main`). This is what
  `venvPath`/`venv` point at so third-party imports (torch, transformers, numpy,
  pydantic, …) and the editable `artcurator` install resolve. `.venv` was **read
  only** during this pass; nothing was installed into it.
- `.venv-check`, `.venv-ci`, `.venv-qrealign`, `.venv-hpsv3`, … are not used by the
  gate. `hpsv3`-only imports remain unresolved by design (those modules live in
  `.venv-hpsv3`); see the environment records in the triage.

## Configuration and justification

`pyproject.toml`:

```toml
[tool.basedpyright]
pythonVersion = "3.12"
venvPath = "."
venv = ".venv"
include = ["src/artcurator", "tools", "tests"]
exclude = [".venv*", ".test-tmp", ".uv-cache", "out", "dist"]
typeCheckingMode = "all"
```

| Setting | Value | Justification |
|---|---|---|
| `pythonVersion` | `"3.12"` | `pyproject.toml` pins `requires-python = ">=3.12,<3.13"`; ruff target is `py312`. Pre-existing setting, kept. |
| `venvPath` + `venv` | `"."` + `".venv"` | Third-party and editable-package resolution must use the pinned main env, which holds the full dependency set. Kept from the pre-existing block; the isolated `.venv-typecheck` deliberately has no dependencies. |
| `include` | `src/artcurator`, `tools`, `tests` | Expanded from the pre-existing `["src"]`. Gates the shipped package and the two other committed Python trees; `tools` and `tests` are 133 of 217 Python files. |
| `exclude` | `.venv*`, `.test-tmp`, `.uv-cache`, `out`, `dist` | `out/` alone contains 62 generated `.py` files; the rest are caches/envs/build products. Pyright keeps its own defaults (`**/node_modules`, `**/__pycache__`, `**/.*`, auto-detected venvs) on top of these. |
| `typeCheckingMode` | `"all"` | Pre-existing setting and basedpyright's strictest preset; it enables the `reportAny`/`reportUnknown*` family that exposes the annotation debt quantified below. Left unchanged for an honest baseline. |

`strict`/`extraPaths` are deliberately absent: the include set plus the editable
install already resolve `artcurator` (verified on a single-file run before the full
run), and `pythonPlatform` keeps the default `All` so Windows-only branches are not
newly excluded.

## Baseline results (2026-09-22)

Summary from the JSON report: **217 files analyzed, 4,938 errors, 0 warnings,
0 information, 82.5 s**. All diagnostics are severity `error` because
`typeCheckingMode = "all"` promotes every enabled rule. 199 of 217 files have at
least one diagnostic; **13 of 114 `src/artcurator` files are already clean**.

| Directory | Diagnostics | Share |
|---|---:|---:|
| `src/artcurator` | 1,641 | 33.2% |
| `tests` | 2,790 | 56.5% |
| `tools` | 507 | 10.3% |

### All 42 rules, by count and directory

| Count | Rule | src | tests | tools |
|---:|---|---:|---:|---:|
| 2,010 | `reportAny` | 537 | 1,242 | 231 |
| 554 | `reportUnusedCallResult` | 209 | 305 | 40 |
| 496 | `reportUnknownArgumentType` | 224 | 230 | 42 |
| 484 | `reportUnknownMemberType` | 236 | 195 | 53 |
| 363 | `reportUnknownVariableType` | 185 | 136 | 42 |
| 195 | `reportArgumentType` | 45 | 110 | 40 |
| 124 | `reportUnknownParameterType` | 17 | 100 | 7 |
| 110 | `reportIndexIssue` | 1 | 109 | 0 |
| 108 | `reportMissingParameterType` | 2 | 103 | 3 |
| 50 | `reportImplicitRelativeImport` | 0 | 45 | 5 |
| 46 | `reportImplicitStringConcatenation` | 26 | 5 | 15 |
| 46 | `reportOptionalMemberAccess` | 0 | 46 | 0 |
| 38 | `reportUnannotatedClassAttribute` | 34 | 3 | 1 |
| 38 | `reportOptionalSubscript` | 0 | 38 | 0 |
| 25 | `reportCallIssue` | 0 | 25 | 0 |
| 23 | `reportUnnecessaryComparison` | 23 | 0 | 0 |
| 23 | `reportUnknownLambdaType` | 2 | 21 | 0 |
| 22 | `reportPrivateLocalImportUsage` | 3 | 17 | 2 |
| 22 | `reportMissingTypeArgument` | 17 | 1 | 4 |
| 21 | `reportDeprecated` | 20 | 1 | 0 |
| 21 | `reportAttributeAccessIssue` | 3 | 12 | 6 |
| 17 | `reportUnusedParameter` | 3 | 13 | 1 |
| 17 | `reportUnusedImport` | 4 | 11 | 2 |
| 15 | `reportMissingTypeStubs` | 14 | 0 | 1 |
| 14 | `reportImportCycles` | 14 | 0 | 0 |
| 8 | `reportMatchNotExhaustive` | 2 | 6 | 0 |
| 8 | `reportPossiblyUnboundVariable` | 4 | 4 | 0 |
| 7 | `reportExplicitAny` | 4 | 3 | 0 |
| 4 | `reportPrivateUsage` | 1 | 3 | 0 |
| 4 | `reportOperatorIssue` | 1 | 2 | 1 |
| 3 | `reportAssignmentType` | 1 | 0 | 2 |
| 3 | `reportReturnType` | 0 | 1 | 2 |
| 3 | `reportGeneralTypeIssues` | 0 | 0 | 3 |
| 3 | `reportConstantRedefinition` | 0 | 0 | 3 |
| 2 | `reportInvalidTypeForm` | 1 | 1 | 0 |
| 2 | `reportMissingImports` | 2 | 0 | 0 |
| 2 | `reportImplicitOverride` | 2 | 0 | 0 |
| 2 | `reportUnreachable` | 2 | 0 | 0 |
| 2 | `reportUnusedVariable` | 0 | 2 | 0 |
| 1 | `reportCallInDefaultInitializer` | 1 | 0 | 0 |
| 1 | `reportOptionalOperand` | 1 | 0 | 0 |
| 1 | `reportUnnecessaryIsInstance` | 0 | 0 | 1 |

### Full per-file counts

<details>
<summary>All 199 files with diagnostics (click to expand)</summary>

| File | Diagnostics |
|---|---:|
| `tests\test_album_archive_recovery.py` | 187 |
| `tests\test_gallery_candidates.py` | 148 |
| `tests\test_first_pass_boundaries.py` | 143 |
| `tests\test_first_pass_policy.py` | 136 |
| `tests\test_ingest.py` | 132 |
| `tests\test_negotiation_adr.py` | 127 |
| `tests\test_first_pass_execution.py` | 123 |
| `tests\test_identity_grouping_exports.py` | 113 |
| `tests\test_album_archive_adversarial.py` | 109 |
| `tests\test_album_archive.py` | 103 |
| `tests\test_negotiation_flow.py` | 95 |
| `tests\test_gallery_payload.py` | 94 |
| `src\artcurator\first_pass_mapping.py` | 93 |
| `tests\test_wd_cache_layers.py` | 91 |
| `tests\test_album_archive_policy.py` | 79 |
| `tools\build_cluster_fixture.py` | 79 |
| `src\artcurator\cli.py` | 74 |
| `tests\test_negotiation_clusters.py` | 72 |
| `src\artcurator\hpsv3_model.py` | 68 |
| `tests\test_identity_v2_memory.py` | 68 |
| `tests\test_negotiation_consent.py` | 67 |
| `src\artcurator\album_map_recovery.py` | 66 |
| `tools\certify_identity.py` | 66 |
| `tests\test_identity_grouping.py` | 65 |
| `tests\test_album_archive_conflicts.py` | 64 |
| `tools\negotiation_evidence.py` | 61 |
| `src\artcurator\album_map.py` | 59 |
| `src\artcurator\ingest_cli.py` | 55 |
| `src\artcurator\models.py` | 54 |
| `tools\certify_identity_fp32.py` | 53 |
| `src\artcurator\identity_group_math.py` | 52 |
| `tools\build_gallery.py` | 52 |
| `src\artcurator\album_map_cli.py` | 50 |
| `src\artcurator\identity_embed.py` | 50 |
| `tests\test_identity.py` | 46 |
| `tests\test_album_recovery.py` | 42 |
| `tests\test_apply.py` | 41 |
| `tests\test_negotiation_metrics.py` | 40 |
| `tests\test_identity_profiles.py` | 39 |
| `src\artcurator\scan.py` | 38 |
| `tests\test_negotiation_copy.py` | 38 |
| `src\artcurator\identity_cluster.py` | 37 |
| `src\artcurator\identity_detector.py` | 36 |
| `src\artcurator\report.py` | 36 |
| `tests\test_gallery_clusters.py` | 36 |
| `src\artcurator\identity_report.py` | 34 |
| `tests\test_negotiation_cli.py` | 32 |
| `src\artcurator\verify.py` | 31 |
| `tests\test_identity_candidates.py` | 30 |
| `tests\test_album_clusters.py` | 29 |
| `tools\build_negotiation_demo.py` | 29 |
| `src\artcurator\apply.py` | 28 |
| `src\artcurator\identity_anchor.py` | 28 |
| `src\artcurator\wd_worker.py` | 28 |
| `tests\test_ingest_recovery.py` | 28 |
| `src\artcurator\first_pass_policy.py` | 26 |
| `tools\benchmark_pipeline.py` | 26 |
| `src\artcurator\album_map_discovery.py` | 24 |
| `src\artcurator\alias_candidates.py` | 24 |
| `src\artcurator\identity_store.py` | 23 |
| `tests\test_architecture_worker.py` | 23 |
| `src\artcurator\negotiation_report.py` | 22 |
| `tests\test_pipeline.py` | 21 |
| `tools\publish_identity_certificate.py` | 21 |
| `src\artcurator\ingest_storage.py` | 20 |
| `src\artcurator\worker_runtime.py` | 20 |
| `tools\ingest_evidence.py` | 20 |
| `src\artcurator\album_map_storage.py` | 19 |
| `src\artcurator\identity_anchor_sources.py` | 19 |
| `src\artcurator\identity_group.py` | 19 |
| `tests\test_architecture_identity.py` | 19 |
| `tests\test_identity_edges.py` | 19 |
| `tests\test_pipeline_edges.py` | 19 |
| `src\artcurator\_moves.py` | 18 |
| `src\artcurator\identity_candidates_v2.py` | 18 |
| `src\artcurator\negotiation_clusters.py` | 18 |
| `tests\test_alias_reconciliation.py` | 18 |
| `tests\test_gallery_hps.py` | 18 |
| `src\artcurator\cluster.py` | 17 |
| `src\artcurator\wd_cache.py` | 17 |
| `src\artcurator\album_map_vectors.py` | 16 |
| `tests\test_wd_tagger.py` | 16 |
| `tools\album_mapping_evidence.py` | 16 |
| `src\artcurator\album_map_clusters.py` | 15 |
| `src\artcurator\album_map_exchange.py` | 15 |
| `src\artcurator\cache.py` | 15 |
| `src\artcurator\config.py` | 15 |
| `src\artcurator\ingest.py` | 15 |
| `src\artcurator\negotiation_cli.py` | 14 |
| `tools\hpsv3_receipt.py` | 14 |
| `src\artcurator\album_archive_plan.py` | 13 |
| `src\artcurator\identity_labels.py` | 13 |
| `src\artcurator\negotiation_sources.py` | 13 |
| `src\artcurator\wd_projection.py` | 13 |
| `tests\test_gallery_negotiation.py` | 13 |
| `tests\test_album_discovery_lineage.py` | 12 |
| `tests\test_album_pool_boundaries.py` | 12 |
| `tests\test_contract.py` | 12 |
| `tools\pipeline_receipt.py` | 12 |
| `src\artcurator\db.py` | 11 |
| `src\artcurator\ingest_adapters.py` | 11 |
| `src\artcurator\resources.py` | 11 |
| `src\artcurator\score.py` | 11 |
| `src\artcurator\undo.py` | 11 |
| `tools\probe_hpsv3.py` | 11 |
| `src\artcurator\album_map_browser.py` | 10 |
| `tests\test_album_promotion.py` | 10 |
| `tests\test_architecture_persistence.py` | 10 |
| `src\artcurator\identity_candidates.py` | 9 |
| `src\artcurator\migrations.py` | 9 |
| `src\artcurator\negotiation_metrics.py` | 9 |
| `src\artcurator\qrealign_worker.py` | 9 |
| `src\artcurator\references.py` | 9 |
| `src\artcurator\wd_exchange.py` | 9 |
| `tests\test_alias_evidence.py` | 9 |
| `tests\test_ingest_controls.py` | 9 |
| `src\artcurator\ingest_runtime.py` | 8 |
| `tests\test_negotiation_folders.py` | 8 |
| `tools\check_identity_labels.py` | 8 |
| `tools\run_identity_gpu.py` | 8 |
| `src\artcurator\first_pass_audit.py` | 7 |
| `src\artcurator\journal.py` | 7 |
| `src\artcurator\memory_curation.py` | 7 |
| `src\artcurator\worker_protocol.py` | 7 |
| `tests\test_album_adapters.py` | 7 |
| `tests\test_alias_cli.py` | 7 |
| `tests\test_architecture_resources.py` | 7 |
| `tests\test_build_gallery.py` | 7 |
| `tests\test_conservative.py` | 7 |
| `tests\test_model_refusal.py` | 7 |
| `src\artcurator\identity_candidate_report.py` | 6 |
| `src\artcurator\isolated_score.py` | 6 |
| `src\artcurator\wd_benchmark.py` | 6 |
| `tests\test_album_cluster_conflicts.py` | 6 |
| `tests\test_album_g3_cli.py` | 6 |
| `tests\test_album_store.py` | 6 |
| `tests\test_family_ids.py` | 6 |
| `tests\test_ingest_inference.py` | 6 |
| `tests\test_ingest_process.py` | 6 |
| `src\artcurator\album_map_promotion.py` | 5 |
| `src\artcurator\candidates_schema_v2.py` | 5 |
| `src\artcurator\identity_schema.py` | 5 |
| `tests\test_album_discovery.py` | 5 |
| `tests\test_album_vectors.py` | 5 |
| `tests\test_hpsv3.py` | 5 |
| `tools\alias_receipt.py` | 5 |
| `tools\build_alias_demo.py` | 5 |
| `tools\summarize_identity_runs.py` | 5 |
| `src\artcurator\album_archive_ledger.py` | 4 |
| `src\artcurator\alias_reconciliation.py` | 4 |
| `src\artcurator\character_memory.py` | 4 |
| `src\artcurator\identity_group_export.py` | 4 |
| `src\artcurator\ingest_profile.py` | 4 |
| `src\artcurator\negotiation.py` | 4 |
| `src\artcurator\negotiation_authority.py` | 4 |
| `src\artcurator\previews.py` | 4 |
| `tests\test_album_archive_cli.py` | 4 |
| `tests\test_album_contracts.py` | 4 |
| `tests\test_identity_admission.py` | 4 |
| `tests\test_ingest_state.py` | 4 |
| `tools\check_aesthetic_upgrade.py` | 4 |
| `tools\run_identity_grouping.py` | 4 |
| `src\artcurator\album_archive.py` | 3 |
| `src\artcurator\album_map_schema.py` | 3 |
| `src\artcurator\identity_profiles.py` | 3 |
| `src\artcurator\identity_tag.py` | 3 |
| `src\artcurator\ingest_schema.py` | 3 |
| `tests\test_album_browser.py` | 3 |
| `tests\test_anchor_crops.py` | 3 |
| `tests\test_gallery_aliases.py` | 3 |
| `tools\conservative_receipt.py` | 3 |
| `src\artcurator\album_contracts.py` | 2 |
| `src\artcurator\album_map_protocol.py` | 2 |
| `src\artcurator\identity.py` | 2 |
| `src\artcurator\ingest_process.py` | 2 |
| `src\artcurator\negotiation_copy.py` | 2 |
| `src\artcurator\parallel.py` | 2 |
| `src\artcurator\receipt.py` | 2 |
| `src\artcurator\worker_adapter.py` | 2 |
| `tests\test_album_receipts.py` | 2 |
| `tests\test_wd_exchange.py` | 2 |
| `tools\check_identity_grouping.py` | 2 |
| `tools\hpsv3_versions.py` | 2 |
| `src\artcurator\album_map_tray.py` | 1 |
| `src\artcurator\album_registry.py` | 1 |
| `src\artcurator\alias_schema.py` | 1 |
| `src\artcurator\first_pass.py` | 1 |
| `src\artcurator\first_pass_schema.py` | 1 |
| `src\artcurator\identity_admission.py` | 1 |
| `src\artcurator\identity_group_schema.py` | 1 |
| `src\artcurator\ingest_catalog.py` | 1 |
| `src\artcurator\negotiation_consent.py` | 1 |
| `src\artcurator\negotiation_regimes.py` | 1 |
| `src\artcurator\prefetch.py` | 1 |
| `src\artcurator\wd_schema.py` | 1 |
| `tests\test_album_registry.py` | 1 |
| `tests\test_model_suggestions.py` | 1 |
| `tests\test_signal_degradation.py` | 1 |
| `tools\build_demo.py` | 1 |

</details>

## Triage

Buckets are assigned per rule from the observed evidence (they sum to 4,938).
Counts are mechanical; the *verdicts* below are from manually inspecting code
context for every high-value finding, including all 45 `src` argument-type hits,
all `src` unreachable/unbound/assignment findings, and representative test/tools
findings.

| Bucket | Diagnostics | Share of total |
|---|---:|---:|
| (a) likely genuine defects | 478 | 9.7% |
| (b) annotation / signature debt | 3,721 | 75.4% |
| (c) false positives, config artifacts, strictness noise | 739 | 15.0% |

**Bucket (b) dominates (75.4%).** `reportAny` + the `reportUnknown*` family alone
are 3,477 diagnostics (70.4% of everything). The single largest `src`
concentrations are `first_pass_mapping.py` (74), `cli.py` (71),
`album_map_recovery.py` (66), `hpsv3_model.py` (59), `album_map.py` (55).

### (a) Likely genuine defects — verified highlights

Highest-value `src` findings (all `reportArgumentType` hits were inspected; most
turned out to be dict-as-kwargs inference, listed under (b)):

1. `src/artcurator/verify.py:64` — `assert 0 <= row.qrealign <= 1` where
   `qrealign: float | None`; the optional operand raises `TypeError` if the value is
   absent. Real `Optional` dereference in shipped code (only one in `src`).
2. `src/artcurator/identity_labels.py:56` — `payload` is first inferred as `bytes`
   (file read) and later assigned `event.model_dump(...)` (`dict[str, Any]`);
   variable reuse across incompatible shapes (`reportAssignmentType`).
3. `src/artcurator/candidates_schema_v2.py:97` — `version: Literal[2, 2.1] = 2.1`
   is an invalid type form (float literals are not allowed in `Literal`);
   reflects a real annotation/schema hole in `CandidateDocumentV2`.
4. `src/artcurator/worker_protocol.py:69` — the `output_contract`/`tensor_schema`/
   `provider` mismatch guard is **statically dead**: all three fields are
   single-value `Literal`s on both request and response, so the `raise` is
   unreachable. The type model already makes the mismatch unrepresentable; the
   runtime guard duplicates pydantic validation.
5. `src/artcurator/identity_profiles.py:70` — `case "cpu": return cpu` is
   unreachable after the early `if options.device == "cpu": return cpu` narrows the
   match subject. Harmless dead branch.
6. `src/artcurator/ingest_storage.py:100,102` — `msvcrt` / `fcntl` are "possibly
   unbound" because the platform imports are conditionally bound and repeated
   `os.name` checks are not narrowed. Runtime-guarded, but the analyzer is
   technically right; the fix is a single import boundary, not a suppression.
7. `src/artcurator/cli.py:14-15` — `sys.stdout.reconfigure(...)`: the `TextIO`
   protocol has no `reconfigure` (only `io.TextIOWrapper` does). Works in the normal
   CLI path; would break if stdout is replaced by a non-`TextIOWrapper`.
8. **14 import cycles** (`reportImportCycles`, all `src`, file-level): `_moves.py →
   journal.py`; `negotiation.py → negotiation_authority.py`; `qrealign_worker.py →
   worker_runtime.py`; and a 11-diagnostic cluster among
   `alias_candidates.py`, `alias_reconciliation.py`, `character_memory.py`,
   `identity_labels.py`, `identity_candidates_v2.py`, `memory_curation.py`,
   `identity_anchor.py`, `album_map_discovery.py → album_map_promotion.py`.
   Python permits these, but they are exactly the layering risk this project
   documents elsewhere; no runtime failures observed.
9. Test-code findings that are genuine type facts, not analyzer mistakes:
   `tests/test_apply.py:126` (`plan.moves[0].dst` is `Path | None`),
   `tests/test_first_pass_boundaries.py:102` (`after` is
   `MappingRecord | Support | None`; `.subjects` only exists on `MappingRecord`),
   `tests/test_negotiation_cli.py:44-56` (a yielding fixture annotated `-> Path`
   instead of `-> Iterator[Path]`). These 84 `Optional`-related test findings and
   25 `reportCallIssue`/110 `reportIndexIssue` hits in
   `tests/test_gallery_candidates.py`/`test_architecture_identity.py` all come from
   indexing dynamic JSON without narrowing.

### (b) Annotation / signature debt — the dominant bucket (3,721)

- `reportAny` (2,010): 537 `src`, 1,242 `tests`, 231 `tools`. Sources are
  argparse `Namespace` attributes, `json.loads`/`dict.get` round-trips, and
  unpinned/loosely typed model libraries (torch, transformers, pyiqa, onnxruntime).
- `reportUnknownArgumentType` (496) + `reportUnknownMemberType` (484) +
  `reportUnknownVariableType` (363) + `reportUnknownParameterType` (124): mostly
  numpy `ndarray[..., dtype[Unknown]]`, JSON values, and untyped decorators.
- `reportMissingParameterType` (108), `reportUnknownLambdaType` (23),
  `reportMissingTypeArgument` (22), `reportUnannotatedClassAttribute` (38)
- Dict-as-kwargs inference pattern: `src/artcurator/first_pass_mapping.py:66`
  (12 of the 45 `src` argument-type diagnostics at one call) and
  `src/artcurator/first_pass_policy.py:15,21,69,78,80` (10 diagnostics) pass a
  heterogeneous `dict(...)` via `**base`/`**fields`; each value is inferred as a
  union, so every keyword argument is flagged. Runtime-correct; a `TypedDict` (or
  explicit keyword arguments) clears these without suppression.
- `reportDeprecated` (21) — mostly `@contextmanager` with `-> Iterator[...]` return
  annotations and `typing.Iterator`; mechanical modernisation.
- `reportMissingTypeStubs` (15) — `accelerate` and peers without `py.typed`.

### (c) False positives / configuration artifacts / strictness noise (739)

- `reportUnusedCallResult` (554, basedpyright-exclusive rule enabled by
  `typeCheckingMode = "all"`): ignores return values of `.append()`, `.mkdir()`,
  `.update()`, … Sampled instances are harmless; rule policy decision needed.
- `reportImplicitRelativeImport` (50): `tests` has no `__init__.py`; sibling test
  modules are imported by file name. Runtime-correct under pytest.
- `reportImplicitStringConcatenation` (46), `reportPrivateLocalImportUsage` (22),
  `reportUnusedImport` (17), `reportUnusedParameter` (17), `reportPrivateUsage` (4),
  `reportUnusedVariable` (2) — style/dead-code hygiene, no runtime effect observed.
- `reportUnnecessaryComparison` (23): every instance is the project's deliberate
  exhaustive-match idiom (`case unreachable: assert_never(unreachable)` /
  `case _ as unreachable:`) in `src`; the rule does not recognise the capture form
  as the "assert unreachable" exemption. Analyzer artifact.
- Analyzer/stub limitations, verified by reading the code:
  `tools/build_gallery.py:433` (`all(isinstance(item, str) ...)` does not narrow the
  list element type — a documented pyright limitation with a loop workaround),
  `tools/build_gallery.py:1690` (`HTML_TEMPLATE` reassignment flagged as constant
  redefinition), `tools/build_gallery.py:1048` (`row["flags"]` on a `JsonValue`
  map), `src/artcurator/report.py:15` (typeshed `DictWriter` literal-key mapping vs
  `dict[str, Any]`), `src/artcurator/wd_worker.py:74` (onnxruntime `SparseTensor`
  indexing), `src/artcurator/models.py:65,86` + `identity_embed.py:71`
  (`.to("cuda")` resolved against an overload that takes `self`),
  `src/artcurator/hpsv3_model.py:96` (`bnb_4bit_compute_dtype` stub says `str`,
  torch dtype in fact accepted), `src/artcurator/worker_adapter.py:55`
  (`np.savez` `**kwargs` typing), `src/artcurator/undo.py:46` (`Path("...")` call in
  a default argument; immutable, safe).
- `reportMissingImports` (2, `src/artcurator/hpsv3_model.py:60-61`): `hpsv3` lives
  only in `.venv-hpsv3` (isolated scorer env by design). Environment artifact.

## What "clean gate" means here

Given the project rule **never suppress with `# type: ignore` / `as any` /
`@ts-expect-error`**, a clean gate means:

1. `basedpyright` exits **0** over the target file set with
   `typeCheckingMode = "all"` unchanged and zero diagnostics.
2. No inline ignore comments, no `cast(...)` used to silence, and no basedpyright
   `baselineFile` hiding findings (a hidden-suppression mechanism, same spirit as an
   inline ignore).
3. Where a third-party stub is wrong, fix the boundary (narrowing/guard/adapter),
   not the diagnostic.
4. Where a rule is genuinely wrong for this project, **turn the rule off in
   `pyproject.toml` with a written rationale** — an explicit, reviewable policy
   change, never a per-line bypass.

## Phased plan

| Phase | Scope | Effort (focused) | Exit criteria |
|---|---|---|---|
| 0 (done) | `.venv-typecheck`, config, this baseline | 0.5 day | reproduced numbers above |
| 1 | Rule-policy decisions: `reportUnusedCallResult`, `reportImplicitRelativeImport`, `reportMissingTypeStubs`, stub strategy, pinning basedpyright | 0.5–1 day | decisions recorded in this file; config edits only if justified |
| 2 | **`src/artcurator` only** → clean | 5–8 days | `basedpyright src\artcurator` → exit 0 |
| 2a | ~73 defect-class diagnostics (bucket (a) in `src`) and the import-cycle cluster | 1–2 days | defects fixed or explicitly reclassified |
| 2b | ~1,296 bucket (b): `reportAny`/`Unknown*`/missing annotations in ~20 files (`first_pass_mapping`, `cli`, `album_map*`, `hpsv3_model`, `models`, `identity_*`, …) | 3–5 days | no `Any`-family diagnostics in `src` |
| 2c | ~272 bucket (c) in `src` (209 `reportUnusedCallResult`, 26 implicit concatenation, leftovers) | 0.5–1 day | fixed or consciously disabled by policy |
| 3 | `tools` (507) | 1–2 days | `basedpyright tools` → exit 0 |
| 4 | `tests` (2,790; dynamic-JSON indexing, fixtures, `Optional` assertions) | 3–6 days | `basedpyright tests` → exit 0 |

Once Phase 2 lands, add the gate to CI as a narrow target (either
`basedpyright src\artcurator` or by narrowing `include`), then widen as later phases
land. Full-suite clean is realistically **2–4 weeks** of focused work; the tail is
uncertain because it depends on upstream stub quality (Phase 1 decisions).

### Recommended first target: `src\artcurator` only

- It is the shipped package (`[tool.hatch.build.targets.wheel]` packages it; the CLI
  entry point lives there); type errors there are product risk.
- It is already 33% of the total and 13/114 files are clean; the debt classes are
  concentrated and mostly mechanical (`Any` 537, `Unknown*` 662, `UnusedCallResult`
  209 = 86% of `src` findings).
- `tools/` are one-off operator scripts and `tests/` findings are 56.5% of the total
  and dominated by test-ergonomic patterns (dynamic JSON fixtures) that are the
  highest effort for the least product risk. Gating `src` first delivers a real
  regression signal instead of a year-long cleanup project.

## Open decisions

- **`reportUnusedCallResult` (554).** Keep as an error and fix mechanically, or
  disable by policy? It does not exist in pyright and produces the largest single
  block of noise.
- **Third-party `Any` sources.** Add stub packages where they exist, or declare the
  genuinely untyped libraries (`allowedUntypedLibraries`) with a written reason.
- **`reportImplicitRelativeImport` in tests.** Add `tests/__init__.py`, convert to
  relative imports, or disable for `tests`.
- **Version pinning** of basedpyright in the reproduction command (currently
  `1.40.1`).
- **Baseline file / ratchet.** Not used; the project's no-suppression rule argues
  against it. Confirm.

## Limits of this pass

- Measurement only: no file under `src/`, `tools/`, `tests/` was modified. The
  working tree also contains pre-existing edits to `docs/pipeline/album-mapping.md`
  and four `specs/evidence/*.json` files that were **not** made by this pass.
- Counts are tied to the `.venv` dependency set (`environment-versions.json` →
  `main`) and to basedpyright 1.40.1; a different resolution env changes the
  third-party findings.
- Effort estimates are judgement calls, not measurements.
- Whether the test-code `Optional` findings can fail at runtime was not exercised
  (the test suite was running in a separate task); they are latent, not observed
  failures.
- `hpsv3`-dependent code cannot be fully checked until a resolution strategy for
  the isolated scorer environment is chosen.
