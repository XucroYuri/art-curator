# G6 — optional reversible physical export

Authority: **FR-ALBUM-MAP-007**, MAP-003 and **INV-M**. This backend/CLI export
does not change mapping rows, relations, dispositions, locators, reference support
or mapping history. Logical ARCHIVE and mapping undo remain filesystem-read-only.
Physical undo is a different command. This is not backup or power-loss certification.

## Frozen plan and selection

`derive(AlbumStore, ArchiveRequest)` reads one committed snapshot and the selected
files. It does not mkdir, save a plan, acquire another filesystem lock, or publish
mapping changes. A preparation without a committed revision cannot authorize export.
The CLI follows the existing store admission/reconciliation convention; its synthetic
before/after test includes database files. It does not certify zero transient SQLite
sidecar activity on every SQLite/filesystem combination.

`ArchiveRequest` (`album-archive-request-v1`) contains absolute `source_root`,
`export_root`, a separate `ledger_root`, optional `selections`, and `transfer`.
The ledger root must not contain, or be inside, either data root. Roots and locators
reject symlinks/junctions/traversal. Each run gets its own ledger directory.

Default selection includes only uniquely eligible relations on explicitly verified
human-resolved rows/subjects. `assigned`, `original-design`, `ordinary` and
`non-character` may qualify; `hypothesis`, `deferred`, `unknown-foreign`, `pending`,
inherited and unverified decisions do not qualify by default. No disposition or
verification is promoted by exporting. Excluded occurrence IDs and reasons are shown.

For explicit selection, each entry is
`{image_id, occurrence_id, relation_id, reviewed_inclusion:false}`. Exactly one
relation/destination per occurrence is allowed. Multiple memberships never choose
the first character. Select the intended relation explicitly, or leave the occurrence
excluded. `reviewed_inclusion:true` separately acknowledges an uncertain row; it does
not turn that row into a verified mapping. Copy-to-every-membership is not supported.

Layout is `<export_root>/<typed namespace>/<opaque entity_id>/<original basename>`:

| Type | Namespace |
|---|---|
| work | `IP/作品` (two path components) |
| artist | `画师` |
| original-series | `原创系列` |
| character | `角色` |
| ordinary-person | `普通人` |
| undetermined | `未定` |

The stable entity ID, not an inferred name, is the folder key. IDs containing path
separators or Windows-forbidden filename characters are refused, not silently
sanitized. A future display-name/encoded-ID layout requires a new reviewed policy.

`ArchivePlan` includes the full request, selected occurrence/relation bindings,
source and destination paths, full SHA-256, size/mtime/device/inode observations,
mapping library/revision/root digest, complete snapshot digest, exclusions, per-target
counts, every conflict-class count including zeros, required copy bytes and `digest`.
Ordering and digest are deterministic for the same snapshot, paths and observations.
The token is **`EXPORT-<full plan digest>`**. It is an explicit confirmation phrase,
not a password or proof that a person really inspected the plan.

## Conflict rules and measured synthetic counts

Counts below are separate two-file scenarios, **not added together as a library
survey**. Conflict classes overlap. The clean fixture has target
`角色/fixture-character = 2`, ready=2, excluded=0 and zero conflicts.

| Class | Synthetic count | Rule |
|---|---:|---|
| `already_correct` | 1 in the one-file no-op fixture | Same source/destination: leave it alone; still check its content. |
| `name_collision` | 1 with an existing same-byte target | Block; even identical content never grants authority to remove either occurrence. Planned duplicate destinations/sources also block. |
| `different_target` | 1; also name_collision=1 | Existing different file/directory: block, never overwrite or add a suffix. |
| `missing` | 1 | Missing/non-file original: block; keep the mapping decision. |
| `unreadable` | 1 | Read/hash failure or read-only source: block. Both injected sharing failure and actual Windows byte-range lock are tested. |
| `path_length` | 2 | Source/target at least 260 UTF-16 code units: conservative Windows limit, block. |
| `case_hazard` | 1 existing alias; 2 planned folder aliases | Compare actual and planned spellings case-insensitively, including directory components; block. |
| `cross_volume` | 2 under injected volume mismatch | Report and block in v1; no implicit cross-volume copy or rename fallback. |
| `capacity` | 2 under injected zero free space | Block if reported free target-volume bytes cannot hold all ready copies. No reservation or guaranteed future capacity. |
| `changed_source` | Covered by changed-source admission test | Hash disagrees with mapping: block. Execute also rejects changed size/mtime/inode. |
| `unsafe_path` | Additional conservative guard | Reject links/junctions/reserved Windows path components; structural root escapes refuse the request. |

All blocking conflicts abort the entire admission. No "skip the bad files and move
the rest" behavior is hidden in execute. Fix the source issue or explicitly narrow
the selection, then derive and confirm a new plan.

## Execution and recovery

Execution requires the exact submitted plan, `--album-authorize <digest>` **and**
`--archive-token EXPORT-<digest>`. It checks digest, current mapping/snapshot,
every untouched source, targets and conflicts before creating run artifacts. It
compares a fresh observation with the submitted plan, but never substitutes another
plan. A stale confirmation is refused. Empty/all-no-op plans write no run artifacts.

Default `transfer="copy-verify"` reuses `_moves.verified_copy`:

1. Durable hash-framed copy-intent record.
2. Exclusive destination creation, copy, flush/fsync, preserve file stat metadata.
3. Verify source and destination SHA-256; recheck original size/mtime/inode.
4. Durable `Entry(status="done")` with destination inode/mtime/size observation.
5. Recheck both contents, then unlink only the verified redundant source.

This is **no deletion as a classification action**, not literally no `unlink`.
Partial copies are retained, never cleaned up automatically. Post-copy failures are
interrupted/partial runs, not byte-identical aborts. At least one original-content
copy remains at every tested copy/verify/ledger/unlink cutpoint.

Optional `transfer="rename"` uses Windows `os.rename` only on the same volume.
It never uses `os.replace`. Windows refuses an existing target. An fsynced intent
precedes rename; source and target hash/inode/mtime checks bind recovery. A crash
after rename but before acknowledgement can be recovered only when the destination
has the recorded source identity and the source is absent. Non-Windows rename is
refused before run writes. Copy/verify remains the portable, conservative default.

Artifacts: `archive_plan.json` and `disposition_log.jsonl`, under the independently
selected ledger root. The adapter reuses `_moves.Entry`, `Move`, `Plan`, `batch_lock`
and `journal.Record/publish`: sequence, operation_id, run_id, plan_id, previous and
digest are retained. The archive reader validates archive lineage because the legacy
journal reader is bound to a character-score plan. No second mapping store or
unframed journal is introduced; the legacy SQLite move projection is not used.

Exact execution replay does not copy or rewrite acknowledged completed files.
After a durable done record but before source unlink, retry checks both sides and
finishes that unlink. Once inverse execution starts, use inverse recovery, not
forward replay. Rename intent with neither successful rename nor a done record,
and uncommitted copy intent, fail closed for review rather than guessing ownership.

## Whole-run physical undo

`archive-undo` reads the saved plan and ledger in reverse order and reuses
`undo.restore`: exclusive reverse copy, verify, then remove only the redundant
export copy. Mapping revision changes do not prevent physical undo.

Later source content or target content/mtime/inode replacements are preserved.
Every eligible item is attempted; conflicts return `partial_undo:true` and occurrence
IDs/reasons. A same-byte replacement target is still protected by inode/mtime.
Terminal `undone`/`already_undone` entries prevent repeated undo from touching later
human files, including ABA-like reuse. A lost inverse acknowledgement can resume from
both-present or source-only state. Failed/ambiguous uncommitted copies remain visible
as partial undo and need manual review; the tool never deletes them speculatively.

`archive-status --archive-ledger <run>` reports `outstanding` and `mapping_changed`.
Use it after mapping undo to see exports whose originating revision is no longer
current. There is **no library-global export registry or automatic UI notification**;
retain the ledger path for each run. Mapping undo and physical undo must stay distinct.

## CLI walkthrough (synthetic demo only)

Run from the project root. Start with an already committed **synthetic** database
and a request JSON whose source/export/ledger paths are inside your fixture temp
directory. Do not point this rehearsal at the real image library.

```powershell
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\demo.sqlite --album-op archive-plan --album-file request.json > preview.json
# archive-preview is an alias of archive-plan. Inspect items, exclusions and counts.
$plan = Get-Content -Raw preview.json | ConvertFrom-Json
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\demo.sqlite --album-op archive-execute --album-file preview.json --album-authorize $plan.digest --archive-token ("EXPORT-" + $plan.digest)
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\demo.sqlite --album-op archive-status --archive-ledger $plan.request.ledger_root
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\demo.sqlite --album-op archive-undo --archive-ledger $plan.request.ledger_root
# Mapping inverse is separate and does NOT restore physical files:
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\demo.sqlite --album-op undo --album-batch <mapping-batch-id>
```

Request/plan schemas are exposed by `ArchiveRequest.model_json_schema()` and
`ArchivePlan.model_json_schema()`. JSON stdout follows other album-map operations.
Preflight errors exit nonzero; an undo response must be inspected for `partial_undo`
even when its command successfully returned a structured response.

## Evidence and open gates

Receipt: [`AC-FR-ALBUM-MAP-007-01.json`](../../specs/evidence/AC-FR-ALBUM-MAP-007-01.json).
It records the exact full-suite result and conservative **partial** AC verdict.
Observed full suite from the project root: **668 passed, 0 failed, 1 pre-existing
sklearn warning, 228.05 seconds**. All 58 new archive cases passed. Compilation of
the six changed production modules passed; no clean LSP/type-check result is claimed.

* `test_album_archive.py`: deterministic read-only planning, digest/token refusal,
  unchanged virtual mapping, idempotent forward/inverse and later edits.
* `test_album_archive_conflicts.py`: exact requested hazard counts, actual Windows
  byte-range lock, stale hash/mtime/mapping/plan refusal and prepared-only rejection.
* `test_album_archive_policy.py`: six namespaces, eight dispositions, explicit
  multi-membership selection and no-op layout.
* `test_album_archive_recovery.py`: real copy/hash/ledger/unlink ordering, five forward
  fault seams, resumed forward/inverse operations and Windows rename recovery.
* `test_album_archive_adversarial.py`: planned folder case aliases, reverse-copy
  interruption, same-byte human replacement, torn/tampered ledger preservation.
* `test_album_archive_cli.py`: real subprocess plan/refusal/execute, mapping undo,
  outstanding-export status and separate physical undo.

Byte-identical proof compares the complete fixture file set and each file's
`(size, mtime_ns, SHA-256)` before/after refused or preflight-aborted execution.
Atime, directory mtimes, ACLs and alternate streams are not part of that proof.
Once actual copying begins, retained partial output intentionally changes the tree.

Remaining qualification: torn journal automatic repair; all physical OS/power-loss
cutpoints; hard process-kill coverage; source/target races with non-cooperating human
writers; corpus-wide exclusion across independent databases/output directories;
capacity reservations; cross-volume execution; global export registry/UI notices;
arbitrary unsafe entity-ID encoding; comprehensive ACL/alternate-stream preservation.
Existing `batch_lock` stale-lock handling requires proving the old process is gone
before manually removing `.disposition.lock`. Never do that during an active run.
No WAL-level, power-loss, backup, security-sandbox or production graduation claim is made.
LSP type-check evidence is unavailable because basedpyright installation was declined.
