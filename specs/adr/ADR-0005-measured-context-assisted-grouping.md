> 中文摘要
> 目录或会话上下文仅可在测量、明示同意、逐图留证和无残留撤销后辅助分组。
> 上下文是弱先验，视觉矛盾始终否决；不改变模型输入、原始分数或人工决定。
> 人工继承目录始终可用；本次批准修改宪章，不代表实现或认证通过。

# ADR-0005 — Measured context-assisted grouping

Status: accepted; date: 2026-09-21; owner: Art Curator maintainers.
Requirement and AC trace: INV-2 / AC-INV-2-01–06, INV-P / AC-INV-P-01,
FR-ALBUM-VISION-001/002, FR-ALBUM-NEGOTIATE-001–003,
FR-ALBUM-MAP-001/002/006, NFR-SPEC-001.
Supersedes: only the unconditional grouping prohibition in
[INV-2](../000-CONSTITUTION.md#inv-2--pure-vision) and the pending constitutional
conflict for [INV-P](../features/FR-ALBUM-VISION.md#inv-p--provenance-as-measured-weak-evidence).
Superseded-by: none.

## Context

Scenario 3 is to inherit a good folder classification and continue recognition
on that basis. The album master specification introduced INV-P as measured weak
provenance evidence, but correctly left it inactive: INV-2 previously prohibited
paths and timestamps as evidence for any algorithmic grouping. Folder labels could
name human-selected references, and manual inheritance could organize collections,
but neither authorized using a query image's folder or session membership to
assist grouping. Consent alone could not waive that constitutional prohibition.

The user has explicitly approved a constitutional amendment. Historical album
observations motivate per-folder measurement, not identity truth or universal
purity estimates. No new measurement, inference or implementation accompanies this
decision. INV-1, INV-3, INV-4 and INV-M are unchanged.

## Decision and alternatives

Approve INV-P and the narrow INV-2 exception below. These clauses elaborate those
existing records, not independent requirements. All conditions are conjunctive;
missing, stale or unverifiable conditions deny algorithmic context use.

1. **Restricted layer and input.** Only explicitly selected folder membership or
   user-declared session membership may inform a separate, versioned grouping
   proposal layer. Membership is an opaque, snapshot-bound relation, not lexical
   interpretation of names, paths or timestamps. No inferred timestamp sessions,
   captions, EXIF, engagement signals or arbitrary metadata features are licensed.
   Canonical tensors, embeddings, raw scores, visual similarities, context-free
   retrieval and its decisions remain unchanged; both proposal variants are kept.
2. **Measured admission, reported before consent.** For each selected folder/session,
   use seeded simple random sampling without replacement of up to 100 distinct
   image hashes; record population/sample hashes, seed, counts, duplicates, coverage,
   missingness, profile and snapshot digests. Use same-profile visual vectors,
   one declared image representation per image, with non-self leave-one-out centroid
   cosines. Require at least 30 sampled images with valid vectors, median cosine
   >=0.90 and 10th percentile >=0.80 (linear-interpolated quantiles). Invalid or
   zero-norm vectors are unavailable, never zero-valued measurements. Report the
   valid-vector denominator and missingness against the entire sample.
   These are conservative coherence admission heuristics, not identity accuracy.
   For an identity-oriented prior also require at least 30 independently human-
   labelled sampled images, and a Wilson 95% lower bound >=0.90 for the declared
   target identity count divided by the **entire** sample, including unresolved
   images. Report the estimate, unresolved count and interval using z=1.96;
   for a census report the exact fraction and use that fraction >=0.90 instead
   of a sampling interval. Duplicate/near-duplicate dependence must be disclosed;
   unestablished label independence blocks identity-prior admission. Coherence-only
   admission can suggest an unnamed collection, never a named identity. Model tags,
   source concentration and inherited labels cannot certify their own purity.
   Reports follow NEGOTIATE-001; smaller or failing sets remain manually usable.
3. **Explicit, non-silent use.** Default is context-free. Before enabling the layer,
   show method, measurements, limits, context-free/contextual impact and affected
   members; record affirmative consent bound to report, membership, profile,
   relation type and operation digests. Closing, timeout or prior preferences are
   not consent. New members or changed measurements/profiles require new consent.
   Each affected image, and each differing subject/relation, records full SHA-256,
   occurrence/context IDs, `source=inherited`, `verified=false`, `evidence_refs`
   to measurement/report/consent/profile snapshots, operation/batch ID, baseline
   result, contextual result and reason. Mixed evidence retains this provenance
   rather than hiding it behind a model source. Display the inherited badge and
   evidence access per image, including when contextual and baseline results agree.
4. **Weak prior, visual veto.** Context may suggest tentative membership or order
   visually admissible ambiguous proposals; it cannot modify similarity scores,
   lower visual gates, rescue invalid/missing visual evidence, override a visual
   winner, or promote an inherited proposal to a confirmed identity/reference.
   Disagreement with the context-free visual winner, or independent non-self
   memory/profile-valid anchors under FR-CANDIDATES-009's contradiction rule,
   vetoes that contextual suggestion even below full auto-assignment gates.
   Retain the conflict for inspection, demote to review, and preserve visual and
   independent human results. Ambiguity is not confirmation. Context never
   increases auto eligibility under MAP-002; no amount of purity overrides a veto.
5. **Retraction with no operative residue.** Disable/retract removes every dependent
   contextual proposal, derived mapping/index/cache contribution and retrieval
   influence, including transitive descendants. Never seed confirmed memory from
   inheritance. Restore exactly the context-free result for unchanged inputs;
   with later independent human edits, replay the same human events over that
   baseline and preserve them, reporting conflicts rather than overwriting them.
   Restart/resume cannot resurrect revoked context. Only explicitly inactive audit
   events/receipts remain; they are history, not evidence eligible for future use.
   Source bytes and paths never change. Durable reversal follows MAP-006.
6. **Always-available human path.** Manual folder/session inheritance as visibly
   unverified organization remains available without models, valid measurements,
   qualifying purity or consent to algorithmic assistance. Record explicit human
   selection and unavailable measurement reasons; retain undo and no-source-write
   guarantees. A failed automatic gate does not disable manual organization.
   Manual inheritance alone grants no AI identity evidence. Continuing recognition
   after inheritance requires separate scoped consent; inheritance-only stays so.

Semantic identity: allocate a separate context-assisted grouping policy/profile,
including these methods, thresholds, veto rules and provenance schema; bind context
snapshot and consent to run identity. Do not reuse pure-vision result/cache identity
for contextual proposals. Models, rendering and execution profiles are unchanged.
Changing admission thresholds or the permitted use requires a new reviewed semantic
profile and evidence; lowering these constitutional minima requires an amending ADR,
not a runtime override or a post-hoc coverage target.

Rejected alternatives:

- **Keep the blanket prohibition:** safe but cannot deliver scenario 3 beyond
  manual organization; measured context could never assist subsequent recognition.
- **Trust folder names/session proximity or consent alone:** neither establishes
  coherence/purity, records actual per-image use nor protects against silent errors.
- **Fuse context into model inputs/scores or let purity outweigh contradiction:**
  destroys path-invariant visual evidence and makes withdrawal non-local or unsafe.
- **Require measurements for all manual inheritance:** needlessly blocks human
  organization in small, mixed or no-model libraries; manual actions are not AI truth.

## Consequences and evidence

Scenario 3 becomes legally possible, not implemented or verified. Costs include
measurement/reporting, independently labelled identity samples, dual proposals,
per-image lineage, scoped consent and dependency-aware rollback. Sparse folders
may never qualify automatically; missingness and visual contradictions reduce
coverage intentionally. No recognition-accuracy or performance claim is made.

Acceptance is owned by INV-2: AC-INV-2-02 measures admission, -03 checks consent and
per-image provenance, -04 enforces visual veto/isolation, -05 tests residue-free
retraction, and -06 preserves manual inheritance. AC-INV-2-01 remains unchanged;
AC-INV-P-01 still requires paired replay. All new ACs are unverified future criteria.
Their ALBUM-FOLDER-v1, ALBUM-MAP-v1, ALBUM-CONFUSABLE-v1 and ALBUM-FLOW-v1 suites
inherit the album fixture registry. Execution manifests must freeze generator/seed,
full fixture SHA-256, analytic expected results and profiles before testing;
no invented digest or missing artifact establishes qualification. Public evidence
contains aliases/digests, not private paths. Adversarial cases include small samples,
correlated duplicates, self-labelled purity, misleading folders, cross-identity
visual conflicts, stale consent, later edits and interrupted retraction/restart.

Revoke assisted use on any missing receipt, measurement/profile/snapshot mismatch,
unlogged image, visual override or residual influence after withdrawal; retain
context-free recognition and manual organization. Requalification requires all
affected AC receipts and NFR-SPEC-001 release-manifest/profile updates. Constitution
approval does not silently change existing component contracts or claim they pass.

References: [constitution](../000-CONSTITUTION.md),
[lifecycle](../README.md#requirement-grammar-and-evidence-convention),
[album vision and fixture registry](../features/FR-ALBUM-VISION.md),
[measurement and consent](../features/FR-ALBUM-NEGOTIATE.md),
[mapping and reversal](../features/FR-ALBUM-MAP.md),
[visual grouping](../features/FR-IDENTITY-GROUPING.md),
[candidate contradiction rules](../features/FR-IDENTITY-CANDIDATES.md).
