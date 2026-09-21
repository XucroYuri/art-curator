> 中文摘要
> 相册以浏览、智能分类、人工反馈三层构成；虚拟映射优先于物理移动。
> 未知是常态，目录继承是可撤销弱先验，不能冒充身份真值。
> 本总纲约束后续开发，不宣称现有流水线已完成产品或质量认证。
> 来源参与分组须先解决与现行纯视觉宪章的冲突；默认仍保持纯视觉。

# Album master specification: vision and authority

Owner: Art Curator maintainers. Baseline: 2026-09-21. English is normative.
This family is the product-level governing specification for subsequent album work:
[INGEST](FR-ALBUM-INGEST.md) owns orchestration/resources;
[NEGOTIATE](FR-ALBUM-NEGOTIATE.md) owns evidence and consent;
[MAP](FR-ALBUM-MAP.md) owns disposition and reversal.
All records are proposed, not implemented or verified claims. Supporting tables
inherit their enclosing record. Evidence paths are future release-bundle paths,
not artifacts created by this documentation change. Lifecycle follows NFR-SPEC-001.

## Grounding (informative)

Read with 000-CONSTITUTION, 010-ARCHITECTURE, 011-CONTRACTS, 012-PERFORMANCE,
030-UX, 040-QUALITY-GATES, 050-ROADMAP and ADR-0001 through ADR-0004.
Existing feature contracts remain the component authorities: FR-IDENTITY-001/002,
FR-GROUP-001–004 and FR-CANDIDATES-005–007/FR-WD-001 in
[FR-IDENTITY-CANDIDATES](FR-IDENTITY-CANDIDATES.md).
The in-flight FR-CANDIDATES-008/009 amendment supplies `suggested_model`,
`suggested_verified` and contradiction demotion; its presence is not graduation.

Implemented experimental foundation: scan/thumbnail/preview; face detection,
crop embedding, clustering and anchors; reference-gated grouping with abstention;
WD/model plus user-memory candidates and fixed buckets; baseline/variant marks;
memory rename/merge/delete/import/export; offline single-file studio with dual
candidate sections, rapid review, marks and memory panel. Separate moves use
plan digest/token, copy→verify→unlink, ledger and undo; rehearsal is not universal
power-loss certification. Sources: `docs/pipeline/wd-memory.md`,
`docs/pipeline/identity-v2.md`, `docs/pipeline/identity-grouping.md` and
private `out/library-audit/report.md`. The virtual album and orchestration below
are target contracts, not names for an already complete application.

| Observation | Product consequence, not accuracy claim |
|---|---|
| 26,876 files, 27 top-level folders, 30.3 GB; 14,096 unsorted files | Incremental background work and mapping without relocation |
| 1,285/1,580 = 81.33% without a character tag ≥0.35; 10/1,580 = 0.63% candidate conflict | Unknown-first design; low conflict does not establish correctness |
| Comparable folder unresolved proxies span 100% to 20% | Per-folder measurement, not one global inheritance assumption |
| 4/6 exploratory clusters lack tag-based folder matches | Open-world naming; not four proven new identities |
| After majority-source hints, only 1/6 lacks either weak correspondence | Keep tag and provenance evidence separate; hints are not truth |
| Vocabulary scaffold coverage 32/43 | User-created namespace cannot be constrained to model vocabulary |
| A closed-set cross-character tag occurs on 204 faces, 146 above 0.85 | High scores alone never authorize identity assignment |

The audit used non-population-weighted stratified sampling with retained duplicate
files. Its proportions do not estimate all 26,876 files; folder unresolved proxy
is not misfiling rate. Whole-image and crop evidence have different denominators.
Exploratory leaf clustering was not preregistered identity validation.

### FR-ALBUM-VISION-001 — Authority and precedence
When an album change is proposed, the maintainer shall trace it to this family and preserve constitutional safety, existing component contracts and evidence-gated graduation.

Scope: S:* / E:* / T0–T4. Status: proposed.
- Precedence: existing constitutional vetoes → accepted constitutional amendments
  including mapping/provenance constraints → album product contracts → component
  implementation choices → usefulness → throughput → convenience. No lower rule
  waives a higher rule; unresolved contradictions fail closed.
- INV-M and INV-P below are proposed constitutional entries, not a stealth edit to
  000-CONSTITUTION. INV-M adds constraints compatible with INV-3. INV-P would permit
  a narrowly recorded provenance-aware grouping layer, conflicting with INV-2's
  current grouping prohibition. Until an explicit constitutional amendment and ADR
  are accepted, provenance can be measured/displayed and explicitly inherited as
  human-directed album organization, but cannot influence algorithmic grouping.
- Even after amendment, canonical visual tensors, raw model scores and pure-vision
  reference retrieval remain path-invariant; contextual grouping is a separate
  versioned proposal with both contextual and context-free results retained.
- AC-FR-ALBUM-VISION-001-01: Method: static change-manifest review; fixture: ALBUM-CONTRACT-v1; comparator: every change linked to an owner record and zero contextual grouping enabled before amendment approval; evidence `evidence/AC-FR-ALBUM-VISION-001-01.json`.

### INV-M — Mapping precedes moving
When the album classifies or organizes images, it shall maintain a virtual image-to-disposition mapping before any separately authorized optional reversible physical export.

Scope: S:* / E:* / T0–T4. Status: proposed constitutional addition.
- Browsing, naming, inheritance, first pass, review and logical ARCHIVE do not move,
  rename, rewrite metadata in, or delete source files. Export failure does not
  erase the mapping. Mapping undo and physical undo are distinct operations.
- AC-INV-M-01: Method: filesystem-write tracing and before/after hashes through all eight stages; fixture: ALBUM-FLOW-v1; comparator: zero source writes and identical source bytes/paths, mapped views available without physical export; evidence `evidence/AC-INV-M-01.json`.

### INV-P — Provenance as measured weak evidence
When folder or session provenance is proposed as grouping evidence, the system shall require measured coherence or purity, explicit consent, recorded use and reversible inheritance without silently treating context as identity truth.

Scope: S:* / E:* / T0–T4. Status: proposed constitutional amendment, activation gated by FR-ALBUM-VISION-001.
- Record sampling basis, denominator, missingness, confidence method/limits,
  measurement/profile/snapshot digests, selected folders and actual affected rows.
  No measurement means no contextual grouping permission. Weak consistency is not
  ground-truth purity; inferred labels cannot certify their own input folders.
- Inherited relations stay visibly `inherited`, unverified and retractable. Folder
  names and timestamps are never hidden features in a model, score or embedding.
  Disable/retract removes contextual proposals, not independent human decisions.
- AC-INV-P-01: Method: paired context-free/contextual replay plus retraction; fixture: ALBUM-FOLDER-v1; comparator: zero unmeasured or unconsented context uses, all uses logged, exact context-free result restored after retraction absent later human edits; evidence `evidence/AC-INV-P-01.json`.

### FR-ALBUM-VISION-002 — Three layers and three journeys
When a user opens or imports a library, the album shall provide browsing, intelligence and a human decision loop through the following observable journeys.

Scope: S: album / E: local client / T0–T4. Status: proposed.
- Browsing: source-tree and virtual-album views, thumbnail grid, preview, navigation,
  name/type/status filters, search of human labels, and unavailable-file indicators;
  browsing remains available with no model or with all evidence unavailable.
- Intelligence: background detection, grouping, candidates, first-pass mapping and
  unknown-pool discovery; every proposal links its evidence and policy version.
- Human loop: inspect, confirm, reject, correct, defer, name, split, merge, mark
  references, retract and undo; model evidence remains immutable and inspectable.
- Journey 1: drop a pile/tree → see inventory and progress → analyze → consent to
  mode → first-pass eligible named identities → browse mapped albums and unresolved
  tray → optional physical export. Empty memory permits hypotheses, not fabricated
  confirmed identities; a library build can finish with most images unresolved.
- Journey 2: inspect any AI result, including detections/boxes, attributes, cluster
  membership, suggested names, regime and purity estimates → record correction or
  disagreement → preview affected mappings/references → confirm reversible batch.
  Human labels strengthen retrieval, never weights; disagreement with a measured
  statistic is recorded as feedback, not a rewrite of the measurement.
- Journey 3: import a tree → receive proactive mode prompt → measured report shows
  qualifying clusters and folder evidence → name clusters or select inheritance →
  inspect consequences → confirm. No timeout or closing the prompt grants consent.
- AC-FR-ALBUM-VISION-002-01: Method: scripted end-to-end walkthrough of all three journeys including no-model startup; fixture: ALBUM-FLOW-v1; comparator: all listed actions reachable, every AI result supports feedback, zero unauthorized mappings or source moves; evidence `evidence/AC-FR-ALBUM-VISION-002-01.json`.

### FR-ALBUM-VISION-003 — Open-world namespace and resolution
When naming or resolving content, the album shall preserve typed user-extensible entities and distinct resolution states rather than forcing every image into a known character.

Scope: S: album taxonomy / E:* / T0–T4. Status: proposed.
- Namespace types: `work` (IP/作品), `artist` (画师), `original-series` (原创系列),
  `character` (角色), `ordinary-person` (普通人), `undetermined` (未定).
  Opaque entity IDs survive rename; aliases and typed relations allow many artists,
  works and characters per image. Same display name across types is not equality.
  User naming grows the namespace without adding model classes or prompt features.

| Resolution state | Meaning; not a deletion instruction |
|---|---|
| `assigned` | Named relation accepted by human or authorized first-pass policy; verification remains separate |
| `hypothesis` | Inspectable tentative name(s), including unverified model advice |
| `deferred` / 待查证 | Deliberately postponed with notes; eligible for later evidence |
| `unknown-foreign` / 陌生人 | Unrecognized subject, not a nearest-known assignment or nationality claim |
| `original-design` / 新设计 | User-selected original/new-design category; not proven model novelty |
| `ordinary` / 普通人 | Anonymous/ordinary-person organization; not real-world identity verification |
| `non-character` / 非人形 | Human-resolved non-character material; failed face detection is insufficient |
| `pending` | Not yet assessed or evidence unavailable |

- These states are independent of physical location and quality/safety routes.
  Mixed-subject images retain per-subject states; image aggregation is in MAP.
- AC-FR-ALBUM-VISION-003-01: Method: schema and round-trip tests; fixture: ALBUM-MAP-v1; comparator: all six types and eight states preserved, same-name entities remain distinct, no-face does not become non-character automatically; evidence `evidence/AC-FR-ALBUM-VISION-003-01.json`.

### FR-ALBUM-VISION-004 — Product boundaries and client gate
When presenting product capabilities or selecting a client form, the maintainer shall distinguish measured evidence from target behavior and preserve local operation without silent automation.

Scope: S:* / E:* / T0–T4. Status: proposed.
- No identity precision/recall, artist attribution, calibrated probability, real-person
  identification, universal taxonomy coverage or guaranteed complete classification
  without suitable independent labels/evidence. No user-corpus training, silent
  provider/model substitution, automatic destructive cleanup or default cloud path.
- Browser/FS-access feasibility is in flight: test durable access after restart,
  denied/revoked permissions, read-only ingest, job lifetime, offline review and
  explicit export authority before choosing browser-only, local companion or desktop.
  Current single-file studio remains a supported review/export surface, not proof
  that an HTML tab can durably orchestrate filesystem jobs after closure.
- AC-FR-ALBUM-VISION-004-01: Method: claims review and client capability matrix; fixture: ALBUM-CONTRACT-v1 and ALBUM-FLOW-v1; comparator: zero unsupported claims and each capability marked measured/pass, fail or untested with evidence; client selection blocked for unmet mandatory flow contracts; evidence `evidence/AC-FR-ALBUM-VISION-004-01.json`.

### FR-ALBUM-VISION-005 — Dependency-gated product roadmap
When scheduling or graduating album development, the maintainer shall use the G1–G7 dependency map and satisfy the owning acceptance criteria without equating component completion with product completion.

Scope: S:* / E:* / T0–T4. Status: proposed.

| Gap | Owning requirements | Dependencies / qualification boundary |
|---|---|---|
| G1 ingest orchestration | FR-ALBUM-INGEST-001–003; NFR-ALBUM-INGEST-001–004 | Existing scan/identity/cache workers; G5 persistence; G7 durable job capability |
| G2 mode negotiation | FR-ALBUM-NEGOTIATE-001–004 | G1 analysis; INV-P amendment for contextual grouping, not for display/manual inheritance |
| G3 cluster naming | FR-ALBUM-MAP-004/005 | Existing identity clusters and human journal; G5 batch undo; G2 consent |
| G4 first-pass policy | FR-ALBUM-MAP-002/003 | G2 consent, G5 mapping; in-flight FR-CANDIDATES-008/009 zero-reference tiers and demotion; no reference means no auto identity |
| G5 virtual album model | FR-ALBUM-MAP-001/006; NFR-ALBUM-MAP-001 | Full hashes, profile registry, human/memory lineage; authoritative publication/recovery gate |
| G6 optional physical archive | FR-ALBUM-MAP-007 | G5 committed snapshot; separate plan/token/digest/ledger/undo; INV-3 and move gates |
| G7 client form | FR-ALBUM-VISION-004; FR-ALBUM-INGEST-002; NFR-ALBUM-VISION-001 | Browser/FS spike and existing offline studio; no framework selection implied |

- Implementation order: G5 contracts/persistence prototype and G7 spike → G1/G2 →
  G3/G4 → G6 opt-in integration. Work can overlap against contracts; unresolved
  zero-reference/client work does not block this specification or manual review.
- AC-FR-ALBUM-VISION-005-01: Method: milestone-manifest audit; fixture: ALBUM-CONTRACT-v1; comparator: all seven gaps have owner IDs and prerequisite receipts before graduation, zero inherited blanket verification; evidence `evidence/AC-FR-ALBUM-VISION-005-01.json`.

### NFR-ALBUM-VISION-001 — Local privacy boundary
When album data is processed or exported, the system shall remain local-only by default and require separate explicit per-action consent for any future cloud path restricted to metadata-stripped thumbnails or embeddings.

Scope: S:* / E:* / T0–T4. Status: proposed; cloud execution deferred.
- No cloud original images, full-resolution crops, source paths, filenames, notes,
  EXIF or personal labels. Future payload contract: thumbnails at most 512 pixels
  on the long side and/or profile-bound vectors, opaque action-local IDs only.
  Embeddings are sensitive, not anonymized by definition. Consent lists endpoint,
  exact payload preview/count/bytes, purpose, retention/deletion policy and cost;
  unavailable retention guarantees block admission. Cloud results stay proposals.
- Missing local models fail visibly; explicitly authorized model downloads are
  separate network activity and contain no library payload. Logs and public release
  evidence use generic aliases/digests; private paths and imagery stay local.
- AC-NFR-ALBUM-VISION-001-01: Method: network capture and payload inspection; fixture: ALBUM-FLOW-v1 with denied, absent and granted cloud consent; comparator: zero default egress, denied actions send zero bytes, allowed payloads contain only declared bounded thumbnails/vectors and opaque IDs; evidence `evidence/AC-NFR-ALBUM-VISION-001-01.json`.

## Family fixture registry (inherited by every family AC)

These are planned suites, not newly generated corpus files. Under NFR-SPEC-001,
each execution manifest binds fixture version, generator/seed or licensed snapshot,
full SHA-256, expected outputs and profile versions before testing. Missing digests
or labels make qualification inconclusive; this document supplies no invented hashes.

| Alias | Definition |
|---|---|
| ALBUM-CONTRACT-v1 | Four-document tree, positive/negative release and consent manifests, dependency and claims matrices |
| ALBUM-FLOW-v1 | Synthetic folder tree with duplicates, CJK names, missing/corrupt files, revoked handles, staged jobs, injected failures and network capture |
| ALBUM-FOLDER-v1 | Labelled synthetic folder regimes, 0/1/29/30/50/100-item samples, mixed labels, sparse vocabulary, correlated duplicates, conflicting proxies |
| ALBUM-MAP-v1 | Analytic vectors and versioned mapping/events: every state/source, multi-face cases, repeated batches, later edits, all publication cutpoints |
| ALBUM-CONFUSABLE-v1 | Synthetic score/visual disagreement boundary cases plus separately consented held-out hard negatives; includes generic high-score cross-character pattern |
| ALBUM-PERF-v1 | Frozen 1,580-file stratified slice and 26,876-file workload shape, file/face counts separate, cold/warm runs, recorded hardware/storage/runtime; private content digests at execution |

Open decisions: constitutional amendment approval; labelled precision/coverage budgets;
client selection; durable mapping backend; fixture digests; unmeasured stage budgets.
These are explicit release gates, not reasons to fabricate certification or delay
the documentation contract. Model/weight/image rights remain independently gated.
