# G2 mode negotiation: client data contract (experimental)

Governing contract: `specs/features/FR-ALBUM-NEGOTIATE.md`. This document defines the
**data a client surface renders and sends back**; it does not build the surface. English
is normative here except the quoted Chinese copy, which is required user-facing data.

Implemented today: measured post-analysis report, explicit snapshot-bound consent
receipt, dismissal and retraction, CLI transport. **Not implemented:** any mapping
execution (G4), review/archive lanes (G4/G6), batch undo (G5) and contextual grouping
(ADR-0005 stays disabled; `context_enabled` is always `false`). A confirmed choice
records authority only; it changes no image, mapping, cache or score.

## Where the JSON lives

```powershell
.venv\Scripts\python.exe -m artcurator.cli ingest-run --input C:\synthetic --corpus demo --inventory-only
.venv\Scripts\python.exe -m artcurator.cli ingest-negotiate --corpus demo
.venv\Scripts\python.exe -m artcurator.cli ingest-confirm   --corpus demo --decision decision.json
.venv\Scripts\python.exe -m artcurator.cli ingest-dismiss   --corpus demo
.venv\Scripts\python.exe -m artcurator.cli ingest-retract   --corpus demo --actor local:me
```

* `ingest-negotiate` prints exactly one `NegotiationReport` JSON object (the same object
  is atomically stored at `out/ingest/<corpus>/negotiation/reports/<report_digest>.json`;
  `job.json.negotiation.report_path` is the authoritative relative path).
* `ingest` / `ingest-run` write `out/ingest/<corpus>/initial-intent.json`: a `Presentation`
  containing only `text.ingest_prompt` and `text.g2_boundary`. Render the proactive
  prompt from that object; it is intent, not consent.
* The client MUST treat every JSON string as data. Do not hardcode copy in markup and
  do not re-key by locale: render `presentation.text` and `presentation.folder_text`
  verbatim, or wait for a locale-specific report.

## Report object (what the surface renders)

Top level of `NegotiationReport`, `schema_version = "album-negotiation-v1"`:

| Field | Type | Client obligation |
|---|---|---|
| `report_digest` | sha256 | Echo it back in `Decision.report_digest`; display staleness, never recompute |
| `snapshot_digest`, `analysis_profile_digest`, `seal_digest`, `profile_digest` | sha256 | Bind the report to the frozen corpus and policy; all four are echoed back |
| `g1_report_ref` | path | Link to the sealed G1 analysis report |
| `labels`, `labels_digest` | object | Human labels actually used; empty means measurements are visual/weak only |
| `global_evidence` | object | Global counts and denominators (table below) |
| `folders[]` | array | One measured report per directory, including `.` |
| `clusters[]` | array | Every frozen cluster, eligible or not; `remaining_cluster_ids` is the route to all others |
| `eligible_cluster_ids` | int[] | Clusters passing `coherent-cluster-v1`; not an identity guarantee |
| `members[]` | array | Frozen `{image_id, occurrence_id, path, folder_id}` rows consent covers |
| `prediction` | object | `auto/review/none/audit/changed` are `null` with an explicit `reason` until G4/G5 exist |
| `recommendations` | object | Thresholds and highlight flags; `selects_for_user` is always `false` |
| `limitations[]` | string[] | Every limitation must be acknowledged in the decision |
| `presentation` | object | Copy-as-data and choice controls; render the strings verbatim |

`global_evidence`: `files`, `unique_images`, `faces` (null when no detector evidence),
`processed_images`, `unavailable_occurrences`, `decode_failed_images`, `scope`,
`whole_image_denominator`/`whole_image_unknown`/`whole_image_conflict` (null with
`missing_vocabulary` when G1 has no corpus-wide vocabulary measurement),
`crop_candidate_denominator`, `crop_unknown`, `crop_conflict` (crop denominators are
separate and never pooled with whole-image numbers), `unavailable_signals`,
`model_profiles`, `costs`.

`folders[]` fields: `folder_id`, `path`, `population_ids`, `population_digest`, `sample_ids`,
`sample_digest`, `seed`, `design` (seeded SRS without replacement, ≤100 distinct hashes),
`population`, `sample`, `occurrences`, `duplicates`, `unavailable_occurrences`, `coverage`,
`vector_profile`, `representation`, `coherence`, `purity`, `purity_identity`,
`independent_labels`, `unresolved_labels`, `target`, `target_purity`, `weak_agreement`,
`unresolved_proxy_D`, `unknown_U`, `conflict_C`, `model_coverage`, `artist_agreement`,
`regimes`, `coherence_admitted`, `identity_prior_admitted`, `identity_recommendation`,
`context_enabled` (always `false`), `manual_collection_available` (always `true`),
`thresholds`, `limitations`.

`clusters[]` fields: `cluster_id`, `member_digest`, `image_ids`, `face_ids`, `unique_images`,
`faces`, `outlier_fraction`, `coherence`, `eligible`, `eligibility_reasons`,
`representation`, `representatives[]` (`image_id`, `face_id`, `image_ref`, `crop_ref`;
`min(12, image count)`, medoid then lowest coherence then farthest-point, full-hash
tie-break), `candidates[]`, `names[]`, `source_concentration`, `source_concentration_basis`,
`reference_support_ref`, `profile`.

### Proportion, coherence and regime values

Every measured fraction is an object `{numerator, denominator, value, interval, method, limits}`.

* `method = "unavailable"` → `value`/`interval` are `null`; render `未知` (reason shown
  from context) or `不适用`. Never render `0%`/`100%` for an unavailable value.
* `method = "census-exact"` → `interval` is `null`; it is a descriptive fraction of the
  population, **not** a model-correctness interval.
* `method = "Wilson-95%-z=1.96-SRS"` → render `interval` with its stated limitations.
* `unresolved_labels` stays in the purity denominator; `purity_identity` names the
  count used. No labels means identity purity is unavailable, and weak agreement is
  never relabelled purity.
* `coherence.scores` is one nullable cosine per sampled image; `medium`/`p10` are the
  gates. Regimes are `heuristic/unvalidated` with `confidence: null`; `status` is one of
  `recommended`, `ambiguous`, `undetermined`, `insufficient-evidence`.

## Presentation object (copy as data)

`presentation` contains: `locale` (`"zh-CN"`), `templates` (every literal with `{braces}`
unbound), `text` (bound, no braces; import into the surface as-is), `modes[]` and
`scopes[]` (each `{id, label, consequences[], available}`), `default_mode`
(`"human-first"`), `default_scope` (`"none"`), `affirmative_required` (`true`),
`mapping_action_available` (`false` in G2), `folder_text` (per-`folder_id` bound
`measured_evidence` line).

Required literals (also exact in `tests/test_negotiation_copy.py`):

| `text` key / control | Render where |
|---|---|
| `ingest_prompt` `这批图片希望怎样整理？分析后会再次请你确认，不会自动移动原文件。` | Proactive first prompt |
| `modes[].label` `人审优先` / `自动优先` / `仅继承目录` | Mode choice controls |
| `scopes[].label` `全继承` / `逐目录勾选` / `不继承` | Inheritance controls |
| `coherent_clusters` `发现 {count} 个视觉较一致的分组，共 {images} 张图片。分组不等于同一角色，请先确认名称或拆分。` | Cluster section; already bound |
| `folder_text[<id>]` `测量依据：{method}；样本 {sample}/{population}；证据覆盖 {coverage}；置信说明：{confidence}。` | Per-folder evidence; already bound |
| `purity_missing` | When no independent labels make identity purity available |
| `inheritance_warning` | Beside inheritance controls |
| `auto_warning` | When `auto-first` is selected |
| `model_tier` `模型建议（未核实）` | Model-sourced candidate labels |
| `reference_tier` | Reference/memory tier explanation |
| `conflict` | Demoted/contested cluster or folder rows |
| `confirmation` `将新增或修改 {changed} 张图片的虚拟映射，{review} 张待审，{none} 张保留未解决；原文件不变。` | Confirm dialog; bound with `未知` while G4 has no counts |
| `commit_action` `确认并建立虚拟映射` | Confirm control label |
| `dismiss` `暂不决定` | Dismiss control label |
| `undo` `撤销本批映射` | Reserved for G5 batch undo; do not offer the action in G2 |
| `g2_boundary` | Status line: consent recorded, no mapping built |

Rendering rules: unavailable values are `未知`/`不适用` with a reason, never zero by
default; no percentage may be labelled identity confidence; `mapping_action_available:
false` means the surface may show `commit_action` as disabled/locked, never as an
executed mapping; `affirmative_required: true` means no default, timeout, window close
or restored preference ever fills the decision. Control-width/keyboard acceptance
(520/900/1440, keyboard-only) is owned by the visual task.

## Decision object (what the surface sends back)

The surface writes one JSON file and passes it as `--decision`. There is no other
confirmation channel; absence of a response leaves `job.json.progress.stage = CONFIRM`.

```json
{
  "actor": "local:<user-or-client-id>",
  "operation_id": "<one fresh id per confirmation attempt>",
  "affirmative": true,
  "report_digest": "<from report>",
  "snapshot_digest": "<from report>",
  "profile_digest": "<from report>",
  "mode": "human-first | auto-first | inherit-only",
  "inheritance": "all | selected | none",
  "folders": [{"folder_id": "<64-hex>", "relation_type": "work|artist|original-series|character|ordinary-person|undetermined", "descendants": "current-snapshot|direct-only"}],
  "threshold_overrides": [],
  "cost_ceiling_seconds": 0,
  "acknowledged": ["<every entry of report.limitations>"]
}
```

Rules the client must honor (all fail closed server-side):

* `affirmative` must be the literal `true`; omission is rejected.
* `folders` is empty only with `inheritance: "none"`; `"all"` must list **every** report
  folder exactly once; `"selected"` freezes exactly the checked `folder_id`s.
* `descendants` defaults to `current-snapshot`; future files are never covered — a new
  member requires a new report and receipt.
* `threshold_overrides` must stay empty; constitutional minima cannot be lowered.
* `acknowledged` must cover all `report.limitations`; the surface must display them first.
* One `operation_id` per decision. Replay of the identical decision returns the same
  receipt; reuse with different content, a second decision while consent is active, or
  a digest mismatch is refused with a stable `IngestError`.
* Changing labels, re-running analysis or adding members makes the report stale: the
  old receipt can no longer authorize anything (`authorize`/`confirm` fail closed).
  Retract explicitly (`ingest-retract --actor ...`) before a new choice.

## Confirmation receipt (what the surface may display)

`ingest-confirm` prints `ConsentReceipt`: `receipt_id`, `decision` (echo), `timestamp`,
`status` (`active`), `consequences[]` (machine tokens including `context-disabled`,
`G4-execution-guarded`, `no-source-writes`), `members[]`, `inherited[]` (each with
`source: "inherited"`, `verified: false`, `measurement_ref`, `effect:
"pending-human-directed-collection"`), `predicted` (`null` counts + G4 reason),
`evidence_refs[]`, `context_enabled: false`, `mapping_mutations: 0`. After confirmation
`progress.stage` shows `FIRST-PASS` but `status` stays `paused` and `reason` states that
execution is not implemented; the surface must present the job as awaiting G4, not done.

## Realistic fixture

Full contract example: `tests/fixtures/negotiation-report.example.json` (validated by
`tests/test_negotiation_copy.py`). It is generated from the synthetic ALBUM-FLOW-v1
recipe (two rectangles plus one duplicate copy) with one synthetic human label and no
model signals, so model-dependent fields are explicitly unavailable:

```json
{
  "schema_version": "album-negotiation-v1",
  "report_digest": "<sha256>", "snapshot_digest": "<sha256>",
  "labels": {"snapshot_digest": "<sha256>", "labels": [{"image_id": "<sha256>", "identity": "示例角色",
    "actor": "local:example", "evidence_ref": "human:example", "independent": true}],
    "targets": {"<folder-a-id>": "示例角色"}, "target_types": {"<folder-a-id>": "character"}},
  "global_evidence": {"files": 3, "unique_images": 2, "faces": null, "crop_candidate_denominator": 0,
    "crop_unknown": {"numerator": null, "denominator": 0, "value": null, "interval": null, "method": "unavailable", "limits": "…"}},
  "folders": [{"path": "folder-a", "population": 1, "sample": 1, "duplicates": 1,
    "purity": {"numerator": 1, "denominator": 1, "value": 1.0, "interval": null, "method": "census-exact"},
    "purity_identity": "示例角色", "unresolved_labels": 0, "context_enabled": false,
    "regimes": {"profile": "folder-regime-v1", "status": "insufficient-evidence", "confidence": null}}],
  "recommendations": {"eligible_clusters": 0, "cluster_coverage": null, "highlight_human_first": false,
    "highlight_inheritance": false, "selects_for_user": false},
  "prediction": {"auto": null, "review": null, "none": null, "audit": null, "changed": null,
    "reason": "Unknown: G4 policy not implemented; no mapping changes in G2.", "estimate": true},
  "presentation": {"locale": "zh-CN", "default_mode": "human-first", "default_scope": "none",
    "affirmative_required": true, "mapping_action_available": false,
    "text": {"ingest_prompt": "这批图片希望怎样整理？分析后会再次请你确认，不会自动移动原文件。",
      "confirmation": "将新增或修改 未知 张图片的虚拟映射，未知 张待审，未知 张保留未解决；原文件不变。", "…": "…"}}
}
```

Abridged; the fixture contains the complete arrays, `templates`, `folder_text` and every
literal above. Do not construct a report client-side from this excerpt.

## Honest limits

* No rendered client, DOM snapshot, width or keyboard verification exists here; AC-004-01
  remains partial until the visual task supplies that evidence.
* No labelled ALBUM-FOLDER-v1/ALBUM-CONFUSABLE-v1 precision run exists; cluster/regime
  numbers are measured but uncalibrated.
* Predicted tier counts, cost enforcement and mapping changes are unavailable, not zero;
  `prediction.*` is `null` by design.
* Contextual grouping never activates in G2; manual directory organization remains
  available through the same report (`manual_collection_available: true`).
