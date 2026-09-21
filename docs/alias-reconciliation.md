# Alias reconciliation — experimental execution receipt

Date: 2026-09-21. Specification: [FR-ALIAS-RECONCILIATION](../specs/features/FR-ALIAS-RECONCILIATION.md).

## What changed

`alias-candidates.json` enumerates reference-name/WD-tag pairs. Each bank exposes
unique-image denominators, co-occurrences, top-1 counts, ranks and score
min/P25/median/P75/max. Direct full-content matches and weak nearest-reference
cohorts are separate. Multiple crops count once per image (maximum score).
Missing/censored WD output is not a zero score. Tied nearest-reference leaders
do not enter a cohort. No proposal mutates memory or promotes a suggestion.

The offline studio's **别名核对** dialog supports confirm/reject, keyboard controls,
stable corpus/profile-scoped drafts and `alias-decisions.json` download. It clearly
distinguishes browser-pending decisions from memory-applied decisions. Downloads
must be applied locally; the browser cannot silently overwrite disk memory.
Only explicit browser decisions are exported, not untouched applied entries.

Memory v2 adds `Character.alias_decisions` with WD tag, decision, actor and timestamp.
V1 remains readable; existing curated aliases are preserved. Confirmation adds
the tag to the canonical namespace; rejection removes that alias and persists.
Rename preserves decisions/old names; merge/import reject conflicting decisions;
delete retracts the character's aliases and decisions. Export/import and label
synchronization preserve the records. Ambiguous alias ownership fails closed.

Canonicalization occurs before duplicate-crop reference conflict handling and
when comparing model/reference/memory/confirmed names. Unknown reference namespaces
report `reference-namespace-unresolved`, **not proven identity error**. Confirming
a compatible alias removes that namespace demotion, but does not set `verified`.
Other-character contradictions and the .85/.20 model gate remain conservative.

## Reproduced real-corpus results

Before was rerun through the pre-change producer, not copied from the supplied table.
After used saved evidence only; no model inference or image writes.

| Corpus | Rows | Before demoted / eligible | After demoted / eligible | Alias proposals | Banks |
|---|---:|---:|---:|---:|---:|
| pilot | 1207 | 1013 / 0 | 1013 / 0 | 21 | 4 |
| review | 3688 | 2885 / 0 | 2885 / 0 | 48 | 4 |
| similarity | 448 | 267 / 0 | 267 / 0 | 18 | 4 |

**Zero real aliases were confirmed. No real eligible improvement or precision is
claimed.** All real proposal pairs currently have **zero direct-reference WD image
overlap**; their support is explicitly weak retrieved-cohort co-occurrence. No
pair meets the relatively-strong direct-evidence heuristic. Obtaining WD evidence
for actual bank images remains a useful next step, not evidence fabricated here.
The review corpus still has **143** gate-passing `2b_(nier:automata)` proposals,
all demoted (similarity: 11; pilot: 0). Margin alone does not solve that confusable.

Input digests, counts and gallery hashes:
[corpus receipt](../specs/evidence/alias-reconciliation.json).
Each private output also contains `alias-reconciliation-report.json` and
`alias-candidates.json`; private screenshots remain under its `out/` directory.

## API and exact command for orchestrator wiring

No change was made to `src/artcurator/cli.py`. Proposed command, **not yet wired**:

```powershell
.venv\Scripts\python.exe -m artcurator.cli identity-alias --out <OUTPUT> --alias-op apply --alias-file <DOWNLOADED_ALIAS_DECISIONS_JSON>
.venv\Scripts\python.exe -m artcurator.cli identity-alias --out <OUTPUT> --alias-op propose
```

Route `apply` to `artcurator.character_memory.apply_alias_decisions(out, path)`
(owns the existing stage lock, validates the batch, saves memory and regenerates
candidates). Route `propose` to `artcurator.alias_candidates.emit_alias_candidates(out)`.
Then rebuild the studio with `python tools/build_gallery.py --out <OUTPUT>`.
Memory exchange remains `memory_curation.export_memory/import_memory`.
Atomic publication is per file, not a certified multi-file power-loss transaction.

Usable now without orchestrator wiring (run from project root; replace both paths):

```powershell
uv run --no-project --python .venv/Scripts/python.exe python -c "from pathlib import Path; from artcurator.character_memory import apply_alias_decisions; apply_alias_decisions(Path('out/OUTPUT'), Path('alias-decisions.json'))"
```

## Verification and limitations

- Root command: `uv run --no-project --python .venv/Scripts/python.exe -m pytest -q`:
  **320 passed**, one inherited sklearn FutureWarning. This includes 18 new alias
  tests; the checkout also contains parallel work, so no baseline test-count delta
  is inferred from the earlier 264-test receipt.
- Red phase: 8 failures/1 pass for missing alias API/sidecar; gallery embedding
  test failed on missing sidecar key; duplicate-crop test failed on dropped aliased
  support. Green suite covers human-only activation, no-alias regression, rejection
  persistence, imports/exports, ownership conflicts, rename/merge/delete and lineage.
- Actual browser downloads were applied to deterministic disk-backed synthetic
  evidence: confirm -> eligible/unverified; reject -> demoted/persisted.
  [Browser-to-API receipt](../specs/evidence/alias-browser-apply.json).
- Synthetic and all three real dialogs checked at **1280 / 768 / 375 × 900**:
  no horizontal dialog overflow, zero final console errors and external requests.
  Enter/Space/Tab/Escape, focus restore, reload persistence and export exercised.
  [UI evidence](../specs/evidence/alias-reconciliation-ui.json).
- Both changed JS modules pass `node --check`; all four gallery builds passed.
  New Python modules/helpers pass the programming no-excuse audit. LSP unavailable:
  basedpyright and TypeScript servers are not installed, previously declined.
  No clean LSP/type-check, Lighthouse, direct-file, screen-reader or recognition
  accuracy certification is claimed.
- Single responsibilities: proposal aggregation, review schemas, mutation service,
  and dialog are separate modules; parsed Pydantic boundaries and exhaustive human
  decision matching; no new untyped escapes, inference dependencies, logging,
  one-off abstraction layer or automatic identity confirmation.
- No commit, hidden-window launch, ingest change or protected-spec edit was made.

## Independent review and open items

Two read-only explore reviewers substituted for unavailable oracle agents. Both
corroborated the schema, token usage, offline construction and width arithmetic.
Neither could decode image attachments, so **independent visual/CJK approval is
unavailable** (not a pass). Primary executor inspected desktop/mobile captures;
Playwright produced all listed captures and runtime measurements. Review results:
design integrity **REVISE (minor)**; visual/CJK **REVISE (evidence unavailable)**.

- **Known minor keyboard limitation:** the modal isolates shortcuts with broad
  keydown suppression; browser find/reload/copy shortcuts are also suppressed
  while open. Tab/Enter/Space/Escape work; close the dialog for browser shortcuts.
  Narrowing this handler is follow-up work, not a claim of full keyboard-accessibility
  qualification.
- Stale drafts whose applied base state changed, or whose pair disappeared, are
  excluded fail-closed. There is currently no discarded-draft count notice.
- Screenshot provenance documentation is now in `docs/assets/README.md`; the
  reviewer requested CLI wiring, but that is explicitly outside this task's allowed
  files. The exact proposed command and immediately usable API call are above.
- Human review of the real proposed aliases, direct bank-image WD coverage and
  subsequent post-confirmation metrics remain open. No fabricated confirmations
  were used to make the real eligible counts improve.
