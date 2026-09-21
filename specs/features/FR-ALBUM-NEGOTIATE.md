> 中文摘要
> 导入主动询问工作方式，分析后展示簇、目录证据与预计影响，再确认执行。
> 人审优先、自动优先、仅继承目录与三种继承范围分别记录，默认不继承。
> 目录纯度必须有测量依据；模型一致性和来源集中度都不等于真实身份纯度。
> 所有推荐均可拒绝，关闭窗口或等待超时不会自动授权。

# Album mode-negotiation contract

Owner: Art Curator maintainers. Status: proposed. English is normative; the quoted
Chinese strings below are required user-facing copy, not an alternate normative body.
Authority and fixture registry: [VISION](FR-ALBUM-VISION.md).
Dependencies: INV-P, FR-ALBUM-INGEST-001, FR-GROUP-002,
FR-CANDIDATES-005/008/009, [MAP](FR-ALBUM-MAP.md).
No change to existing raw visual scores or automatic metadata feature permission.

### FR-ALBUM-NEGOTIATE-001 — Evidence-bearing post-analysis report
When analysis reaches PROPOSE, the album shall display a snapshot-bound report with cluster evidence, folder evidence and predicted consequences before accepting mode confirmation.

Scope: S: album negotiation / E: local client / T0–T4. Status: proposed.
- Global report: file/unique-image/face counts, processed and unavailable counts,
  model revisions/profiles, sample versus census scope, missing vocabulary, unknown
  and candidate-conflict rates, estimated auto/review/none/audit counts, and cost.
  Full-image and crop outputs have separate denominators and are not pooled.
- Cluster list: every qualifying cluster plus a route to all remaining clusters;
  frozen membership digest, unique-image and face sizes, outlier fraction, metrics,
  representative thumbnails, model candidates with score/margin and source,
  reference/memory support, contradictions, names if any and eligibility reasons.
  Representatives default to min(12, image count): medoid, lowest-coherence member,
  then farthest-point diversity with full-hash tie-break; no duplicate-image padding.
- Proposed `coherent-cluster-v1` eligibility: ≥10 distinct images, median member
  cosine to leave-one-out centroid ≥0.90, 10th percentile ≥0.80, all vectors valid
  under one profile. Fewer/invalid vectors are insufficient, not high confidence.
  These configurable discovery thresholds select a representative wall, not an
  identity guarantee or bulk-assignment gate. Every mapped member still follows MAP.
- Folder report: selected population and sample IDs/digest, unique versus duplicate
  counts, sample design/seed/coverage, model/label coverage, U unknown, C candidate
  conflict, coherence and purity fields below, interval method and limitations,
  regime candidates, selected detector profile and inheritance eligibility.

| Metric | Measured basis and honest interpretation |
|---|---|
| Visual coherence | Same-profile non-self centroid cosine quantiles on distinct images; scene/style similarity can dominate |
| Labelled identity purity | Largest independently human-labelled identity count / all randomly sampled images; unresolved labels counted separately, never omitted from denominator |
| Weak target agreement | Model tags matching explicit user-supplied target vocabulary / sampled images; vocabulary coverage and aliases disclosed |
| Unresolved proxy D | Fraction with no candidate, multiple canonical candidates or top candidate outside weak target; only comparable within applicable target vocabulary |
| Source concentration | Largest folder-origin fraction in a visual cluster; describes origin, not identity purity |

- No human labels means identity purity is `unavailable`; weak agreement cannot be
  relabelled purity. Artist/original-series/unmapped targets show D as N/A and
  still show U/C/coherence. No-face is detector missingness, not non-character truth.
- For new prospective purity estimates use seeded simple random sampling without
  replacement within each folder, up to 100 distinct images; record sample and
  population sizes. Show Wilson 95% intervals for sampled binary proportions with
  the independence/duplicate caveat; a full census shows exact descriptive fraction,
  not a model-correctness interval. Unlabelled members cannot establish purity.
  Other sampling designs require their declared estimator; absent one shows
  descriptive-only/no population CI. Never retrofit a CI onto the historical audit.
- AC-FR-ALBUM-NEGOTIATE-001-01: Method: report/schema and analytic-statistics tests; fixture: ALBUM-FOLDER-v1 and ALBUM-CONFUSABLE-v1; comparator: all mandatory fields/denominators present, representatives reproduce exactly, boundary eligibility exact, zero unlabelled purity or unsupported population estimates; evidence `evidence/AC-FR-ALBUM-NEGOTIATE-001-01.json`.

### FR-ALBUM-NEGOTIATE-002 — Measurable folder-regime hypotheses
When proposing how to interpret a directory tree, the album shall emit versioned measurable regime hypotheses with an insufficient-evidence outcome instead of treating directory names as proven classifications.

Scope: S: folder-regime-v1 / E: saved local evidence / T0–T4. Status: proposed heuristic, uncalibrated.
- Detector sample uses NEGOTIATE-001; minimum 30 distinct valid images for automatic
  regime recommendation. Smaller folders remain inspectable with manual selection.
  Thresholds below are configurable semantic-profile parameters, not measured
  accuracy optima. Outputs include feature values, denominators, threshold results,
  supporting thumbnails and nullable confidence; no invented probability.
- Define `V` = median whole-image LOO cosine, `F` = largest face-cluster share among
  detected eligible faces, `K` = count of face clusters each supported by ≥3 distinct
  images, `Q` = fraction of images with zero detected faces or ≥2 detected faces,
  `A` = fraction of sampled images independently confirmed by a human to share an
  artist. Missing face/artist evidence leaves the dependent detector unavailable.

| Regime | Proposed measurable detector | Consequence, not automatic assignment |
|---|---|---|
| `session-set` | V≥0.90 and F≥0.80 with ≥30 valid images and ≥30 eligible faces | Suggest inspecting one coherent set; same session does not imply one identity |
| `mixed-pile` | V<0.80 and F<0.50 and K≥3 | Suggest cluster-first review; do not inherit character names automatically |
| `scenario/documentary` | V≥0.85 and Q≥0.50 and F<0.80 | Suggest scene/collection organization; no-person conclusion prohibited |
| `artist-portfolio` | A≥0.80 over ≥30 randomly sampled independently labelled images, with ≥3 distinct confirmed character/work entities represented | Suggest artist axis independently of character axis; visual style alone cannot certify artist |

- Multiple passing detectors are returned as ambiguous; none passing is
  `undetermined`, not a fifth secretly inferred regime. Human choices can override
  display interpretation with an event, without changing measured values.
- Display confidence as `heuristic/unvalidated` plus measured proportion intervals
  where applicable; calibrated regime confidence needs a held-out labelled fixture
  and a preregistered profile. Paths can locate folders and display user declarations;
  timestamps/name patterns do not enter raw visual math. Contextual grouping is
  governed by ADR-0005 and the INV-2/INV-P amendments, and stays inactive unless its
  measured admission conditions pass. Consent alone does not authorize use, and regime
  detection grants neither measurement nor consent.
- AC-FR-ALBUM-NEGOTIATE-002-01: Method: analytic detector boundary and missingness replay; fixture: ALBUM-FOLDER-v1; comparator: exact table outcomes including ties/overlap/unavailable, zero unsupported artist or identity claims, unchanged raw scores under path rename; evidence `evidence/AC-FR-ALBUM-NEGOTIATE-002-01.json`.

### FR-ALBUM-NEGOTIATE-003 — Explicit mode and inheritance consent
When ingestion begins and again when its measured report is ready, the album shall proactively ask the user to select a working mode and inheritance scope and record the confirmed consequences before FIRST-PASS.

Scope: S: consent and first-pass authorization / E: local client / T0–T4. Status: proposed.
- Initial prompt records intent only; default selection is 人审优先 with 不继承,
  but even defaults require explicit confirmation after analysis. Basic inventory,
  thumbnails and explicitly authorized analysis can run before this final consent;
  disposition changes cannot. No response leaves PROPOSE/CONFIRM waiting.

| Mode | Recorded consequences |
|---|---|
| 人审优先 | Show representative wall; await cluster→typed-name confirmation; machine eligible assignments remain proposals until accepted; manual batch naming available |
| 自动优先 | Explicitly authorize only MAP-002 auto-eligible mappings, keep verified=false, emit audit-5% and review/none lanes; no reference-free WD identity assignments |
| 仅继承目录 | Materialize selected directory organization as inherited virtual collections; no AI identity first-pass changes or post-confirmation recognition; analysis already performed remains inspectable and later recognition requires new consent |

| Inheritance | Recorded consequences |
|---|---|
| 全继承 | Freeze all selected-root directory IDs and user-selected types as inherited organization; unresolved types stay undetermined, no automatic character coercion |
| 逐目录勾选 | Freeze only checked directory IDs, relation types and descendant policy; default descendant policy is include current snapshot descendants, not future files |
| 不继承 | Preserve source-tree browsing only; zero inherited semantic relations or context-assisted grouping |

- Mode and inheritance are orthogonal except 仅继承目录 + 不继承: show browse-only
  outcome, not a successful classification. Future files require a new scoped
  receipt; saved preferences may prefill, never silently broaden old consent.
- Every inheritance result has source=inherited, verified=false, receipt and
  measurement refs. Unmeasured/low-purity folders can be explicitly retained as
  human-directed collections, not promoted to AI identity evidence. Proposed
  recommendation for identity-oriented inheritance requires ≥30 independent labels,
  Wilson lower bound ≥0.90, V≥0.90 and disclosed missingness; failure disables the
  recommendation, not manual collection organization. This is engineering policy.
- “Many coherent clusters” defaults to ≥3 eligible clusters collectively covering
  ≥20% of valid unique images: highlight 人审优先 and wait for names. When eligible
  identity-oriented folders cover ≥50% of valid images, highlight inheritance as
  an alternative. If both apply, show both without choosing. Counts and thresholds
  appear in the report; all choices remain available regardless of recommendation.
- Consent receipt: actor-local ID, timestamp, report/snapshot/profile digests,
  mode, inheritance scope, types, members, descendant behavior, threshold overrides,
  predicted affected counts by tier, cost ceiling, limitations acknowledged and
  operation ID. Changes invalidate the previous proposal; re-consent is required.
- AC-FR-ALBUM-NEGOTIATE-003-01: Method: exercise all nine mode/scope combinations, stale reports and dismissal; fixture: ALBUM-FLOW-v1 and ALBUM-FOLDER-v1; comparator: exact consequences above, zero pre-consent changes or inferred future-file consent, one replayable receipt per confirmation; evidence `evidence/AC-FR-ALBUM-NEGOTIATE-003-01.json`.

### FR-ALBUM-NEGOTIATE-004 — Required Chinese copy and honesty
When showing negotiation and its consequences, the client shall render the following Chinese copy with bound counts and no language implying that weak evidence is verified identity.

Scope: S: negotiation presentation / E: all local clients / T0–T4. Status: proposed.

| Surface | Required literal copy; braces are bound values |
|---|---|
| Ingest prompt | `这批图片希望怎样整理？分析后会再次请你确认，不会自动移动原文件。` |
| Choices | `人审优先` / `自动优先` / `仅继承目录` |
| Inheritance controls | `全继承` / `逐目录勾选` / `不继承` |
| Coherent clusters | `发现 {count} 个视觉较一致的分组，共 {images} 张图片。分组不等于同一角色，请先确认名称或拆分。` |
| Measured evidence | `测量依据：{method}；样本 {sample}/{population}；证据覆盖 {coverage}；置信说明：{confidence}。` |
| Purity missing | `没有独立人工标签，无法确认身份纯度；以下仅为视觉一致性或弱标签符合率。` |
| Inheritance warning | `继承目录只是弱先验，不代表角色已核实；会标记为“继承”，可整批撤销。` |
| Auto warning | `自动优先只建立满足门禁的虚拟映射；模型高分不等于身份正确，无参考建议仍需核实。` |
| Model tier | `模型建议（未核实）` |
| Reference tier explanation | `已核实建议仅表示通过参考/记忆门禁，不表示人工确认或准确率认证。` |
| Conflict | `模型建议与参考或人工证据冲突，已降级为待审，不会自动归入该角色。` |
| Confirmation | `将新增或修改 {changed} 张图片的虚拟映射，{review} 张待审，{none} 张保留未解决；原文件不变。` |
| Commit action | `确认并建立虚拟映射` |
| Dismiss / undo | `暂不决定` / `撤销本批映射` |

- Unavailable values render `未知` or `不适用` with reason, never zero/100% by
  default. Intervals name their metric and sampling limits; no percentage score
  labelled “identity confidence” without calibration. Translation changes retain
  these distinctions and require updated acceptance snapshots.
- AC-FR-ALBUM-NEGOTIATE-004-01: Method: string/DOM snapshots and scripted rendered-client walkthrough; fixture: ALBUM-FOLDER-v1 and ALBUM-FLOW-v1; comparator: all applicable literals and bound counts exact, no unresolved placeholders, zero clipped/unreachable choice controls at 520/900/1440 widths and keyboard-only operation; evidence `evidence/AC-FR-ALBUM-NEGOTIATE-004-01.json`.

## Evidence rationale and limits (informative)

The historical 81.33% sample unknown rate, 0.63% tag conflict and 20–100% folder
unresolved range motivate abstention and per-folder disclosure, not particular
purity probabilities. A 32/43 vocabulary scaffold cannot certify artist or original
series folders. V/F/Q/A thresholds and sample minima above are preregistered target
heuristics requiring labelled evaluation; no such regime/purity classifier is
claimed implemented. Folder consent does not lift INV-2 by itself.
