> 中文摘要
> 枚举可选项，不强迫单一猜测；每张人脸展示前五候选、其他和新建角色。
> v2 中模型闭集枚举和用户视觉记忆并行；无参考也可启动，分数不是身份概率。
> 未通过现有门禁仍可人工选择，弃权不等于没有候选。
> 人物标签导出兼容，支持基准/变体标记；属性是独立的可观察证据，不决定身份。

# Feature: Enumerate identity candidates

## Version 2.1 amendment (normative)

### FR-CANDIDATES-008 — Honest cold-start model suggestions
When compact WD evidence passes `wd-score-margin-v1`, the coordinator shall emit
an additive `suggested_model`, independently of the unchanged visual suggestion gate.
Scope: pinned WD-compact-v1 / saved visual embeddings / experimental desktop.

- Envelope `version: 2.1` (JSON number); v2 input remains readable. All v2 fields
  retain their meanings. `suggested_verified` is the existing reference/memory-gated
  `suggested` value; `suggested` remains an identical compatibility alias.
  `abstained` still means **visual-tier abstention**, not absence of model advice.
  Older tolerant consumers ignore new fields and continue seeing only the old tier.
  Strict old `Literal[2]`/extra-forbid parsers require an update; additive compatibility
  does not imply that such parsers accept a minor version they explicitly reject.
- `suggested_model` is null or `{name, display, score, margin_vs_runner_up,
  margin_basis, gate: "wd-score-margin-v1", verified: false}`. It never becomes a
  confirmed label, a memory reference, or a verified suggestion automatically.
- Gate: top canonical WD character **score >= 0.85 AND margin >= 0.20**.
  Provenance: engineering policy selected before this rerun, not label-calibrated.
  The supplied production coverage at >.35 is 81.91% / 87.54% / 68.14%; .85 selects
  the stronger tail instead of promoting all enumerated candidates. The .20 gap
  rejects close closed-set competitors; it is a conservative separation heuristic,
  not an empirically certified accuracy optimum. No threshold promises correctness.
- Sort by score, canonicalize curated aliases, keep each identity's maximum score.
  Runner-up is the strongest other canonical identity. Compact output keeps only
  scores >.35; if absent, use **.35 as an upper bound**, never zero. In that case
  `margin_basis: runner-up-upper-bound-0.35` and the reported margin is a lower
  bound; otherwise `margin_basis: observed`. Exact .20 decimal boundaries pass.
- Adversarial supplied finding: `2b_(nier:automata)` occurs on 204 review faces,
  top-1 on 199, >.85 on 146, despite a different intended corpus subject. The new
  margin is **not** claimed to solve this domain-shift confusion. Report surviving
  occurrences separately; do not blacklist names or infer truth from corpus paths.

### FR-CANDIDATES-009 — Contradiction demotion and honest presentation
When independent visual/reference or confirmed evidence disagrees, the coordinator
shall retain the model proposal for audit but set `model_demoted: true` and record
`disagreements: [{model_name, evidence_name, source, score, reason}]`.

- Compare canonical names with strongest non-self memory and profile-validated
  folder/human references above cosine .35, even if they fail full verification.
  Tied leaders including the model are ambiguous, not contradictory; otherwise
  record all tied leaders. Existing confirmed assignment also takes precedence.
  Exact crop self-matches are excluded; excluded faces get no model proposal.
  Visual scores are never compared numerically with WD scores or fused with them.
- Demotion is conservative evidence disagreement, **not proof the model is wrong**.
  Folder references can demote but do not silently become curated memory or change
  the existing verified-tier gate. No independent evidence means an unverified
  model suggestion can be primary. Verified-tier advice always takes precedence.
- UI: warning-colour badge `模型建议（未核实）`, score and signed margin, with `≥`
  for a bound. Success-colour `已核实建议` denotes passing the existing reference/
  memory gate, not human confirmation or an accuracy certificate. Demoted advice
  appears in secondary conflict details, never as the primary suggestion.
- Explain both tiers in the honesty line. Preserve both source sections, fixed
  buckets, marks, keyboard/undo and single-file offline operation.
- AC-FR-CANDIDATES-008-01: analytic score/gap boundaries, empty/singleton/tie,
  legacy-v2 parsing, cold-start actual producer and reference-conflict tests in
  `tests/test_model_suggestions.py`. All model proposals have `verified: false`.
- AC-FR-CANDIDATES-009-01: regenerate three private snapshots and report proposal,
  primary/demotion, confusable counts and score/margin distributions in private
  `identity-candidates-report.json`; absence of labels forbids accuracy claims.
- AC-FR-CANDIDATES-009-02: regenerate fixture and three galleries, full root pytest,
  zero external asset references; browser checks for cold-start, demotion, narrow
  layout, keyboard/marks/undo and console errors. Fixture screenshots `docs/assets/v12-*`;
  real-data screenshots stay under `out/`. Measurements: `docs/model-suggestions.md`.

## Version 2 amendment (normative)

The following records supersede the v1 wire format and the reference-only/attribute-deferred
restrictions below. V1 records remain historical lineage, not the current JSON contract.
Scope: S: WD-compact-v1 + saved face-embedding retrieval / E: pinned local ONNX CPU/CUDA /
T: experimental desktop. Status: implemented experiment, not recognition certification.
The pipeline implementation does not change `tools/`; studio interaction qualification
belongs to the separate studio task.

### FR-CANDIDATES-005 — Parallel model and memory sources, v2
When emitting candidates, the coordinator shall write `identity-candidates.json` version 2
with `sources.model` (name, revision, license, closed_set_size), `sources.memory`
(`path: character-memory.json`, `version: 1`) and every source face in original order.

- Each face contains `face_id`, `image_sha16`, `candidates`, nullable `suggested`,
  `abstained`, and `attributes`. Each candidate uses `name`, optional `display`,
  `source: model|memory|bucket|action`, and an evidence score only for model/memory.
- Model top-five uses strict score >0.35, ≤5 entries; zero is valid. It works with
  no human references. User names are never prompts or inference features.
- Memory top-five uses maximum saved cosine over that character's baseline, variant,
  and assigned faces, >0.35. Exact crop-content self matches and excluded faces are
  removed. Saved embedding payload/order/profile validation remains mandatory.
- Enumeration is model-first then memory-only entries. Exact names (including explicit
  curated aliases) deduplicate; shared entries retain the model `source`/`score` plus
  `score_model` and `score_memory`. Scores are not averaged or treated as comparable
  probabilities. Multiple aliased model tags keep the maximum model score.
- Fixed `普通人物`, `新角色设计`, `无法确定` bucket entries are always available,
  followed finally by `{"name":"其他","source":"bucket"}` and
  `{"name":"新建角色","source":"action"}`. Buckets are not trained identities.
- Suggestions are `{name, source, margin_vs_runner_up}` or null. WD scores alone
  never bypass old gates: ≥2 supported visual identities, centroid threshold, positive
  minimum of centroid/individual-reference margins, and exclusion checks. Default
  gates reuse saved anchor calibration, or conservative .9/.05 when absent. With
  zero curated visual references this implementation always abstains, **even when
  WD enumeration is strong**. Folder-derived anchors are not silently converted to
  user-confirmed memory. Legacy anchor CSV is diagnostic, not a v2 JSON mirror.
- AC-FR-CANDIDATES-005-01: CANDIDATES-SYN-v1 tests cover zero-reference startup,
  finite/range checks, duplicate two-source scores, fixed buckets and strict top-five;
  compare to analytic vectors and explicit expected names. Evidence:
  `evidence/wd-memory-integration.json`, `tests/test_identity_v2_memory.py`.

### FR-CANDIDATES-006 — Reference marking and memory persistence
When a human confirms a face, the coordinator shall strengthen that character's visual
memory without changing any model weights, including for model-known characters.

- Journal version 1 and its four existing label fields remain compatible; the optional
  `mark: baseline|variant` is additive and omitted when absent. Marks on ignore/wrong_box
  are rejected. A mark-only change is journaled even if assignment is unchanged.
- `character-memory.json` version 1 contains `characters` with `name`,
  `origin: model|user|mixed`, `aliases`, `baseline_faces`, `variant_faces` (face_id/note),
  `assigned_faces`, `attribute_profile`, timezone-qualified `updated_at`.
- Confirmed marks retain membership in assigned faces; baseline/variant are mutually
  exclusive for a face. Ordinary repeated confirmation preserves its current mark.
  Reattribution/rejection removes that face from the former character's visual support.
- First migration uses human journal events only. No automatic WD assignment is a
  user reference. Memory stores IDs pointing to validated saved vectors, not duplicated
  feature matrices. Profile/corpus-mismatched imports fail closed.
- AC-FR-CANDIDATES-006-01: synthetic baseline/variant round-trip, mark-only replay,
  reassignment and unchanged legacy event hashes; evidence `evidence/wd-memory-integration.json`.

### FR-CANDIDATES-007 — Curatable namespace
When the human renames, merges, deletes, imports or exports a memory character, the
coordinator shall preserve valid visual support and reattribute current assignments
without rewriting historical naming events or touching image originals.

- CLI: `character-memory --memory-op list|rename|merge|delete|import|export`;
  rename/merge use `--name` and `--target`; exchange uses `--memory-file`.
  Create/assign through `identity-apply --labels`; baseline/variant are label marks.
- Rename preserves old name as alias. Merge unions baselines/variants/assignments,
  preserves variant notes and aliases, appends assignment events and regenerates v2.
  Delete removes curated state and retracts assignments; it does not modify WD's
  immutable vocabulary, so the deleted raw model tag can still be enumerated.
- Import merges by name, rejects ambiguous alias/face owners and unresolved foreign
  face IDs. Export carries corpus/profile binding. Cross-corpus vector transfer is not
  implemented; name-only entries are portable, visual references are corpus-local.
- Publication is atomic per file, with an exclusive identity-stage lock for CLI
  operations. Multi-file power-loss recovery is not certified; exported labels remain
  a replay receipt. Do not run direct mutation APIs concurrently.
- AC-FR-CANDIDATES-007-01: synthetic rename/merge/delete/import/export verify assignment
  and reference unions, preserved hash chain, conflict refusal and CLI execution;
  evidence `evidence/wd-memory-integration.json`, `tests/test_identity_v2_memory.py`.

### FR-WD-001 — Pinned local candidate and attribute evidence
When identity-tag processes saved crops, it shall execute the pinned WD v3 ONNX locally
in `.venv-wdtagger`, with versioned bounded subprocess requests and compact outputs.

- Artifact: `SmilingWolf/wd-eva02-large-tagger-v3`, revision
  `b25b82a03f7282e41aa2f257a52c7583b710bd1c`, **Apache-2.0**, 2,751 character classes
  (not the full multi-category output width). Model SHA256:
  `9e768793060c7939b277ccb382783e8670e8a042d29d77aa736be0c8cc898bfc`.
- Local model location is `out/zero-shot-candidates/model/{model.onnx,selected_tags.csv}`;
  no model download or image upload occurs in the stage. Source code remains AGPL-3.0-only.
- Preprocess `wd-white-square-bicubic448-bgr-f32-0-255-v1`: alpha over white,
  centered white square, bicubic 448×448, BGR float32 in [0,255]. Face crops differ
  from full-image Danbooru inputs: **domain shift is material**, clothing/context
  may be absent. Tags and scores are uncalibrated evidence, not verified attributes.
- `wd-worker-1.0` binds build, dependency pins, full model/tag hashes, preprocessing,
  request/run IDs, ordered crop hashes, deadline and actual active providers. The
  long-lived worker handles microbatches ≤16 (default eight), 240-second deadline,
  ≤60-second pending heartbeat. No hidden windows. Coordinator owns cache/state.
- CPU and CUDA cache namespaces are distinct: crop SHA256 + revision/preprocess +
  full handshake. Hits are schema/digest checked. Each face persists at most five
  character tags and 40 general attribute tags >.35; no raw 2,751-character vector
  or full multi-category vector. Rating category is not an attribute channel.
- `attributes` uses source `wd-tagger`, nullable hair_color/hair_style, and
  `tags:[{tag,score}]`. Hair summaries choose strongest retained matching tags.
  Memory hair-color profiles summarize supported faces; attributes never gate identity.
- Supplied probe evidence (not re-derived): ~2.78 s/full image CPU at eight threads,
  73.3% character coverage >.85 / 84.0% >.35; closed-set confusables observed. Those
  probe numbers are **not** face-crop production accuracy claims.
- AC-FR-WD-001-01: compact output/strict threshold tests and actual versioned subprocess
  inference; corrupted lineage rejected; evidence `evidence/wd-memory-integration.json`
  and private `out/<corpus>/wd-tagger.json`, `cache/wd-tagger/*.json`.
- AC-FR-WD-001-02: run all three private snapshots, report face coverage, memory
  entries, suggestions/abstention, top attributes, named-confusable occurrences;
  measure CPU/CUDA on identical eight crops with first/warm repeats. Occurrence is
  not false-positive rate without labels. Evidence `out/<corpus>/identity-candidates-report.json`
  and `out/<benchmark-corpus>/wd-throughput.json`. Not a paired ten-repeat performance
  qualification or cross-device numerical-equivalence certificate.

## Version 1 historical records

Design principle: **enumerate options, do not force a single guess**.
Status: implemented experiment; experimental semantics, not recognition certification.
Dependencies: INV-1–4, FR-GROUP-002/004, FR-IDENTITY-002, FR-CACHE-001.
Scope for all records: S: anchor-centroid-v1 / E: existing profile-bound saved
matrices / T: inherited identity execution tier. No model inference, dependency,
image writes, weight updates, score-column changes or automatic human labels.
Fixture: CANDIDATES-SYN-v1 (deterministic vectors and synthetic studio records).
Evidence: tests/test_identity_candidates.py, tests/test_gallery_candidates.py,
browser screenshots `docs/assets/v10-*`; private outputs remain under `out/`.
These scoped tests do not qualify global numerical, performance or accuracy gates.

### FR-CANDIDATES-001 — Per-face ranking
When identity-group processes saved face embeddings, the system shall emit an
additive version-1 `identity-candidates.json` containing every face in source order.

The envelope contains `version`, `provenance`, `thresholds`, and `faces`. Each face
contains `face_id`, `image_sha16`, `candidates`, `suggested` and `abstained`.
JSON is authoritative. An optional `identity-candidates.csv` may repeat the same
rows for spreadsheet inspection; consumers must not treat CSV as a second schema.
Candidates contain `character`, finite cosine `score`, nullable
`margin_vs_runner_up`, and `source: "anchor" | "cluster"`. This implementation
emits anchor evidence only; unnamed clusters are not invented known characters.
Rank all supported known characters before retaining at most five, descending
centroid cosine, ties broken by character name solely for deterministic display.
For each candidate, margin is its score minus the strongest *other* character's
score (negative for losers); it is null when no competitor exists. This exposes
the top candidate's runner-up gap without implying that lower ranks won.
Empty/zero-norm centroids are unavailable. Exact query crops are excluded from
references; effective references use the existing confirmed-reference replay.
Provenance binds input digests, profile, reference version and thresholds.

- AC-FR-CANDIDATES-001-01: synthetic six-character, tied, empty and singleton
  cases produce exact ordering, maximum length five, finite scores, correct null
  margins and one record per face; compare against analytic cosines.

### FR-CANDIDATES-002 — Suggestions are optional
When the top candidate fails any existing grouping gate, the system shall retain
ranked choices but emit `suggested: null` and `abstained: true`.

Otherwise suggested is the top character and abstained is false. Gates remain
the existing similarity threshold, positive stable margin (minimum of centroid
and individual-anchor margins), at least two supported characters, and exclusion
registry. Candidate display margins do not replace stable gate margins.
No candidate is a human confirmation. No references means an empty list and
abstention; unknown characters cannot be scored from their names.

- AC-FR-CANDIDATES-002-01: gate boundaries, individual-anchor disagreement,
  excluded faces and low scores match existing decide() results exactly; JSON
  uses null/boolean rather than empty strings, NaN or fabricated zero evidence.

### FR-CANDIDATES-003 — Human enumeration surface
When a human opens a face naming popover, the studio shall show up to five ranked
candidate buttons with score and competing margin, followed by `其他` and
`新建角色`, alongside `不是 / 跳过` without requiring acceptance of top-1.

Show `候选仅含已建档角色；其他角色需先建立参考` and disclose abstention and cosine
units (not probability). Four supported characters means four buttons, not a
fabricated fifth. Absent sidecars show unavailable ranking, never a guessed list.
Number keys 1–5 confirm the corresponding candidate; arrows move focus; Enter
activates the focused choice; Esc closes without recording. Input/IME typing
does not trigger candidate or image actions. One click confirms. Confirm and skip
advance to the next unlabeled face in the current filtered queue. Skip is
session-only and never exported as an incompatible face action. Exhaustion stops.

- AC-FR-CANDIDATES-003-01: synthetic DOM and browser checks at fit and narrow
  widths exercise mouse, keyboard, no-candidate, four/five-candidate, new-name,
  escape and next-face paths; no horizontal clipping or console errors.

### FR-CANDIDATES-004 — Compatible human labels and future evidence
When exporting a candidate choice, the studio shall retain the existing
`character_labels.json` version-1 review-studio envelope and unchanged label
fields `face_id`, `image_sha16`, `character`, `action`.

Ranked choices and `其他` use confirm; typed new names use new; rejection retains
ignore semantics (face exclusion, not a new per-character negative-reference
schema). No scores or candidate metadata enter the label envelope. A later
optional per-candidate `attributes` JSON evidence object may be added without
changing required fields or version; consumers preserve unknown fields and do
not assume its presence. Attribute-channel evidence is **planned**, pending a
separate feasibility test; no attribute inference or score fusion ships here.

- AC-FR-CANDIDATES-004-01: apply exported candidate/other/new labels through the
  existing LabelEnvelope and identity-apply path; optional attributes survive
  serialization and studio embedding without affecting scoring or labels.

### NFR-CANDIDATES-001 — Saved evidence and honest qualification
When producing or displaying candidates, the system shall reuse validated saved
matrices, preserve corpus files and existing contracts, and identify scores as
experimental retrieval evidence rather than calibrated identity probabilities.

- AC-NFR-CANDIDATES-001-01: execute grouping on the three private snapshots,
  report face totals/suggestions/abstentions and unchanged image row counts;
  run full pytest, regenerate synthetic/real galleries and capture v10 evidence.
  No held-out semantic accuracy, broad accessibility, cross-device equivalence,
  crash-atomic multi-file publication or throughput qualification is implied.
