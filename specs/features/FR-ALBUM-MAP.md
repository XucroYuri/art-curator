> 中文摘要
> 相册视图来自虚拟映射，多角色、多作品与来源证据共存，不靠移动文件分类。
> 首轮分自动、待审、无建议与百分之五抽检；高分跨角色冲突必须降级。
> 簇命名、拆并、未知池晋升和待查证均可追溯，整批操作可一键撤销。
> 当前逐文件原子写入不等于跨文件崩溃原子提交；物理归档另行授权。

# Virtual album, first pass and human resolution

Owner: Art Curator maintainers. Status: proposed. English is normative.
Authority/fixtures: [VISION](FR-ALBUM-VISION.md); execution:
[INGEST](FR-ALBUM-INGEST.md); consent: [NEGOTIATE](FR-ALBUM-NEGOTIATE.md).
Dependencies: FR-STABLE-001, FR-PERSIST-001, FR-IDENTITY-002, FR-GROUP-002/004,
FR-CANDIDATES-005–009, ADR-0002. Current sidecars and memory are foundations,
not an already implemented authoritative virtual-album transaction store.

### FR-ALBUM-MAP-001 — Content-bound virtual mapping schema
When publishing an album revision, the coordinator shall persist a versioned image-to-disposition mapping with typed relations and decision provenance from which album views are derived without moving source files.

Scope: S: album-map-v1 / E: local coordinator and readers / T0–T4. Status: proposed.

| Field | Required meaning / validation |
|---|---|
| `schema_version`, `library_id`, `revision`, `parent_revision` | Explicit schema and revision lineage; unknown major blocks mutation |
| `image_id` | Full SHA-256 of original bytes, never display sha16 alone |
| `occurrences` | Stable occurrence ID, local locator, observed full hash, availability; paths locate, not score |
| `disposition` | One of the eight VISION-003 states; image-level summary, not physical destination |
| `subjects` | Zero or more region/crop IDs bound to image/detection profile; each has disposition and relations |
| `relations` | Typed entity ID, role/type, subject ID or image scope, relation disposition and provenance; many-to-many |
| `source` | Primary decider basis: `model|memory|anchors|inherited|human`; mixed supporting sources retained in evidence refs, never erased |
| `scores` | Separate nullable finite WD score [0,1], visual cosines [-1,1], stable margin [-2,2], model margin and bound kind; units/profile per metric |
| `verified` | True only after explicit content/member-bound human confirmation of the asserted relation; never copied from `suggested_verified` |
| `batch_id`, `operation_id`, `decider` | Batch/operation lineage; decider is typed human actor-local ID or policy ID/version; missing basis is rejected |
| `created_at`, `updated_at` | Timezone-qualified timestamps; operational metadata, never model features |
| `evidence_refs` | Nonempty refs to input/report/consent/profile/reference/member digests and events, plus measured inheritance evidence when applicable |
| `flags`, `notes`, `hypotheses`, `review_after` | Contradiction/missingness/inheritance reasons; separately stored human notes and tentative alternatives; nullable revisit date |

- Metadata exists per image and per relation/subject where it differs. A pending
  initialization uses source=model and decider=`policy:pending-initialization-v1`,
  null scores, verified=false and unavailable-evidence reason; this is not inference.
- An image can appear in multiple character/work/artist views. Counts distinguish
  content, occurrences and faces. No single “winner” erases other accepted subjects.
  Summary priority for mixed subjects: pending → deferred → hypothesis →
  unknown-foreign → assigned; remaining categorical states summarize only unanimous
  subjects, otherwise hypothesis. Accepted relations remain visible in every case.
  `verified` at image level requires explicit confirmation covering all asserted
  subjects/relations; partially confirmed images show per-relation verification.
- Views include source tree, typed albums, unresolved/deferred/conflict trays and
  batch history; all read one committed revision. Missing originals show unavailable
  locators, not removed decisions. Human history and model proposals are separate.
- Import/export binds schema, full hashes, profiles and entity IDs; unknown optional
  fields survive round-trip. Legacy short IDs require manifest-backed full-hash
  resolution with unique association; ambiguity blocks import, never guesses.
- AC-FR-ALBUM-MAP-001-01: Method: schema, round-trip and view-projection tests; fixture: ALBUM-MAP-v1; comparator: exact relations/counts/lineage, every field validated, ambiguous legacy identities rejected, zero view-triggered moves; evidence `evidence/AC-FR-ALBUM-MAP-001-01.json`.

### FR-ALBUM-MAP-002 — First-pass tiers and contradiction veto
When FIRST-PASS evaluates a consented snapshot, the coordinator shall apply the versioned auto/review/none policy below and select an audit-5% overlay without converting model confidence into human verification.

Scope: S: album-first-pass-v1 / E: profile-validated local evidence / T0–T4. Status: proposed, semantic precision unqualified.
- Precedence: existing human assignment/exclusion → invalid/stale evidence veto →
  contradiction/demotion → reference-gated eligibility → model-only hypothesis →
  none. No threshold overrides identity/content/exclusion/consent prerequisites.
- Auto eligibility requires explicit 自动优先 consent, valid non-self visual evidence,
  ≥2 supported competing identities, unique centroid winner, and agreement of the
  centroid and individual-reference winners. Use `s ≥ max(0.90, calibrated_min_sim)`
  and stable margin `m ≥ max(0.05, calibrated_min_margin)`; stable margin is the
  minimum of centroid and same-winner individual-anchor margins. A reference-only
  leave-one-out calibration receipt and human-confirmed support for the winning
  identity are mandatory. No calibration, zero/one supported identities or
  folder-only unconfirmed support means no auto. Exact crop self-matches excluded.
- These are configurable conservative album defaults, not silent replacements for
  FR-GROUP-002's P95-wrong-cosine/P10-positive-margin calibration. Threshold changes
  create a new policy and require impact preview/consent and predeclared evaluation.
  No automatic lowering to reach a coverage target.

| Tier | Default decision | Mapping and review consequence |
|---|---|---|
| `auto` | All auto gates pass; no contradiction | `assigned`, source=memory or anchors, verified=false; visible policy/batch and undo; no automatic memory reference |
| `review` | Valid candidate evidence but auto gate fails, model-only advice, any contradiction, or user selected 人审优先 | Hypothesis/proposal with alternatives and reason; human decision required; existing human mapping preserved |
| `none` | No valid candidate above enumeration threshold and no other actionable evidence | Keep pending/unknown/deferred as appropriate; no nearest-name forcing or automatic non-character/original-design claim |
| `audit-5%` | Overlay on auto rows and eligible none rows, separately sampled | Retain base disposition and add audit flag/review task; audit does not claim a new identity |

- Enumeration defaults remain WD >0.35 and memory cosine >0.35 (strict v2 gates).
  Historical whole-image audit used ≥0.35; record this boundary difference rather
  than silently treating the two counts as identical. Review also includes conflicts
  even if current enumerated candidates disappear; absence of evidence is not acquittal.
- Zero-reference integration: consume in-flight `suggested_model` only as unverified
  hypothesis when WD score ≥0.85 and other-canonical-identity margin ≥0.20. Compact
  missing runner-up uses 0.35 upper bound, not zero; label margin as lower bound.
  `suggested_verified` means component reference-gate advice, not human verification
  or automatic satisfaction of this stricter album gate. Older v2 input without new
  fields remains reviewable; missing producer tier never fabricates an auto label.
- Contradiction rule follows FR-CANDIDATES-009: disagreement with an existing human
  assignment or strongest independent non-self memory/profile-valid anchor evidence
  above cosine 0.35 demotes model advice, even if that evidence fails the full auto
  gate. Tied leaders including the model are ambiguous, not proof of contradiction.
  Record `model_demoted`, alternatives, source, score and reason; raw model advice
  survives in secondary evidence. Never fuse WD scores and visual cosines.
- The observed `2b_(nier:automata)`-style case (204 occurrences, 146 >0.85 against a
  different intended subject) is a mandatory generic adversarial pattern. High WD
  score or margin cannot defeat contradictory evidence. With no independent evidence,
  keep it an unverified hypothesis, never auto; no corpus-name inference or blacklist.
- Audit selection: for each nonempty base-tier stratum, choose `ceil(0.05 × n)`
  distinct images by ascending SHA-256 of pinned policy seed + snapshot digest +
  tier + image full hash. Store selected IDs, seed and denominator. Review rows are
  already scheduled; zero rows yield zero sample. Replaying the snapshot is exact.
  Human errors found during audit freeze remaining publication for that policy batch
  and offer review/undo of the entire batch; do not silently retune thresholds.
- AC-FR-ALBUM-MAP-002-01: Method: analytic exact/just-below threshold, self-match, no-reference, multi-face and contradiction tests; fixture: ALBUM-MAP-v1 and ALBUM-CONFUSABLE-v1; comparator: exact tier table, zero model-only or contradictory auto assignments, zero automatic verified/reference promotions, exact deterministic ceil-5% samples; evidence `evidence/AC-FR-ALBUM-MAP-002-01.json`.

Threshold rationale (informative): the 81.33% unknown sample and 32/43 scaffold
coverage justify no minimum auto-coverage promise. The 0.63% conflict statistic
measures tag conflicts, not false assignment. Existing candidate fallback .90/.05
and observed anchor calibration about .9484/.00682 motivate retaining the larger
similarity threshold while adding a conservative .05 album margin. They do not
prove precision. The .85/.20 WD tier is an engineering tail/separation rule; the
146 high-score cross-character occurrences show why thresholds alone are insufficient.
Five-percent audit is a deterministic workload policy, not a statistical accuracy
certificate; tiny strata get one item and sampled labels do not verify unsampled rows.

### FR-ALBUM-MAP-003 — Visible batch change and one-click undo
When a user or policy commits a mapping batch, the album shall display what changed and why and provide a single batch-undo action that preserves later independent edits.

Scope: S: mapping events / E: local coordinator/client / T0–T4. Status: proposed.
- Before commit show affected image/member IDs, previous→next disposition/entity,
  counts by source/state, verification changes, thresholds, consent, reasons,
  conflicts, cost and source-files-unchanged notice. Persist this summary and
  before-images with operation/batch IDs and expected parent revision.
- `撤销本批映射` appends one inverse batch restoring all still-matching rows from
  that batch. No per-image clicking is required. Later edited rows are not overwritten:
  show conflict IDs and preserve them; label outcome partial undo, not total success.
  Repeated undo is idempotent. Original/inverse events remain inspectable.
- Naming, inheritance and promotion use this same contract. Reference membership
  added by a reverted human event is retracted unless independently supported;
  dependent unconfirmed suggestions become stale/review, not silently rewritten.
- AC-FR-ALBUM-MAP-003-01: Method: commit/undo/repeat-undo with intervening edits; fixture: ALBUM-MAP-v1; comparator: one action restores exact before-state for every eligible row, zero later edits lost, exact conflict and changed-count summary; evidence `evidence/AC-FR-ALBUM-MAP-003-01.json`.

### FR-ALBUM-MAP-004 — Cluster naming, split and merge
When a user resolves a visual cluster, the album shall present a representative wall and permit typed naming, member exclusion, split and merge through previewed reversible mapping batches.

Scope: S: cluster resolution / E: local client/coordinator / T0–T4. Status: proposed.
- Flow: representative wall → inspect all members/outliers and evidence → choose
  existing entity or new typed name → choose affected members/subjects → preview
  bulk mappings → confirm. Wall sampling alone does not assert all members correct.
  Confirmation explicitly covers the frozen selected member list, not future members.
  Another face in the same image is never assigned merely because one face was named.
- Human-confirmed selected relations get source=human, verified=true and event refs;
  evidence records cluster-level confirmation versus individual inspection. Only
  those confirmations may enter retrieval memory. Baseline/variant marks are explicit,
  mutually exclusive per face; no automatic marking of every cluster member.
- Split records disjoint chosen subsets plus remainder; merge previews conflicting
  names, mixed types and contradictory human labels. Conflicts require explicit
  resolution or stay deferred, never majority overwrite. Both operations create new
  member-set snapshot IDs with parent lineage; old clusters/events remain readable.
  Entity merge differs from visual-cluster merge and requires separate named intent.
- AC-FR-ALBUM-MAP-004-01: Method: naming/split/merge/replay/undo walkthrough; fixture: ALBUM-MAP-v1; comparator: exact selected-member mappings, zero sibling-face/future-member attribution, complete split partition and parent lineage, conflicts preserved; evidence `evidence/AC-FR-ALBUM-MAP-004-01.json`.

### FR-ALBUM-MAP-005 — Re-cluster and promote the unknown pool
When a user requests unknown-pool discovery or approves a scheduled proposal, the coordinator shall re-cluster a frozen unresolved set and allow promotion of a selected cluster as one named reversible batch.

Scope: S: open-world discovery / E: compatible saved vectors / T0–T4. Status: proposed.
- Default pool: unknown-foreign, pending with valid vectors, hypothesis and deferred;
  explicitly resolved ordinary/original-design/non-character items are excluded unless
  selected. Deferred notes/revisit settings survive. No valid vector means retained
  unresolved item, not deletion or invented embedding.
- Show pool membership digest, proposed profile/parameters, previous cluster lineage,
  cost and additions/splits/merges; preserve all confirmed relations outside selected
  unresolved subjects. Saved vectors require profile compatibility; re-embedding is
  separately quoted if needed. No PCA/UMAP/threshold changes hidden as optimization.
- Unknown seed default: ≥10 distinct images (configurable), consistent with the
  exploratory audit's discovery scale, not identity evidence. Smaller sets and noise
  remain manually nameable. Proposed coherent wall uses NEGOTIATE-001 gates; changed
  clustering parameters create a distinct proposal, not revised historical evidence.
- Promotion flow: representative wall → existing/new typed entity → selected member
  preview → explicit confirmation → one MAP-003 batch. A tag/folder unmatched cluster
  is not automatically a new character; permit work/artist/series or deferred outcome.
- AC-FR-ALBUM-MAP-005-01: Method: unknown-pool growth/re-cluster/promotion/reversal tests; fixture: ALBUM-MAP-v1 and ALBUM-CONFUSABLE-v1; comparator: exact frozen pool, zero unrelated confirmed changes, noise retained, cluster promotion one batch and exact eligible undo; evidence `evidence/AC-FR-ALBUM-MAP-005-01.json`.

### FR-ALBUM-MAP-006 — Non-terminal deferred tray
When a user selects 待查证, the album shall retain notes, competing hypotheses and revisit triggers without treating deferral as rejection, deletion or a completed identity.

Scope: S: deferred resolution / E:* / T0–T4. Status: proposed.
- Notes can be empty; alternative typed names/scores retain source evidence and
  never enter memory as confirmations. Optional review_after date, new-reference
  availability or changed candidate evidence adds a visible revisit notification.
  A trigger proposes review only; it cannot silently replace the deferred decision.
- Tray supports filters by age/reason/batch, explicit reopen, confirm, re-defer,
  unknown-foreign and undo. Logical ARCHIVE preserves the tray and unresolved count;
  export/import preserves notes and triggers. User text never enters scoring.
- AC-FR-ALBUM-MAP-006-01: Method: clock/evidence-trigger and archive round-trip tests; fixture: ALBUM-MAP-v1; comparator: every note/hypothesis/trigger preserved, exactly one notification per trigger revision, zero automatic confirmation or training; evidence `evidence/AC-FR-ALBUM-MAP-006-01.json`.

### FR-ALBUM-MAP-007 — Optional reversible physical archive
When a user separately requests physical organization, the move adapter shall derive a frozen export plan from a committed mapping revision and require independent plan/digest/token confirmation before any filesystem mutation.

Scope: S: optional mapping-to-move export / E: local move engine / T0–T4. Status: proposed integration; existing engine is separately implemented experimental.
- Default ARCHIVE is logical only. Export binds mapping revision, explicit selected
  relations/files/destinations, source full hashes and existing decision/plan digest
  contracts. Multi-membership requires an explicit destination/copy policy, never
  arbitrary first character. Hypothesis/deferred/inherited/unverified rows are
  excluded by default and need explicit reviewed inclusion, not auto promotion.
- Preserve copy→fsync→verify source and destination→durable ledger→verified redundant
  source unlink; no unrelated overwrite. Recheck changed sources/plans and reject;
  never regenerate a different plan during execute. Report collision, capacity and
  missing-file conflicts. Existing per-output locks are insufficient proof of
  corpus-wide exclusion; concurrency qualification remains gated by FR-PERSIST-001.
- Physical undo uses the move ledger; map batch undo does not move files back.
  Display the two actions separately and show outstanding physical exports when
  mapping undo changes their originating revision. Rehearsed moves are not backup
  or physical-power-loss certification; INV-3 and NFR-GATE-005 still govern.
- AC-FR-ALBUM-MAP-007-01: Method: adapter dry-run/execute/undo with changed mapping/source and all move cutpoints; fixture: ALBUM-MAP-v1 plus MOVE-SYN-v1; comparator: zero mutation without separate authorization, zero unverified unlink/overwrite, at least one verified copy per recoverable operation and exact conflict report; evidence `evidence/AC-FR-ALBUM-MAP-007-01.json`.

### NFR-ALBUM-MAP-001 — Publication atomicity and explicit recovery gap
When a mapping batch affects multiple artifacts or is interrupted, the coordinator shall expose only one internally consistent committed revision and reconcile incomplete publication before accepting another mutation.

Scope: S: authoritative mapping/event/reference publication / E: local storage / T0–T4. Status: proposed; current multi-file crash atomicity unqualified.
- Current identity/memory/mapping-related sidecars use atomic replacement per file
  and stage locks, not crash-atomic commit across journal, registry, memory, map and
  exports. No existing multi-file transaction or power-loss guarantee is claimed.
- Target protocol: durable prepared batch with parent revision and before-images;
  validate all artifact digests; durable commit marker/root selects the complete
  revision; derived views read only that revision. Uncommitted fragments are hidden.
  Storage backend (transactional store or generation-plus-root protocol) is an open
  architectural decision requiring ADR and fault-injection evidence, not prescribed
  by this documentation as already implemented.
- Single-writer admission binds the library, not merely an output directory.
  On restart, reconcile prepared/committed/inverse batches and artifact digests.
  Torn or ambiguous state blocks mutation, preserves evidence and offers explicit
  recovery; no timestamp-based “newest file wins.” Backups and export receipts are
  retained under the storage policy. A clean process-exit test is not power-loss QA.
- AC-NFR-ALBUM-MAP-001-01: Method: fault injection at every prepare/write/fsync/root/commit/undo boundary and concurrent-writer attempt; fixture: ALBUM-MAP-v1; comparator: reader observes exactly old or fully committed new logical revision, no lost human events, one admitted writer, all ambiguities block mutation with recovery receipt; evidence `evidence/AC-NFR-ALBUM-MAP-001-01.json`.

## Qualification and deliberately open matters (informative)

All new AC artifacts are future obligations. No label-derived precision threshold,
minimum auto coverage or universal cluster purity is invented here. Held-out
confusables, drift/false-merge tolerances and label audit design require predeclared
budgets before semantic graduation. The in-flight model-tier amendment and browser
spike are dependencies, not reasons to change their dirty files or wait to publish
these contracts. No source/corpus mutation, implementation, inference or certification
is performed by this specification set.
