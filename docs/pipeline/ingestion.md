# G1 ingestion orchestration (experimental)

Governing contract: `specs/features/FR-ALBUM-INGEST.md`. No normative requirement
or AC was changed. This implementation is **not certification of all seven ACs**.
It implements read-only G1 through PROPOSE, plus G2 mode negotiation (measured
report and explicit snapshot-bound consent; see [mode-negotiation.md](mode-negotiation.md)).
FIRST-PASS, REVIEW and ARCHIVE still raise explicit `NotImplementedError` guards
through `ingest-advance`; this is an orchestration boundary, not absence of the
delivered G2–G6 backend contracts. Explicit `album-map` operations expose mapping,
first-pass, review and archive contracts. No mapping or human decision is synthesized
by G1, and consent records authority only. Generated reports list capabilities from
the actual `ingest_cli.COMMANDS` and `album_map_cli.Operation` CLI contracts.

## Commands

Run from the repository root using the existing uv-created environment:

```powershell
# Independent local process; no browser/review surface has to remain open.
.venv\Scripts\python.exe -m artcurator.cli ingest --input C:\synthetic-images --corpus demo
.venv\Scripts\python.exe -m artcurator.cli ingest-status --corpus demo
.venv\Scripts\python.exe -m artcurator.cli ingest-pause --corpus demo
.venv\Scripts\python.exe -m artcurator.cli ingest-resume --corpus demo
.venv\Scripts\python.exe -m artcurator.cli ingest-cancel --corpus demo

# Foreground diagnostic, explicitly without model signals/downloads.
.venv\Scripts\python.exe -m artcurator.cli ingest-run --input C:\synthetic-images --corpus diagnostic --inventory-only

# Read a bounded sample directly from original locators, without staging copies.
.venv\Scripts\python.exe -m artcurator.cli ingest-run --input C:\synthetic-images --corpus direct-sample --inventory-only --sample 2000

# Reuse an explicitly selected incumbent profile/reference bundle, read-only.
.venv\Scripts\python.exe -m artcurator.cli ingest --config config.example.local.yaml --corpus demo --ingest-profile-from out\saved-profile --wd-provider CUDAExecutionProvider

# This prints the measured G2 report and parks at CONFIRM; it approves nothing.
.venv\Scripts\python.exe -m artcurator.cli ingest-advance --corpus demo --ingest-target CONFIRM
```

Run `ingest` again after a completed job to ingest a new delta. Use `ingest-resume`
for a frozen interrupted snapshot: newly added files wait for the next ingestion.
Resume revalidates access and full hashes. Changed bytes at a frozen member fail
closed rather than transferring decisions by filename. For changed-input recovery,
start a separately named corpus output; do not delete evidence to force continuation.

### Deterministic bounded selection

`--sample N` selects the first N image **occurrences**, ordered by case-sensitive
Unicode lexical comparison of POSIX-style relative paths, before source hashing or
decoding. It is a reproducible prefix, **not a statistically representative sample**.
Traversal lists candidate paths throughout the tree, but only selected file payloads
are read. Fewer than N candidates selects all; duplicates count toward N. No source
copy, move or write is involved. For `ingest`/`ingest-run`, `--limit N` is an alias;
specifying both, nonpositive values or selection flags on resume is a usage error.

`launch.json.options.sample` records the bound. Each sealed revision's
`snapshot.json.selected_paths` records exactly which relative paths were selected;
`occurrences` binds those paths to SHA256, size, mtime and status, and `job.json.root`
records the original root. `selected_paths` excludes historical removed/deselected
occurrences retained in the incremental ledger. Manifest absolute paths refer to
original sources, never a staged replica. Resume reuses the frozen selection and
revalidates its hashes, ignoring newly added files. A new invocation after completion
reselects the prefix, records additions/changes/removals from the selected set and
reuses unchanged content; a changed bound participates in profile identity.

### Decode reservation backpressure

The invariant is **0 <= reserved bytes = sum(active reservations) <= cap**.
The FIFO queue predicate, admission increment, release decrement and notifications
share one condition lock: there is no check-then-act gap. An individually admissible
request waits for release instead of becoming an image rejection. FIFO prevents
new small requests from starving an older large request. Reservations are not nested.
Only negative/individually over-cap estimates are refused; over-cap images remain
recorded per-item failures/deferrals, not a stage abort.

Backpressure is bounded by `ordered_map`: at most `workers` active/waiting tasks and
`2 * workers` submitted tasks, including results awaiting consumption. There is no
per-reservation timeout that rejects admissible work due to contention. Instead the
existing **24-hour whole-stage deadline** bounds a stalled stage; pause allows up to
**240 seconds** for in-flight work before process-tree termination. Both bounds are
typed options. A killed stage remains interrupted/failed, never a successful item
deferral. Inline library callers must supply their own supervision if they require
a wall-clock deadline. Admission caps and storage policy are unchanged.

`scan-rejected.json` retains inspect/thumbnail failures. `previews-rejected.json`
records deferred original paths and full hashes; `previews-timing.json.deferred`
records their count. Scan action reasons include scan-rejected and preview-deferred
counts, included in G1 report costs, with the rejection/timing artifacts in its
commit. All-oversized scan batches also continue to a partial proposal.

`--quota-gib` defaults to 8 and `--reserve-gib` to 1. `--ingest-folder-anchors` is
an explicit opt-in to the existing folder-labelled reference builder; it is not
permission to use folder names as inference features. Missing/uncertified models
or references yield unavailable signals or an explicit failed stage. Offline
flags are forced; model provisioning is a separate action. `--input` alone uses
default identity settings; an explicit nondefault `--config` supplies the other
settings and `--input` overrides just its input root.

## Ownership, state and artifacts

All job artifacts are local/gitignored under `out/ingest/<corpus>/`:

| Location | Contract |
|---|---|
| `launch.json` | Validated immutable settings/options for background resume |
| `owner.lock` | OS single-writer byte lock, released by process death |
| `job.json` | Atomic current state, orthogonal status/reason/resume_stage, heartbeat |
| `progress.json` | Small job-ID-bound live heartbeat; avoids rewriting the full artifact ledger every tick |
| `control.json` | Pause/resume/cancel request independent of the client |
| `runs/<job-id>.json` | Per-invocation costs, failure/cached outcomes and checkpoint |
| `commits/<operation-digest>.json` | Stage barrier with input/profile/member binding and full artifact hashes |
| `content/<full-sha256>.json` | Validated per-content scan result, including decode failures |
| `scan/<batch-digest>/` | Existing scan/thumbnail/preview outputs for delta microbatches |
| `revisions/<full-digest>/snapshot.json` | Frozen occurrence snapshot plus exact `selected_paths` |
| `revisions/<full-digest>/inventory.json` | Added/changed/removed occurrences; decoded/failed status |
| `revisions/<full-digest>/barrier-*.json` | IDLE, INGEST, ANALYZE and PROPOSE input/output barriers |
| `revisions/<full-digest>/analysis-report.{json,md}` | Partial-evidence report, representatives, folder counts, estimates |
| `revisions/<full-digest>/seal.json` | Full-hash artifact set; inconsistent sidecars block reuse |
| `admission.json` | Storage class caps, reservations and disclosed unqualified boundaries |
| `owner.log`, `stages.log`, `exchange/` | Independent process diagnostics and typed exchanges |

The owner refreshes its checkpoint heartbeat every 0.5 seconds. Pause stops further
scheduling, acknowledges `pausing` on that heartbeat, and lets the in-flight stage
settle. After 240 seconds (configurable in the typed options), it kills the stage
process tree and marks it failed/interrupted, never complete. A worker watches its
owner: owner death also stops the child and its WD subprocess. Whole-stage deadline
defaults to 24 hours; this is a safety bound, **not an ETA**. Status older than
60 seconds is shown as stalled. The OS lease prevents a second owner from writing
the same output. Two deliberately separate outputs are independent read-only jobs,
not authority to perform concurrent mapping mutations.

Progress units change explicitly from unique images to faces where known. Unknown
inventory size reports `discovered`, with no percentage or fabricated ETA. Stage
logs retain existing adapter microbatch output. Independent OS owner durability is
tested through launching-client exit; host shutdown/reboot does not auto-restart
work. Run resume explicitly after restarting. There is no hidden-window launch.

## Reused stages and cache boundaries

* `scan.scan(..., paths=delta)` is the same scan/decode/thumbnail implementation;
  the optional path list avoids rescanning old content. `previews.previews` creates
  the existing metadata-stripped previews on that microbatch's manifest.
* New revisions assemble a unique-content manifest plus a separate occurrence
  ledger. Existing outputs are never overwritten to bypass detection's snapshot guard.
* `identity_detect.detect`, `identity_embed.embed`, `identity_cluster.cluster`,
  `identity_anchor.create_anchors/load_anchors`, `identity_group.group`,
  `identity_tag.tag` and `identity_candidates_v2.emit` remain the algorithms.
* Sealed predecessor caches/crops are copied only after payload validation, never
  hardlinked. Their existing profile/handshake caches decide actual inference hits.
  Aggregate clustering/grouping/candidate publication recomputes for changed members;
  inference runs only on invalidated contents/crops. No-change replay validates
  source and sealed output hashes without scheduling stages or rewriting the snapshot.
* WD keeps its existing persistent worker, versioned handshake, 240-second request
  deadline and microbatch cache publication. G1 does not implement a second tagger.
* A saved profile supplies incumbent SigLIP metadata and compatible anchors. The
  existing local-only SigLIP lookup now also checks the shared top-level `out/`
  cache, because ingestion snapshots are nested deeper than legacy outputs.
* Windows full-hash cache nesting uses extended paths. A shared read-only SQLite
  URI helper strips the Win32 prefix before URI serialization; it does not grant writes.

## Evidence and honest limits

`tests/fixtures/album-flow.json` is the deterministic synthetic corpus recipe:
two differently shaped RGB rectangles plus an identical copy. Tests instantiate
it in isolated temporary directories; no real library paths/pixels are committed.
`tests/test_ingest*.py` cover G1 transitions, explicit future guards, replay, eight
stage cutpoints, incremental add/copy/rename/change/delete, metadata-spoofed content
changes, frozen snapshots, corruption refusal, source-write interception, cancellation,
single-writer ownership, client exit and actual subprocess deadlines.

The inference integration test uses real detection/embedding/cache/cluster/candidate
modules with tiny deterministic inference functions. It is evidence of orchestration
and cache reuse, **not real-model quality or GPU throughput**. The baseline repository's
WD protocol tests remain the worker/handshake evidence; G1 does not recertify the GPU.

Generate scoped AC receipts with:

```powershell
.venv\Scripts\python.exe tools\ingest_evidence.py
.venv\Scripts\python.exe -m pytest -q
```

The generator prints the local evidence bundle location. Its first/warm/incremental
walls measure the synthetic, inventory-only boundary. Historical WD rates are
**0.13–0.22 s/image on RTX 5060 Ti**; the **26,876-image first pass at roughly 2–3 h
is an estimate, not a guarantee**. Face counts, model loads, profile/cache misses,
quadratic grouping and contention matter. No ten-run randomized GPU/full-library
qualification or p95/host/board peak claim is made.

**Explicit remaining gaps:**

1. **Cross-file crash-atomicity is unverified.** Atomic individual JSON replacements
   and an OS owner lock are not a transaction across registry/memory/manifest/report.
   Inconsistent sealed sidecars fail closed; no mapping mutations are performed.
2. Storage admission counts retained revisions/caches, checks quota/free reserve and
   pre-reserves scan assets. It is **not hard per-write quota enforcement** for every
   native/third-party writer, log, temporary or unknown face/matrix allocation.
   NFR-ALBUM-INGEST-002 is therefore only partially covered, not certified.
3. Costs record action wall time, coordinator CPU, source-payload bytes scheduled
   and net output growth. These are **not OS physical I/O or subprocess CPU meters**.
   GPU-active time, energy, transient/host/VRAM peaks and unavailable stage estimates
   stay null. Local service charges/requests are zero, not local compute costs.
4. The Python source-write audit hook is not a native-code or hostile concurrent
   filesystem sandbox. Full hashes detect source mutation before evidence use.
5. Missing evidence is a partial proposal requiring manual review. Folder purity,
   coherence and consent are measured/recorded by G2; mapping publication and batch
   undo belong to G4–G6.

These gaps are disclosed in reports/receipts rather than weakening any FR/NFR/AC
text. In particular, a completed G1 job is not a claim that all ingestion ACs pass.

## Open storage finding: retained inventory then analysis

The 2026-09-22 real-library rehearsal measured **625,289,585 derived bytes** for
2,000 images. Its full-library inventory projection is **8,383,257,466 bytes
(7.81 GiB)** against the unchanged **8,589,934,592-byte (8 GiB)** budget.
Sample revision thumbnails/previews alone occupy **301,558,139 bytes**.
Enabling analysis changes the profile/revision (`ingest_profile.profile_digest`),
and revision assembly copies those assets again (`ingest_catalog.assemble`).
Retaining inventory and adding analysis therefore projects at least
**12,426,247,436 bytes (11.57 GiB)**, before inference outputs and extra metadata.

This is an open amplification finding, **not fixed here**. A follow-up decision must
choose retention/asset-sharing or a different operational workflow before that
two-step full-library run. Neither the quota nor retention policy has been changed.
This lower bound does not prove a fresh inference-first run exceeds 8 GiB. The
folder-balanced sample's extrapolation uncertainty is unquantified; source staging
bytes, allocator overhead, transient writes and inference outputs are excluded.
Evidence remains unchanged in `out/real-library-20260922/REPORT.md` and
`budget-stop.json`; no acceptance receipt was rewritten.
