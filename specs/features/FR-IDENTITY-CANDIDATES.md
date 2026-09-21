> 中文摘要
> 枚举可选项，不强迫单一猜测；每张人脸展示前五候选、其他和新建角色。
> 候选仅含已建档角色；其他角色需先建立参考，分数不是身份概率。
> 未通过现有门禁仍可人工选择，弃权不等于没有候选。
> 人物标签导出保持兼容；属性证据留作独立实验后的可选扩展。

# Feature: Enumerate identity candidates

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
