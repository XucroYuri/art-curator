# Transactional virtual album — G5 backend

**Status: partial implementation, not G5 graduation.** ADR-0006 is accepted by
the Art Curator maintainers, dated 2026-09-21. Architecture acceptance is not
power-loss, identity, UI, or performance certification. The entry audit is
[album-mapping-audit.md](album-mapping-audit.md). No UI or existing copy literal
was changed by this work.

## Authority and schema

`AlbumStore` owns one local SQLite connection, WAL, synchronous FULL, foreign
keys and an OS-held admission lock. SQLite 3.51.3+ or the explicitly enumerated
3.44.6/3.50.7 fixed backports are admitted. No weaker fallback is provided.
Existing stores open with `mode=rw`, never silently create a replacement.
Copied databases with a different canonical path are refused.

Migration **1**, checksum SHA-256 over newline-joined SQL statements in
`album_map_storage.MIGRATION_1`, creates:

| Table/index | Responsibility |
|---|---|
| migrations | Applied version and SQL checksum; `user_version=1` |
| binding | Library ID and canonical database path |
| root | Singleton committed library/revision/digest |
| artifacts | Digest-addressed original evidence bytes and descriptors |
| batches | Unique batch/operation IDs, request/manifest digests, state, unique inverse key |
| one_prepared | Partial unique index: only one unresolved prepared batch |
| commits | Unique revision/batch and execution receipt |
| events | Ordered changes, before/after images, digests and tokens |
| materialized | Current image/support rows, including tombstone tokens |

There is **no migration 2 or upgrade/backup runner yet**. SQL checksum checking
is implemented; backup-before-upgrade qualification is not.

`album-map-v1` includes all eight disposition literals and all six entity types,
full image hash, stable occurrence/subject/relation/entity identifiers, subject
crop/profile binding, many-to-many relations, source, typed decider, separate
nullable metrics, explicit verification members, timestamps, evidence references,
notes/hypotheses/flags, revisit state and logical archive. Nested relations cannot
claim a sibling subject. The convenience request builder stamps image-level
revision/parent and operation/batch IDs. Raw requests and nested decision metadata
are not yet fully causality-enforced; this remains a schema qualification gap.

## Publication, reconciliation and undo

1. Preview a `BatchRequest`. Affirmation echoes its canonical fingerprint.
2. P persists artifacts, before-images and the immutable prepared manifest.
   It does not change the committed root or live rows.
3. C compares the parent, writes marker/events/materializations, marks committed
   and compare-and-swaps the root, all inside one SQLite transaction.
4. Reconciliation validates the commit/root before acknowledgement. An identical
   request replays the original receipt, including after response loss/restart.
5. Reopen validates integrity/FKs, migration checksum, artifact bytes, batch
   manifests, complete root/event chain, and reconstructed versus live state.
   Prepared before-tokens/digests must match the reconstructed parent state.
   Prepared-only state requires explicit publish/resume or abort.

No recency heuristic, automatic rollback to an ancestor, WAL truncation or source
move is used. `test_old_or_complete_revision_when_cutpoint_raises` covers eleven
injected Python-exception cutpoints from before P through acknowledgement.
These are **exception rollback/reopen tests**, not process-kill, torn physical WAL,
I/O-short-write, Windows sharing-violation or actual power-loss tests.

Undo compares **both** the original after-image digest and current last-event
token. The ABA test deliberately keeps complete A/C after-images byte-equivalent,
so digest equality alone cannot pass it. It returns one persistent inverse, including
zero-change/all-conflict partial inverses. Disjoint image edits are preserved and
eligible images restored; repeat undo after restart returns the original receipt.

**Important limit:** undo granularity is currently one image row (plus independent
support rows), not independent nested subject/relation rows. A later edit to another
subject in the same image conservatively conflicts the whole image. Automatic
reference-support retraction/dependent-suggestion invalidation is not complete.

## Exchange and deferred tray

`export_bundle` returns `Export{bundle,digest}`. `bundle.schema_version` is
`album-map-export-v1`, and includes committed snapshot/history, prepared/aborted
batch manifests and all stored artifacts. `restore_bundle` requires an explicitly
initialized empty destination with the same library ID. One transaction restores
the logical history and validates replay/projection before commit. It does not
merge competing stores or guess locators. Request/receipt IDs, undo and opaque
optional **record** fields are round-trip tested. Envelope-level unknown extensions,
incremental cross-library import and complete backup retention remain unqualified.

`Manifest.resolve` requires a unique legacy-ID → full image/crop/profile/subject
association. Missing or ambiguous bindings fail closed. No adapter reads, moves,
renames or rewrites locator targets. CLI export emits JSON to stdout; it is **not**
the ADR's validated atomic-file-export/backup mechanism, which remains open.

`tray_request` creates previewable archive/reopen/defer/unknown-foreign/notify
requests. Archive retains deferred membership and notes. Repeated supplied trigger
revisions are deduplicated. Nested-subject state changes require explicit selection
and are refused by the image convenience API. Automatic clock/new-reference
trigger scheduling and tray age/reason/batch filtering are not implemented.

## Unknown-pool discovery

`preview_pool(snapshot, DiscoveryInput)` freezes unresolved subject/content IDs,
retains missing-vector IDs, binds profile/parameters and a membership digest,
and quotes an arithmetic pair-comparison upper bound (not measured time or cost).
Resolved ordinary/original-design/non-character rows are excluded by default.
`recluster` reuses `identity_cluster.cluster_vectors` and
`negotiation_clusters.representative_indices`; noise remains unresolved. Cluster
IDs bind selected member data, options and profile; prior snapshot IDs are retained
as supplied lineage. The default seed gate is ten distinct images.

`promotion` supports one eligible cluster, typed entity selection, an explicit
staged preview, one named reversible batch and no sibling-face attribution.
Multi-cluster selection, explicit small-set manual naming, automatic lineage
addition/split/merge analysis and full NEGOTIATE coherence qualification remain open.
The seed gate alone is not an identity/coherence qualification.

## Additive contract versions

| Boundary | New boundary | Old artifacts / limitation |
|---|---|---|
| Label envelope | `LabelEnvelopeV2`, version 2; `set_disposition` | `read_labels` dispatches on version; four v1 actions and optional marks retain the original reader. V1 reader still rejects v2. No v1 reinterpretation of ignore/wrong_box/new. |
| Registry | `RegistryV2`, version 2, read-only root/support projection | Original bytes stored in Artifact; original v1 `read_registry` chain/replay validator reused without rehashing/renumbering. Enrollment/writer fencing is incomplete. |
| Consent | `album-consent-v2` | Consent remains zero-mutation; frozen unversioned G2 reader/producers untouched. V2 authority lifecycle/executor integration is not qualified. |
| Execution | `album-mapping-execution-v1` | Count requires committed batch/revision/root/manifest and consent reference; it is never a G2 consent receipt. |
| Negotiation | `album-negotiation-v2` | Nonnegative nullable estimates, denominator/policy/preview/parent and missingness. V1 reports/fixture remain unchanged. No G4 counts invented. |
| Presentation | `album-presentation-v2` | Capability is deliberately still false while executor qualification is incomplete. No copy strings changed. |

V2 negotiation/consent are additive schemas, **not yet dual-version production
dispatchers**. No v2 writer is enabled in the existing client. Registry v1 still
uses the exact historical digest algorithm; new normalization never rewrites it.

## Browser-import wire contract (CLI/local companion, no HTTP server)

Implementation: `album_map_browser.py`; transport: `album_map_cli.py`.

1. Submit `BrowserEnvelope` with
   `schema_version="album-mapping-decisions-v1"`, `source="review-studio"`,
   `corpus_fingerprint`, `parent{library_id,revision,root_digest}`, `export_id`,
   `actor`, `profile`, `manifest_digest`, `original_journal:Artifact`, explicit
   typed `entities[]` and optional `operations[]`.
2. Artifact retains exact downloaded journal bytes as `payload_hex`, byte length
   and SHA-256. Journal `faceLabels` and `clusterDecisions` are parsed without
   claiming that current state is complete history. Undone cluster entries are
   inactive. Legacy face confirm/new require unambiguous explicit typed entity
   bindings; name commands require recorded selected `face_ids`. Unsupported
   split/merge/outlier/exclusion commands leave the whole import pending.
3. Supply `Manifest{schema_version:"album-member-manifest-v1",members:[...]}`.
   Each member binds `legacy_id,image_id,subject_id,crop_id,profile`. Resolution
   uses this frozen manifest, never display names/current cluster membership.
4. `stage_import(snapshot,envelope,manifest)` returns `StagedImport` with original
   envelope/manifest, complete before snapshot, proposed request, conflict IDs,
   zero source moves, and explicit incomplete-history status. It writes no mapping.
   Request changes contain exact per-image/subject after-state. Duplicate identical
   commands are collapsed. Its fingerprint is the confirmation token.
5. `confirm_import(store,staged,staged.fingerprint())` applies via P/C and returns
   `album-mapping-execution-v1`. The operation ID is `browser:` + envelope digest.
   Persist the exact staged artifact for retries: restaging currently uses new
   operational timestamps and is not an identical-request replay mechanism.
6. Only the returned matching receipt means applied. Browser must retain the
   exported original and refresh from the receipt's revision, never mark a local
   draft committed on download. Undo uses the receipt batch ID.

Supported explicit operations are `set_disposition` and `confirm_relation`, with
`members[]`, `scope=image|subject`, disposition, optional typed entity and notes.
`set_disposition=assigned` is refused: a relation command is required. Full-hash
confirmation is explicit at the preview boundary; no automatic reference support
is inserted. Draft provenance/corpus authenticity, exclusion/support cascades,
complete split/merge semantics, stale-consent/revocation gates and durable staging
reconstruction require further work. This transport is experimental, not an
enabled qualified server executor.

## CLI

Run from the project root with the existing interpreter:

```powershell
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\album.sqlite --album-op init --library-id local-library
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\album.sqlite --album-op snapshot
```

The destination parent must already exist. Existing files are not replaced by
init. Commands: `init`, `snapshot`, `prepare`, `publish`, `abort`, `undo`, `export`,
`restore`, `stage`, `confirm`, `tray`. JSON input uses `--album-file`; stage also
requires `--album-manifest`; publish/abort/undo require `--album-batch`.
`--album-authorize` is the exact request fingerprint for prepare, staged
fingerprint for confirm, or export digest for explicit empty-store restore.
Tray emits a request for separate prepare/confirm; it is not an implicit write.
Discovery is currently a Python API, not a CLI subcommand.

## Final requirement verdicts and remaining gate

| AC | Verdict | Evidence / remaining contract |
|---|---|---|
| MAP-001-01 | partial | Exchange/lineage/sibling binding regressions; full metric/verification/taxonomy matrix, typed view projections and nested causality incomplete. |
| MAP-002-01 | inconclusive | G4 first-pass adapter not implemented here. |
| MAP-003-01 | partial | ABA, partial/repeated/restarted inverse tests; nested-row undo and support cascades incomplete. |
| MAP-004-01 | partial | Browser stage/confirm/replay/undo test; split/merge and G3 walkthrough incomplete. |
| MAP-005-01 | partial | Ten-image analytic promotion/undo and missing-vector membership tests; richer selection/lineage/coherence incomplete. |
| MAP-006-01 | partial | Archive and duplicate supplied trigger tests; clock scheduling, full state-cycle/filter tests incomplete. |
| MAP-007-01 | inconclusive | G6 physical-export integration not implemented here. |
| NFR-MAP-001-01 | partial | Eleven exception cutpoints, locking, tamper and prepared-parent refusal; fault classes and enrollment below remain open. |
| INV-M-01 | inconclusive | Synthetic adapters perform no locator I/O; all-eight-stage write tracing not run. |
| VISION-003-01 | partial | Schema/v2 adapters exist with targeted tests; full six-type/eight-state matrix incomplete. |
| VISION-005-01 | partial | G5 explicitly not graduated; complete seven-gap release manifest not qualified. |

Additional ADR gaps: independent stores sharing one library ID are not globally
registered/fenced; only canonical-copy binding and same-path admission are enforced.
Legacy writable sidecars are not enrolled/fenced. Retained acknowledgement rollback
detection, divergent external projection quarantine, capacity/WAL budgets, coordinator
checkpoint policy, consistent backup/migration runner, quiesced incident sets and
durable external failure receipts remain open. Generic low-level `prepare` checks
evidence existence and affirmation, not the full v2 consent/revocation/capability
policy. Do not advertise this prototype as a production-qualified writable album.

Machine-readable scoped receipts and the observed full-suite summary are under
`specs/evidence/`; `album-mapping-run.json` records test-source digests, runtime,
file inventory and limitations. No performance or power-loss result is claimed.

### Observed verification — 2026-09-21

Full suite executed from the project root: **502 passed, 1 failed, 1 warning**
in 329.02 seconds (503 collected cases; all 32 `test_album_*` cases passed).
The failure is
`tests/test_gallery_negotiation.py::test_copy_when_embedded_is_data_not_module_literals`:
a frozen presentation string also appears inside the gallery negotiation modules.
Those files belong to the parallel visual task and were not modified here.
**The mandatory zero-failure gate is unmet.** AC receipts therefore record
`verdict=inconclusive`, separately retaining scoped implementation verdicts and
the names of passing regressions. Existing G2 receipts are not overwritten;
G5 supplements use `.g5.json`.

LSP diagnostics could not run: basedpyright is not installed and the existing
installation decline was respected. No clean type-check claim is made. Python
test execution is the available executable check, not a substitute for that gate.
