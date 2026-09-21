> 中文摘要
> 导入到归档分八阶段推进；所有阶段均不修改源文件。
> 后台任务可暂停续跑，新文件按增量处理，进度与失败单列。
> 全库首轮约需两至三小时是规划估算，不是已认证的端到端承诺。
> 存储、逐动作成本和跨文件崩溃一致性都有明确预算或未认证边界。

# Album ingestion and execution contract

Owner: Art Curator maintainers. Status: proposed. English is normative.
Authority, fixture aliases and evidence lifecycle: [VISION](FR-ALBUM-VISION.md).
Dependencies: FR-ARCH-001/002, FR-CACHE-001, FR-WORKER-001, NFR-RESOURCE-001,
ADR-0001/0004, [NEGOTIATE](FR-ALBUM-NEGOTIATE.md), [MAP](FR-ALBUM-MAP.md).
This is orchestration above existing stages, not a claim that `run-all` already
includes identity, previews, studio, mode negotiation or album publication.

### FR-ALBUM-INGEST-001 — Eight-stage read-only state machine
When a user starts library ingestion, the coordinator shall execute `IDLE → INGEST → ANALYZE → PROPOSE → CONFIRM → FIRST-PASS → REVIEW → ARCHIVE` using durable stage barriers without modifying any source file.

Scope: S: album orchestration / E: local coordinator / T0–T4. Status: proposed.

| Stage | Inputs | Outputs and durable logical artifacts | Exit condition |
|---|---|---|---|
| IDLE | User-selected roots/handles, prior library revision | Draft job, permission/capacity check, model availability | Explicit start; read access and output admission pass |
| INGEST | Frozen root selection | Content/occurrence manifest, full hashes, decode status, thumbnails/previews, inventory delta | Every discovered occurrence accounted as indexed, duplicate, unavailable or failed |
| ANALYZE | Manifest, pinned profiles, compatible saved references | Detection/crop/embedding ledgers; clusters; anchors; model/memory candidates; per-folder measurement receipt | Requested signals completed or explicitly unavailable, no uncommitted evidence consumed |
| PROPOSE | Analysis digest | Negotiation report, representative wall, proposed inheritance, estimated first-pass counts/cost | Report sealed and user notified; partial evidence labelled |
| CONFIRM | Sealed report plus user choices/names | Consent receipt bound to snapshot/report/policy, selected folder IDs and cluster member digests | Explicit confirmation; dismiss/pause remains here |
| FIRST-PASS | Consent, validated evidence and current map revision | Idempotent batch plan, map revision, audit/review/none sets, before/after summary | Durable commit or explicit interrupted/recovery-required state |
| REVIEW | Committed map, audit sample and unresolved pool | Human events, notes, marks, split/merge/naming batches, revised references | User chooses logical archive; unresolved items may remain |
| ARCHIVE | Current map and review events | Read-only album snapshot, unresolved counts, exportable mapping/journal bundle | Snapshot sealed; optional physical export is a separate command |

- Artifact names above are logical contracts, not a new mandate to duplicate all
  existing sidecars. Each stage receipt binds job/run ID, parent revision, full
  input/output digests, semantic/execution IDs, counts, errors and commit state.
- Write boundaries are derived output storage only; no source metadata write,
  rename, move or delete in any stage, including ARCHIVE. Even output selection
  cannot authorize overwriting an original. Physical export belongs to MAP-007.
- Pause/failure/cancel are orthogonal job states with `resume_stage` and reason;
  they do not skip consent. Cancel retains validated artifacts and prior mappings.
  Retry resumes the failed stage; changing report inputs returns to PROPOSE;
  new consent follows any changed affected set, inheritance or policy.
- Review-triggered analysis creates a child analysis revision and new proposal;
  it never silently replaces human decisions. ARCHIVE can re-enter REVIEW or begin
  incremental INGEST. Missing models yield unavailable evidence/manual review,
  not implicit downloads, substitute models or manufactured non-character labels.
- AC-FR-ALBUM-INGEST-001-01: Method: transition-table integration test with write interception and hashes; fixture: ALBUM-FLOW-v1; comparator: every listed output/barrier present, invalid transitions rejected, zero source writes across success/failure/cancel and ARCHIVE; evidence `evidence/AC-FR-ALBUM-INGEST-001-01.json`.

### FR-ALBUM-INGEST-002 — Background control and honest progress
While an ingestion job is active, the coordinator shall expose background progress and pause/resume controls without requiring the review surface to remain open.

Scope: S: orchestration / E: selected local client plus job owner / T0–T4. Status: proposed.
- Progress record: stage, queued/running/completed/cached/failed/unavailable counts,
  current denominator and unit (files, unique images or faces), elapsed/load/compute/
  I/O time, provider, last heartbeat, saved checkpoint, next action and ETA range.
  Unknown inventory size displays discovered count, not a fabricated percentage.
  New faces change face denominators visibly; work does not appear to regress
  silently. Human wait time is separate from machine elapsed time.
- Default observable targets: progress refreshed within 2 s when the coordinator
  is responsive; worker heartbeat within 60 s; pause acknowledged within 2 s,
  scheduling stops immediately and in-flight work settles within its declared
  deadline (WD currently 240 s). Deadline expiration marks interruption, not success.
  Resume revalidates access and checkpoint. Stale heartbeat shows stalled state.
- Client closure never claims that a stopped browser job is still running. The
  G7 spike chooses a durable job owner; without one, closure requires an explicit
  pause/checkpoint and visible capability limitation, blocking background qualification.
- AC-FR-ALBUM-INGEST-002-01: Method: fake-clock and real process lifecycle tests including client closure/revoked access; fixture: ALBUM-FLOW-v1; comparator: 2 s/60 s/deadline bounds met, exact checkpoint resumed, zero hidden job loss or false completion; evidence `evidence/AC-FR-ALBUM-INGEST-002-01.json`.

### FR-ALBUM-INGEST-003 — Incremental inventory without decision loss
When files are added, changed, removed or rediscovered, the coordinator shall create a versioned inventory delta and process only invalidated evidence while preserving content-bound human history.

Scope: S: incremental album / E:* / T0–T4. Status: proposed.
- Full content SHA-256 identifies image content; occurrence IDs identify distinct
  locations. Metadata may select files to recheck but cannot replace content
  validation before evidence reuse. Identical bytes at new paths add occurrences,
  not repeated inference or repeated votes in reference memory.
- Changed bytes create a new image version with pending status; old decisions do
  not transfer by filename. Missing paths become unavailable occurrences; history
  and other existing copies survive. New files discovered after a frozen snapshot
  enter the next delta, not the active confirmation's member set.
- New references or profile changes invalidate dependent proposals, not human
  labels. Re-clustering can change membership and produces a diff/new snapshot;
  unaffected fixed-member IDs follow FR-STABLE-001, not sequential labels.
- AC-FR-ALBUM-INGEST-003-01: Method: add/rename/change/delete/replay integration test; fixture: ALBUM-FLOW-v1; comparator: zero duplicate inference for identical compatible content, zero path-based label transfers, exact expected delta and preserved prior event hashes; evidence `evidence/AC-FR-ALBUM-INGEST-003-01.json`.

### NFR-ALBUM-INGEST-001 — Throughput budgets with measured boundaries
When estimating or qualifying ingestion time, the coordinator shall disclose stage-specific measured boundaries and proposed budgets on the stated hardware rather than advertise inference-only rates as complete ingestion time.

Scope: S: pinned album identity/WD stages, no optional quality ensemble / E: Windows, 6 cores/12 threads, about 32 GB RAM, RTX 5060 Ti 16 GB, matched CUDA FP32 profiles / T2. Status: proposed budgets, historical observations only.

| Stage/boundary | Evidence observed | Proposed qualification ceiling or explicit gap |
|---|---|---|
| Scan + thumbnail + manifest | 12.448 s/300 = 0.04149 s/file; one paired run in 012 | Median ≤0.050 s/file on matched slice; preview measured separately |
| Preview generation | No isolated comparable receipt read | Instrument wall/bytes; predeclare budget before performance qualification |
| Face detect/crop | Historical 0.059–0.156 s/image | Median ≤0.18 s/image on matched labelled workload; face coverage reported |
| Crop embedding stage | About 0.135–0.140 s/face, including publication | Median ≤0.16 s/face; matched FP32 only, no rejected FP16 shortcut |
| Whole-image SigLIP, if selected | 1,580/282.34 ≈5.60 images/s; final matrix assembly excluded | Median ≥5.0 images/s at same boundary; assembly timed separately |
| WD CUDA | 206.37 s/1,580 ≈0.131 s/image inference; 320.98 s wall; small probe ≈0.22 s/image | Median ≤0.25 s/image at full stage boundary; crops reported separately |
| WD CPU | Small probes about 3.3–4.0 s/image or crop; one median 4.047 s | Diagnostic planning ceiling 4.5 s/item, not T2 or CPU certification |
| Clustering, anchors, grouping, candidates | Cluster 0.676–40.522 s; anchor 40.554–62.399 s; grouping 0.597–5.303 s on smaller snapshots | No linear full-library guarantee; record separate walls and predeclare shape-specific ceilings |
| Proposal/map publication/studio build | No complete album-stage measurement | Record wall, count and bytes; budget required before qualification |
| CONFIRM/REVIEW | Human-controlled duration | No completion deadline; show waiting separately |
| ARCHIVE | Logical snapshot only | Time snapshot publication; physical copy cost excluded and separately quoted |

- Source boundaries: 012-PERFORMANCE, `docs/pipeline/identity-v2.md`,
  `docs/pipeline/identity-grouping.md`, `docs/pipeline/wd-memory.md`, private
  `out/library-audit/report.md`. Provider lists do not prove GPU placement for
  every operation; record actual execution and fallbacks.
- Planning envelope: approximately **2–3 h for a 26,876-image first pass** on the
  RTX 5060 Ti, excluding downloads, human waits, optional quality scorers and moves.
  This is an estimate based on component receipts, not an uninterrupted measured
  full-library run. Proposed machine-time target ≤3 h applies only to a frozen
  workload with its face count/stage roster declared. Extra faces, whole-image plus
  crop passes, cache misses, quadratic grouping and contention can exceed it;
  recompute ETA, disclose overrun, never silently skip stages to meet the figure.
- Qualification uses at least ten randomized-order cold/warm paired slice runs,
  plus a full-run receipt; reports medians, p95, load, cache hits, disk/runtime and
  host/board peaks. NFR-GATE-007 regression ratios still apply. Unknown ceilings
  block performance qualification, not disclosed experimental operation.
- AC-NFR-ALBUM-INGEST-001-01: Method: instrumented paired stage benchmark and full-run trace; fixture: ALBUM-PERF-v1; comparator: declared ceilings above and NFR-GATE-007, zero omitted selected stages or boundary conflation; unmeasured ceilings yield inconclusive, not pass; evidence `evidence/AC-NFR-ALBUM-INGEST-001-01.json`.

### NFR-ALBUM-INGEST-002 — Derived-storage admission
When admitting derived artifacts, the coordinator shall estimate, reserve and report storage by artifact class and stop derived writes before exceeding the approved quota.

Scope: S: album artifacts / E: local storage / T0–T4. Status: proposed.
- Configurable initial quota: 8 GiB derived storage per library, with 1 GiB free-disk
  reserve; admission requires free space ≥ incremental reservation + reserve.
  Exclude originals, downloaded weights/environments and optional physical copies
  from this quota but display their separate sizes and required headroom.
- Planning caps: thumbnails 64 KiB/image, previews 192 KiB/image (≤1024 px), compact
  evidence/mapping/index 16 KiB/image, crops 64 KiB/face, plus matrices `rows × dims ×
  bytes_per_component` and headers. Cap breach can defer a derived asset with reason,
  not lower model input fidelity silently. Quotas can be explicitly increased.
- At 26,876 images, 272 KiB/image is about 6.97 GiB before crops/matrices; the 8 GiB
  default is admission policy, not a claim every face count fits. A 1,580×1,152 FP32
  audit matrix is 7,280,640 payload bytes (7,280,768 with observed header), and its
  tag JSONL was 5,641,043 bytes. These support explicit linear accounting only,
  not a measured total-album storage claim. FP16 storage needs its profile gate.
- Account temporary replacements, old revisions and caches too. Rebuildable caches
  may be evicted with recorded policy; human journal, undo before-images and current
  committed mapping cannot be evicted to conceal quota overruns. Retention expiry
  requires explicit backup/prune consent and visible loss of undo scope.
- AC-NFR-ALBUM-INGEST-002-01: Method: size accounting and disk-full fault injection; fixture: ALBUM-PERF-v1 and ALBUM-FLOW-v1; comparator: actual reserved/retained bytes within selected quota and reserve, zero lost human/undo data or source writes; evidence `evidence/AC-NFR-ALBUM-INGEST-002-01.json`.

### NFR-ALBUM-INGEST-003 — Resumability and idempotency
When work is replayed after pause, retry or process failure, the coordinator shall reuse only validated compatible commits and produce the same logical results as uninterrupted execution without duplicate mapping events.

Scope: S: jobs and stage publication / E:* / T0–T4. Status: proposed.
- Idempotency key binds operation type, input snapshot, profiles, reference version,
  policy/consent digest and intended member set. Retry uses the same key; deliberate
  new decisions use a new operation with explicit parent revision.
- Persist checkpoints after each validated microbatch and stage; validate payload
  and order hashes before reuse. Atomic per-file replacement is not cross-file
  commit. Current identity/memory mapping-related stores are per-file atomic;
  multi-file crash consistency is not certified. NFR-ALBUM-MAP-001 owns the target
  publication/recovery boundary; until then, inconsistent sidecars block mutation.
- AC-NFR-ALBUM-INGEST-003-01: Method: interrupt every microbatch/stage boundary and replay twice; fixture: ALBUM-FLOW-v1 and ALBUM-MAP-v1; comparator: identical logical outputs to baseline, one committed operation per idempotency key, zero stale-profile hits; evidence `evidence/AC-NFR-ALBUM-INGEST-003-01.json`.

### NFR-ALBUM-INGEST-004 — Per-action cost accounting
When an action is proposed or completed, the coordinator shall show an estimate and persist an actual cost receipt, including cancelled, failed and cached actions.

Scope: S: ingest, inference, review mutation, re-cluster, undo and export / E:* / T0–T4. Status: proposed.
- Receipt: action/job/batch IDs; stage and profile; item units/counts; cache hits;
  estimated and actual wall/CPU/GPU-active time where measurable; read/write bytes;
  derived retained/temporary bytes; peak host/VRAM boundary; external requests and
  currency charge. Unmeasured energy/GPU time is null with reason, not zero.
- Local inference has zero service charge, not zero compute/electricity cost.
  Optional electricity estimate requires explicit watt-hour measurement or labelled
  estimate and user rate. Cloud/export actions have separate quotes and ceilings;
  exceeding an approved charge ceiling pauses before further billed work.
- Totals distinguish inclusive parent wall time from child costs to avoid double
  counting; human waiting is separate. Same snapshot cached rerun reports zero
  fresh inference items but still counts validation I/O and publication.
- AC-NFR-ALBUM-INGEST-004-01: Method: deterministic metered-action replay; fixture: ALBUM-FLOW-v1; comparator: every action has estimate/outcome receipt, byte/item/charge totals equal meter within recorded meter resolution, unknowns remain null and charge ceiling never exceeded; evidence `evidence/AC-NFR-ALBUM-INGEST-004-01.json`.
