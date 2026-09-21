> 中文摘要
> 虚拟相册选择单库 SQLite WAL；映射、事件、引用成员与提交根同事务发布。
> 准备批次不等于提交，重启先校验并协调；歧义和分叉必须阻止后续修改。
> 旧标签与 G2 同意凭据保持可读，新版本不得把同意伪装成已执行映射。
> 浏览器决定经版本化导出、预览和确认迁入服务端；本 ADR 不代表实现或认证。

# ADR-0006 — Transactional virtual-album mapping publication

Status: proposed; date: 2026-09-21; owner: Art Curator maintainers.
Requirement and AC trace: INV-M / AC-INV-M-01, FR-ALBUM-MAP-001/003/006,
NFR-ALBUM-MAP-001 / AC-NFR-ALBUM-MAP-001-01,
FR-ALBUM-VISION-003/005, FR-ALBUM-NEGOTIATE-003/004, FR-PERSIST-001,
NFR-SPEC-001. Supporting acceptance criteria are listed below.
Supersedes: none; resolves the backend choice requested by NFR-ALBUM-MAP-001
on acceptance, not any invariant, existing wire contract or qualification gate.
Superseded-by: none.

## Context

G5 needs authoritative content-bound mapping, deferred decisions and atomic
publication before G3 cluster naming can graduate. G4 needs the same batch/undo
boundary; G6 remains separately authorized physical export. INV-M (映射优先于移动)
is unchanged, including its proposed constitutional status. ADR-0005 permission
does not enable contextual grouping in the frozen G2 implementation.

The supplied read-only inventory finds no album mapping store today: no
schema/library/revision lineage, eight-state disposition, subject/typed-relation
model, decider basis, per-metric scores, human verification, batch/operation IDs,
timestamps, evidence references, flags/notes/hypotheses/revisit state, view
projection, full-hash legacy import/export or prepared/commit-root protocol.
Existing character sidecars and browser journals are not that store.

Reusable patterns, not evidence of cross-artifact atomicity: `identity_store.py`
`atomic_bytes` (lines 30–36) and `stage` (99–120); `_moves.batch_lock`;
`journal.py` hash-framed records; `undo.py` reverse-ledger idempotence; consent
operation-ID replay. Output-directory locks alone cannot admit one library writer.

Constraints: Windows local storage without directory-fsync guarantees; single-user
local tool; approximately 26,876 images; portable exchange; no heavyweight service
or dependency. Before-images and one idempotent inverse batch must preserve later
human edits. None of the backend costs below are measured timings or space results.
They are algorithmic expectations to be qualified on ALBUM-PERF-v1.

## Decision and alternatives

Choose **one local SQLite database in WAL mode, with versioned migrations**, using
Python's existing standard-library SQLite binding. Keep authoritative mapping,
immutable decision events, before-images, reference membership/support, registry
state, evidence payloads needed for recovery, batch records and publication root
in this database. JSON/JSONL/CSV sidecars, memory indexes and gallery views become
revision-bound projections or exports, never a second writable authority.

This is option (b), not a separate application snapshot-plus-log storage engine:
SQLite supplies the transactional substrate; application events are audit/undo
records inside its transaction, not a separately appended authoritative file.
No atomicity is claimed across attached databases, legacy sidecars or source files.

### Alternatives considered and rejected

| Criterion | (a) JSON document + prepared temp + atomic root rename + digest manifest | (b) SQLite WAL + migrations — chosen | (c) Append-only event log + periodic snapshot/compaction | (d) Hybrid authoritative snapshot + log |
|---|---|---|---|---|
| Multi-file atomicity | Works logically only with immutable complete generations and one root; sequential sidecar replacement does not work | All authoritative artifacts and root share one DB transaction; external files are projections | Framed batch commit can be authoritative, but projections/references must replay from exactly its committed prefix | Must bind snapshot boundary, log suffix and references to one extra root; two independent authorities are unsafe |
| Windows crash/restart | Rename visibility is not directory durability; custom manifest, orphan and missing-generation recovery required | SQLite WAL recovery plus application digest/lineage checks; no invented directory-fsync promise | Torn-tail/commit-frame recovery and checkpoint handoff are custom; never simply truncate ambiguous human events | All log recovery plus generation/root handoff recovery; largest custom state space |
| Single writer | New library-wide lock and parent compare required | Library-wide admission plus DB writer serialization and root compare | New library-wide append lock, fencing and parent compare | New library-wide lock across snapshot, log and root |
| Incremental cost at 26k images | Full document serialize/hash/write for a one-row edit, O(N); complete generations amplify cost | Changed rows/index pages/events, approximately O(k) payload plus indexing; full exports/startup verification may be O(N+history) | O(k) append, but replay/query indexes and periodic O(N) snapshot needed | O(k) append between O(N) snapshots; dual-state validation adds work |
| History/compaction | Full revisions grow O(N × batches) without custom dedup; before-images still needed | Events grow O(changes); checkpoint bounds WAL, not audit history; explicit retention below | Log grows O(changes); compaction must preserve before-images, dedup keys and proof of prefix | Snapshot/log retention and reader pinning must be coordinated; easy to discard undo lineage |
| Portable exchange | Native JSON is easy, but root, evidence and complete history must travel together | Versioned logical JSON bundle; never copy only a live DB file | JSONL is portable only with schema, ordering, framing and snapshot boundary definitions | Bundle must carry both halves and exact boundary |
| Undo | Extra event/before-image ledger; JSON overwrite is not undo | Before/after images, row event tokens, supports and inverse receipt commit together | Natural inverse events; current-row conflict checking needs deterministic replay | Inverse events must reconcile snapshot row versions and log positions |
| Testability | Many custom filesystem cutpoints, root loss and generation-GC races | SQLite fault/reopen tests plus finite prepared/committed/root application states | Every frame/tail/replay/schema-upcast/compaction cutpoint must be tested | Combined failure matrix of (a) and (c), plus boundary divergence |
| Dependency weight | Standard library, but custom transaction engine | Standard-library binding, embedded runtime; no server/ORM/new heavy package | Standard library, but custom journal/index/recovery engine | Standard library possible; most application machinery |

Decisive reasons: a single transaction includes the map, human event, reference
support and inverse receipt; incremental edits avoid a whole-library JSON rewrite;
WAL recovery is delegated to an established local engine rather than a new Windows
filesystem publication implementation. Reject (a) as primary storage because its
whole-document writes/history amplification and custom durability reconciliation
buy no required advantage beyond exchange simplicity. Reject (c) because rebuilding
queryable views, migration-aware replay and safe history compaction recreates a
transactional store. Reject (d) because independently durable snapshot/log halves
add a publication boundary without a demonstrated need. These are fit/complexity
disqualifiers, not claims that the alternatives cannot be implemented correctly.

### Winner's exact invariants and identity impact

These clauses elaborate MAP-001/003/006 and NFR-ALBUM-MAP-001; they add no independent
constitutional rule. Mapping semantics use `album-map-v1`; storage protocol uses
`album-store-v1` with DB migration level `user_version=1` initially. Future SQL
layout migrations increment that level and a checksum-bearing migration ledger;
semantic changes separately version the mapping/event/exchange contracts. Model,
rendering, numerical thresholds and execution profiles are not changed here.

1. **One library, one authority.** An opaque persistent `library_id` is independent
   of report fingerprint and output path. All output routes resolve the registered
   canonical DB for that library. A library-keyed OS-held exclusive lock spans
   admission, prepare, publish and reconciliation; the OS releases it on process
   death. PID files/timestamps alone do not prove ownership. A second coordinator
   fails busy without writing. An unexpected second writable DB with the same
   library ID is a fork and blocks admission; copies are read-only exports until
   explicitly imported/forked. Windows path aliases must resolve to the same store.
2. **One committed view.** A read transaction pins root `(library_id, revision,
   root_digest)` before reading any mapping, event or reference state. All pages of
   a view use that snapshot or a revision-pinned materialization; never mix latest
   rows across requests. Prepared rows are invisible to album readers. Missing
   source files affect occurrence availability, not decision retention.
3. **Complete state.** Preserve every MAP-001 field at image/subject/relation scope,
   separate nullable metric units/profiles, nonempty evidence and typed decider.
   States are exactly `assigned`, `hypothesis`, `deferred`, `unknown-foreign`,
   `original-design`, `ordinary`, `non-character`, `pending`. Preserve MAP summary
   priority and six entity types, many-to-many relations and per-relation verified
   status. Human notes and revisit triggers survive logical archive/exchange;
   they are never scoring inputs. `suggested_verified` never sets `verified`.
4. **Immutable identity and causality.** Full image SHA-256 is authoritative;
   occurrence, entity and subject IDs survive locator/name changes. Subjects bind
   image hash, detection/crop identity and profile; a new detection cannot reuse an
   unrelated subject. Cluster member snapshots have content/profile-bound IDs.
   Batch/operation IDs are unique within a library, with canonical request digests.
   Identical replay returns its existing outcome; changed payload under one ID
   is rejected, including after restart, migration, export and undo.
5. **Atomic lineage.** Revision zero is an explicitly initialized empty root;
   every later committed revision has one committed parent and one committed batch.
   Prepared batches include expected parent/root, actor or policy/version, consent
   and evidence digests, frozen members, preview, before/after images and row tokens.
   Root changes only by compare-and-swap inside the publication transaction.
   There is no timestamp-based merge or newest-file selection.
6. **No authoritative external dependency at commit.** Small immutable report,
   consent, profile, member and event payloads needed to prove a decision are stored
   in DB artifact records by digest, including imported original bytes. Large
   vectors/crops remain external content-addressed inputs, validated before prepare
   and publication; missing inputs later disable dependent computation, not erase
   a historical decision. Reference membership, supports and revocation state are
   authoritative in DB. Derived retrieval indexes are usable only if their
   revision/profile/support digest matches root; otherwise unavailable/rebuild.
7. **No source mutation.** Mapping and mapping undo never move or rewrite originals.
   Existing sidecar mutators cannot run as an alternative writer after library
   enrollment: route them through mapping transactions or refuse writes for that
   library. Standalone legacy libraries remain supported until explicit enrollment.

### Prepared / commit / root publication and recovery

The marker names below are logical DB records, not a promise to atomically rename
several files. There is no filesystem `CURRENT` pointer with competing authority.
Use WAL, `synchronous=FULL` and foreign-key enforcement, verify effective settings
on writer connections, and use explicit transactions (`BEGIN IMMEDIATE` for writes).
Run on a supported local filesystem, not a network share or live sync folder.
Record Python/SQLite runtime, OS, filesystem and configuration in evidence. Admit
only a SQLite build containing the WAL-reset fix (3.51.3 or later, or documented
fixed backport such as 3.44.6/3.50.7); the installed runtime is not qualified here.
One coordinator connection owns writes/checkpoints. No automatic weaker mode fallback.

Digest protocol `album-canonical-json-v1`: UTF-8, sorted object keys, compact JSON,
no NaN/Infinity, schema-defined finite numeric encoding frozen in golden fixtures,
preserved array order except explicitly set-like IDs sorted by their full value.
Opaque original imported bytes have a separate byte digest. Artifact entries bind
kind, logical ID, schema, byte length and SHA-256 of exact canonical payload bytes.
A batch manifest contains sorted changed/deleted artifact entries, before/after
digests and row tokens, operation IDs, evidence IDs and expected parent root digest.
Its digest plus parent digest and revision identity define the new root digest;
the genesis manifest fixes the starting state. Deletions are explicit tombstones.
The chain covers unchanged state through its parent; startup replay/materialization
comparison detects edits to rows not touched by the latest batch. Digest checks
detect corruption/divergence, not authenticity against an attacker rewriting all data.

1. **Admit and reconcile.** Take library lock, open existing DB without creating a
   missing replacement, validate schema/ledger/library binding and recover WAL via
   SQLite. Reconcile as below before allowing mutations. Unknown major or unsupported
   migration blocks writes. Freeze and validate request, expected parent, content,
   evidence, consent freshness, row tokens and capacity; render MAP-003 preview.
2. **Prepare (transaction P).** Insert immutable artifacts and `prepared` batch,
   before-images, manifest and proposed revision. Commit P with FULL synchronization;
   reread and validate stored digests. Root and live projections remain unchanged.
   Only one unresolved prepared batch per library is admitted. Store the affirmative
   authorization binding this exact preview/request; preparation is not execution.
3. **Publish (transaction C).** Revalidate parent and all required digests/authority,
   including revocation and changed external inputs. Apply exact prepared mutations
   to current materializations, append events/reference supports, insert commit
   marker `(batch_id, revision, parent_revision, manifest_digest, root_digest)`,
   mark batch committed, and update singleton root with an expected-parent compare.
   All occur in C, including inverse result/conflict receipt when applicable.
   Any failed comparison rolls back C; never recompute a different preview silently.
4. **Acknowledge and project.** Acknowledge only after C succeeds and the selected
   root/marker are validated. A lost response is retried using the same operation
   ID. Export/index work can follow, stamped with revision/digest; its failure does
   not roll back committed human decisions. Export via temp, flush, validate, atomic
   replacement and digest receipt; incomplete exports cannot authorize anything.
5. **Restart reconciliation.** Before mutation, run SQLite integrity and FK checks;
   validate migration ledger, committed parent chain, every authoritative artifact
   digest and event sequence; reconstruct expected state from genesis/events and
   compare materialized map/reference state. Validate prepared batches and inverse
   uniqueness/results. Retain a recovery receipt with observed roots/digests,
   batch IDs, outcome, conflicts, runtime and explicit next action.

| Observed state / cutpoint | Required reconciliation and reader result |
|---|---|
| Killed before P commits; torn uncommitted WAL tail | SQLite recovers the last valid transaction; no visible new batch/root. Never hand-truncate WAL. If integrity/digests fail, preserve and block. |
| Valid prepared batch, no commit marker, root still parent | Old committed revision only. Mark recovery-required; no automatic commit on restart. Explicit resume of the same request revalidates all gates, or explicit abort retains prepared evidence and clears admission. |
| Restart during C (row writes, marker insert or root update) | SQLite yields all of C or none. None follows prepared-only recovery; all validates as committed. A logical mixture is corruption, not a repairable partial success. |
| C committed, reply/export absent | Return original receipt for identical operation; rebuild missing projections from selected revision. Never execute it again. |
| Commit marker without matching root lineage, root without commit, bad/missing digest, duplicate inverse or parent fork | Block mutations; preserve DB/WAL/SHM as a quiesced incident set before attempted repair, record failure outside suspect DB if needed. No automatic rollback to a convenient ancestor. |
| Valid old root survives but a retained acknowledged receipt claims a missing newer commit | Treat as rollback/divergence and block. Require explicit restore/reconciliation, never claim that the event did not happen. |
| Working-copy DB/materialized rows changed outside protocol, or import has stale expected parent | Block publication, retain incoming bytes and observed digest conflicts; explicit rebase requires a new preview, operation ID and affirmative confirmation. Never last-writer-wins. |
| External projection differs from its receipt | Quarantine/preserve divergent bytes; block mutation until it is classified as rebuildable derived data or explicitly imported human edits. Never ingest it implicitly or silently overwrite potential edits. |
| Restart during inverse batch or checkpoint | Same old-or-new root rule; recover through SQLite, validate inverse key/result, never issue a second inverse or delete WAL to clear the error. |

Only a validated committed revision may be offered read-only during explicit
recovery; if no such revision can be proven, show recovery status without an album
view. Repairs retain damaged evidence and require a checked backup/import plus
operator-selected reconciliation receipt. A standalone replaced DB with no retained
external receipt cannot prove that later history once existed: this is a stated
rollback-detection limit, not permission to guess. FULL synchronization relies on
the OS/device honoring flushes; Windows power-loss survival remains unqualified
until scoped fault evidence exists. Process-kill tests are not power-loss tests.

### Batch undo, retention, migration and portable exchange

Undo previews one inverse batch bound to the original committed batch and current
parent root. Eligibility compares each affected logical image/subject/relation or
reference-support row's last-event token **and** after-image digest with the original
batch; value equality alone misses an edit-away-and-back (ABA). Restore before-images
only for matching rows, and preserve all later edits with explicit conflict IDs.
An all-conflict undo still commits one zero-change inverse receipt marked partial
undo. Unchanged rows restore exactly; disjoint later edits need not block eligible
rows. Recompute image summaries from surviving subject/relations in the same C.
Reference supports are independently identified: retract only supports introduced
by the original event, preserve independent support, and make dependent unconfirmed
suggestions stale/review. Inactive contextual history never re-enters retrieval.
The unique inverse key is `(library_id, original_batch_id)`; repeated undo returns
the same result and never retries formerly conflicting rows. Original/inverse events
remain inspectable. Further correction is a new previewed batch, not another undo.

WAL checkpointing is physical maintenance, not event compaction. Schedule bounded
reader transactions and coordinator checkpoints; checkpoint busy means retry later,
not deletion of WAL. Measure WAL growth/disk reserve and block new preparations when
capacity is insufficient. Retain all committed events, before-images, inverse and
operation dedup receipts in v1; do not silently age out undo. Remove only rebuildable
projections and explicitly aborted staging payloads after preserving their audit
record/incident evidence. Snapshot acceleration must retain event identity and
verify against the chain. History pruning needs a later reviewed retention contract;
VACUUM/checkpoint cannot substitute for it.

Before any SQL migration, create and validate a consistent SQLite backup through
the backup API, with library/root/schema digest receipt; never copy only a live
`.db` while WAL may contain commits. Under library admission, apply each migration
and its checksum ledger entry transactionally, compare semantic state/IDs/undo
outcomes, then advance `user_version`. Failure retains the old usable state or
blocks recovery explicitly. Downgrade uses a validated pre-migration backup only
with explicit reconciliation of later events, never by decrementing a version.

Portable `album-map-export-v1` is a logical JSON bundle (optionally packaged with
digest-addressed evidence), not a raw live DB copy. Bind schema, library/root/parent,
profiles, full hashes, entity/subject/occurrence IDs, all mapping fields, original
import payloads, events, before-images, operation/inverse receipts and reference
supports in a manifest; preserve unknown optional fields at every nesting level.
Unknown majors or required capabilities block mutation; extensions remain opaque,
not executable. Round-trip comparator is logical identity/state, not SQLite bytes.
Locators can be remapped with explicit occurrence binding without changing content
IDs. Missing originals remain unavailable. Legacy sha16 resolution requires a
manifest with a unique full-hash/crop/profile association; collisions or missing
bindings block import. Snapshot-only exports must be labelled non-restorable for
history/undo, not accepted as full backups. Keep export/backup receipts and the last
validated backup plus every pre-migration backup in v1; cleanup requires explicit
operator policy and cannot discard the sole recoverable human history.

### Contract-revision plan — do not widen the frozen v1 parsers in place

This ADR edits none of these files. Acceptance is not wire compatibility approval:
implement schema-dispatched v1/v2 readers and consumer tests before enabling v2
writers. Old digest inputs/receipts stay byte-preserved; any normalized v2 record
links the original digest instead of rewriting historical hash chains.

| Current literal / boundary | Required version and replacement | Backward compatibility and old artifacts that must still parse |
|---|---|---|
| `identity_schema.Label.action = Literal["confirm","new","ignore","wrong_box"]` (148); `LabelEnvelope.version=1` | Keep `LabelV1`; add `LabelV2` under `LabelEnvelope.version=2`, with existing actions plus `set_disposition`. The new action carries one of all eight dispositions, typed target IDs, notes/hypotheses/revisit fields and content/profile binding; confirmation remains a distinct explicit assertion. Rich cluster operations use mapping-event v1, not invented v1 label strings. | All four-action `character_labels.json` v1 envelopes, including optional baseline/variant marks, remain accepted by the legacy reader/adapter. `ignore`/`wrong_box` retain exclusion/box semantics, never become deferred/non-character; `new` names an entity, never implies original-design. Existing old clients reject v2 explicitly. No lossy automatic v1 export of new states. |
| `identity_labels.Registry.version: Literal[1] = 1` (24) | Introduce `RegistryV2`, `version=2`, with library/revision lineage and typed event/reference support projection from the store. This is distinct from DB migration level and `album-map-v1`. | Parse/validate all v1 `characters.json` event chains, references, exclusions and reference_version with original digest algorithm. Import as provenance-bound legacy events plus a migration receipt; do not renumber/rehash historical events or fabricate batch history. Preserve original bytes. v1-only writers refuse enrolled v2 libraries. |
| `negotiation_consent.ConsentReceipt.mapping_mutations: Literal[0] = 0` (77) | New discriminated `album-consent-v2` and `album-mapping-execution-v1` receipt contracts. Consent stays zero; execution receipt allows a nonnegative changed-image count only with committed batch/revision/root and consent reference. Never turn a consent receipt into a mutable execution counter. | Unversioned frozen G2 receipts/decisions/states parse as v1 only via the documented legacy entry point, retain zero and original receipt IDs, and remain authority-only. v2 reports/decisions bind a fresh mapping preview/parent; old active consent is not silently upgraded to authorization for an unseen batch. Old revoked/superseded receipts remain inspectable. |
| `negotiation_consent.Prediction` (54–61), frozen `prediction.* = null` | `album-negotiation-v1` → `album-negotiation-v2`; v2 prediction allows validated nonnegative nullable counts, explicit denominator/policy/preview/parent digests and missingness reason. It remains an estimate; actual execution counts live only in execution receipts. | Python fields already permit nullable integers; the closed boundary is the frozen G2 producer contract, not a Literal-null annotation. Existing v1 report/fixture and receipt `predicted` objects must keep parsing with null counts and `estimate=true`. Unknown is never zero; G5 alone does not invent G4 tier counts. |
| `negotiation_copy.Presentation.mapping_action_available: bool=False` (42) | Under `album-negotiation-v2`, use explicitly versioned presentation/capability data (`album-presentation-v2`, including standalone prompts); true requires an available qualified mapping executor, valid preview/authority and reconciled writable store. Defaults remain false. | This is already a bool, not `Literal[False]`; changing its operational meaning still requires the enclosing contract bump. Old initial-intent/report presentations parse as v1 and stay disabled; missing version/capability never enables mutation. Preserve old Chinese copy-as-data; v2 boundary copy must distinguish consent, preview and committed outcome. |

Publish new G2 document sections/fixtures under those explicit versions before
consumer rollout; retain the frozen v1 section and `negotiation-report.example.json`
as compatibility fixtures. Require explicit version dispatch, not trial parsing into
a more permissive model. Unknown schema majors refuse application. Keep
`context_enabled=false` and inherited `verified=false`; no contextual enablement,
physical move authority, threshold override or source-write capability follows from
these bumps. New report digest requires a new matching decision/consent; operation-ID
replay remains exact across old and new namespaces.

### Browser-local journal migration

Mirror the existing **draft → versioned download → local apply → receipt → rebuild**
pattern, not automatic localStorage synchronization. Existing envelopes are
`character_labels.json` `{version:1, source:"review-studio", corpus_fingerprint,
labels:[...]}` and `alias-decisions.json` with the same header plus
`semantic_profile` and `decisions:[{reference_name,wd_tag,decision}]`. Alias approval
does not confirm any image identity. Both existing formats remain supported.

1. Export a new `album-mapping-decisions.json` envelope with
   `schema_version:"album-mapping-decisions-v1"`, source, corpus fingerprint,
   library ID (or explicit unbound-import status), profile/manifest/member digests,
   expected parent revision/root, export ID, actor, ordered operations and original
   journal payload/digest. Capture `journal.clusterDecisions` and `journal.faceLabels`
   plus relevant history/undone markers. A local draft is not a server commitment.
2. Resolve cluster integers/face IDs/sha16 against the frozen producer provenance:
   full image/crop hashes, detection profile and exact cluster member sets. Never
   resolve by current display name, nearest cluster or newest report. Missing or
   ambiguous bindings keep the entire proposed batch pending with error IDs.
3. Import to staging read-only, validate versions and digests, translate to typed
   mapping-event v1 commands (`name_cluster`, `split_cluster`, `merge_cluster`,
   `exclude_member`, `set_disposition`, `confirm_relation`, legacy face actions).
   Translate only recorded intent: cluster merge is not entity merge, undone
   drafts are inactive, and current faceLabels alone are a state snapshot, not a
   complete history. Preserve absent historical information as unknown; server
   before-images come from current committed state, never invented browser history.
4. Show selected-member and per-subject before/after preview, typed-entity resolution,
   reference effects, conflicts and consent requirements. Reaffirm confirmation
   against full content/member bindings before any verified relation/reference is
   admitted. Legacy exclusions remain exclusions. Name/split/merge freeze exact
   selected members; neither sibling faces nor future cluster members are covered.
5. Apply as one mapping batch via P/C with server decider identity, timestamps,
   before-images and evidence linking the original envelope. Stable operation IDs
   bind library + exported draft identity and canonical payload; legacy exports
   lacking IDs receive deterministic import IDs from source-envelope digest and
   entry identity. Persist those IDs in the receipt for all retries. Recognize
   duplicate face state/cluster commands during preview rather than apply twice.
6. Return a receipt binding envelope digest, batch/root/revision, applied/conflict
   IDs and inverse availability. Browser marks only acknowledged matching drafts
   applied, retains exported backup/history and refreshes from committed projection.
   Lost response replays the same IDs; it never generates a second batch. New edits
   to an applied draft get new IDs/preview. Offline review/export remains usable.

G5 owns import/staging/transaction/undo contracts; G3 supplies richer cluster command
semantics and client affordances against them. Persistence completion alone does
not certify naming/split/merge. No direct server endpoint or browser framework is
chosen here; local companion/CLI transport can consume the same portable envelope.

## Consequences and evidence

Benefits: one auditable commit boundary; typed multi-membership and deferred state
independent of source location; exact operation replay and conflict-preserving undo;
logical exchange independent of SQLite's on-disk layout. Costs: SQL migrations,
legacy adapters, revision-aware readers, strict enrollment of every mutator, digest
validation and retained before-images. Standard-library availability does not prove
the bundled SQLite runtime meets admission requirements.

### Risks, rollback and revisit triggers

Disk exhaustion, long readers starving checkpoints, antivirus/file-lock errors,
unsupported/network filesystems, stale sidecar writers, divergent copies and
unsupported runtime builds deny mutation rather than weaken guarantees. Full
startup validation and retained history may become expensive; benchmark them before
claiming interactive latency or bounded storage. Revisit this decision if measured
ALBUM-PERF-v1 costs exceed predeclared product budgets, genuine multi-writer/network
use becomes required, or publication/undo tests find lost events or mixed revisions.
Do not change backend automatically on failure. Revoke write capability, preserve
evidence, and recover through a validated backup/exchange with explicit reconciliation.
No performance, power-loss, identity-accuracy or implementation certification is
issued by this ADR. Status stays proposed pending maintainer acceptance; acceptance
selects the architecture, while G5 graduation still requires the following evidence.

### Acceptance criteria implied by this decision

Reuse stable owning AC IDs rather than allocate orphan ADR-only requirements.
The rows below refine their implementation/evidence checklist without claiming
feature records were edited. Scope: their owning records' S/E/T0–T4; status:
proposed/unverified here. Evidence paths are future release-bundle paths, not files
generated in this task. Every run freezes fixture version, generator/seed or licensed
snapshot, full SHA-256, expected results, schema/profile/runtime and hardware before
testing. Public manifests expose aliases/digests and limitations, not private paths.

| Stable AC ID | Method | Fixture | Comparator | Evidence artifact |
|---|---|---|---|---|
| AC-FR-ALBUM-MAP-001-01 | Schema/identity, view and portable round-trip tests; legacy adapters and extension preservation | ALBUM-MAP-v1 | Exact full hashes, stable occurrence/entity/subject IDs across rename/relocation, all MAP fields/relations/counts/lineage, zero ambiguous short-ID imports; one pinned revision per view | `evidence/AC-FR-ALBUM-MAP-001-01.json` |
| AC-FR-ALBUM-VISION-003-01 | Typed namespace/disposition matrix including v1/v2 label conversions | ALBUM-MAP-v1 | All six types/eight states preserved; same-name IDs distinct; ignore/wrong_box/no-face never auto-converted to resolved categories | `evidence/AC-FR-ALBUM-VISION-003-01.json` |
| AC-FR-ALBUM-MAP-003-01 | Commit/inverse/replay, ABA and intervening human edits/reference supports, all-conflict case | ALBUM-MAP-v1 | One inverse; exact eligible before-state, zero later edits lost, exact conflict/count receipt, identical repeated result, no unsupported references resurrected | `evidence/AC-FR-ALBUM-MAP-003-01.json` |
| AC-FR-ALBUM-MAP-006-01 | Deferred reopen/re-defer, clock/evidence triggers, logical archive and exchange | ALBUM-MAP-v1 | Every note/hypothesis/revisit setting retained; one notification per trigger revision; zero silent confirmation/training | `evidence/AC-FR-ALBUM-MAP-006-01.json` |
| AC-NFR-ALBUM-MAP-001-01 | Inject failure before/after P and C, each artifact/row/marker/root write, sync, acknowledgement, inverse, migration, backup/export and checkpoint; second process through different output/path alias | ALBUM-MAP-v1 | Exactly old or complete new revision; one library writer; zero lost acknowledged human events in qualified fault model; all digest/parent/fork ambiguities block with receipt; identical operation replay; state/undo unchanged by SQL migration | `evidence/AC-NFR-ALBUM-MAP-001-01.json` |
| AC-FR-ALBUM-NEGOTIATE-003-01 | Frozen/new schema dispatch, nine mode/scope combinations, dismissal, stale consent/replay/capability tests | ALBUM-FLOW-v1 and ALBUM-FOLDER-v1, extended with ALBUM-CONTRACT-v1 and ALBUM-MAP-v1 | Exact mode consequences; v1 reports/receipts/decisions still parse; zero pre-consent changes, v1 nonzero mutations or implied execution; changed parent/report requires fresh preview/consent; unknown majors refuse | `evidence/AC-FR-ALBUM-NEGOTIATE-003-01.json` |
| AC-FR-ALBUM-NEGOTIATE-004-01 | Versioned copy/data contract checks; later client walkthrough for enabled/disabled mapping | ALBUM-FOLDER-v1 and ALBUM-FLOW-v1, extended with ALBUM-CONTRACT-v1 | Unknown remains unknown, v1 disabled, true capability never substitutes for commit receipt; required Chinese data/counts exact, no unresolved placeholders; zero clipped/unreachable controls at 520/900/1440 and keyboard-only; no UI qualification from string tests alone | `evidence/AC-FR-ALBUM-NEGOTIATE-004-01.json` |
| AC-FR-ALBUM-MAP-004-01 | Browser export/import/name/split/merge/undo with stale member set and duplicate delivery | ALBUM-MAP-v1 | Exact selected members/partitions/lineage, zero sibling/future attribution, conflicts preserved; no local draft mistaken for server event | `evidence/AC-FR-ALBUM-MAP-004-01.json` |
| AC-INV-M-01 | Filesystem write tracing and source hashes through mapping/import/export/undo | ALBUM-FLOW-v1 | Zero original writes/moves; identical source bytes/paths; mapped views work without physical export | `evidence/AC-INV-M-01.json` |
| AC-FR-ALBUM-VISION-005-01 | G5/G3/G4 dependency manifest review | ALBUM-CONTRACT-v1 | No G3/G4 graduation before required G5 mapping/recovery/undo receipts; acceptance of ADR is not gate completion | `evidence/AC-FR-ALBUM-VISION-005-01.json` |
| AC-NFR-SPEC-001-01 | Contract/profile/fixture/evidence manifest audit | SPEC-TREE-v1 and ALBUM-CONTRACT-v1 | Zero unversioned changed semantics, missing trace or unsupported verified claim; frozen v1 compatibility fixtures retained | `evidence/AC-NFR-SPEC-001-01.json` |

The publication fixture must distinguish process-kill, injected I/O/short-write,
WAL damage and actual power-loss cases in its receipt. Include tampered unchanged
rows, missing evidence, divergent sidecars, crash after committed response loss,
partial inverse with later edits, migration interruption, full disk and Windows
sharing violations. Unexecuted fault classes remain explicitly unqualified.
ALBUM-PERF-v1 adds a predeclared measurement matrix for 1/small-batch/26,876-image
updates, cold restart verification, long readers, checkpoint, export/import and
history growth: record wall time, bytes written, peak memory, DB/WAL/history sizes
and recovery time. Budgets require owner approval before measurement; this ADR
asserts neither measured results nor an invented latency threshold.

### Recommended spec/index follow-up — not made by this task

- Add this exact index row to `specs/README.md` after ADR-0005:
  `| [ADR-0006](adr/ADR-0006-transactional-album-mapping.md) | Proposed SQLite WAL mapping publication, recovery, batch undo and versioned legacy/G2 migration; not implemented or verified |`.
- In NFR-ALBUM-MAP-001 link this backend decision and its acceptance status; preserve
  the existing unqualified crash/power-loss warning and AC ID. MAP-001/003/006 can
  link the schema/exchange, inverse and deferred persistence elaborations here.
- In FR-ALBUM-VISION keep G5 a prerequisite of G3/G4; replace the open backend item
  only after ADR acceptance, with implementation/evidence still pending. Do not
  alter INV-M/INV-P or imply constitutional approval from this storage decision.
- Through NFR-SPEC-001, amend owning feature AC detail/fixture manifests for the
  checklist above and assign any additional performance budgets to the ingestion
  storage/performance owners before qualification; no new AC IDs are reserved here.
- Version the G2 client document and identity/exchange documentation with dual-read
  compatibility, new fixture/schema references and enrollment restrictions before
  implementation release. Keep old frozen examples and v1 interpretation intact.

References: [ADR template](../templates/ADR.md),
[spec lifecycle and index](../README.md),
[album mapping, especially NFR-ALBUM-MAP-001](../features/FR-ALBUM-MAP.md),
[vision, INV-M, taxonomy and fixture registry](../features/FR-ALBUM-VISION.md),
[negotiation](../features/FR-ALBUM-NEGOTIATE.md),
[ADR-0002](ADR-0002-dry-run-first-moves.md),
[ADR-0005](ADR-0005-measured-context-assisted-grouping.md),
[frozen G2 contract](../../docs/pipeline/mode-negotiation.md),
[review export envelopes](../../tools/README.md),
[alias reconciliation](../../docs/alias-reconciliation.md),
`src/artcurator/{identity_schema,identity_labels,identity_store,negotiation_consent,negotiation_copy,journal,undo,_moves}.py`,
`tools/{build_gallery.py,gallery_candidates.js,gallery_aliases.js}`.
SQLite reference: [WAL transactions, checkpoints, portability limits and WAL-reset
fix](https://sqlite.org/wal.html) (consulted 2026-09-21); upstream behavior is not
application-specific Windows fault-injection evidence.
