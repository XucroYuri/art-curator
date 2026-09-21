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

## Reference-side WD evidence (corrected data flow)

The direct join is keyed by the **full source-image SHA-256** on both sides. Query faces
already carried that digest through `identity-provenance.json`; folder reference anchors
did not, so the two sides were disjoint and every real pair had weak retrieved-cohort
evidence only. That root cause is fixed on the reference side:

- The anchor build persists every accepted reference crop byte-identically at
  `out/anchors/<crop_sha256>.jpg`. `persist_crops` verifies the content digest before
  writing anything, so a partial failure writes no file.
- `identity-tag` tags those crops through the **same worker, handshake, provider and
  cache** as query faces. `wd-tagger.json` gains an additive `anchors` list binding
  `(image_sha256, crop_sha256, evidence)`; old files without the key still parse
  (`anchors` defaults to empty).
- The alias producer merges anchor observations into the **direct pool by
  `image_sha256`** and fails closed if a tagged pair is absent from `anchors.json`.
  Retrieved-cohort rows stay in their own field and never receive anchor rows.
- Missing, stale or corrupt crops are omitted rather than raising, which degrades to
  the previous weak-only behavior. No digest or threshold was weakened.
- Corpora anchored before this change were backfilled with
  `tools/backfill_anchor_crops.py`: it finds each source by its recorded full digest,
  re-crops the saved bbox, verifies `crop_sha256` and only then writes the file.
  All three corpora reproduced **145/145** crops with zero unavailable sources.

## Reproduced real-corpus results

Before was rerun through the pre-change producer, not copied from the supplied table.
After used saved evidence only; no human decisions, no threshold changes.

| Corpus | Rows | Before demoted / eligible | After demoted / eligible | Alias proposals | Banks |
|---|---:|---:|---:|---:|---:|
| pilot | 1207 | 1013 / 0 | 1013 / 0 | 25 | 4 |
| review | 3688 | 2885 / 0 | 2885 / 0 | 51 | 4 |
| similarity | 448 | 267 / 0 | 267 / 0 | 22 | 4 |

Reference-side WD coverage and direct support (identical reference side in all three
corpora; `wd-tagger.json` digests differ per corpus):

| Reference bank | Reference images | Tagged by WD | Direct WD tags (direct images) | Strength |
|---|---:|---:|---|---|
| Tifa Lockhart | 64 | 63 | `tifa_lockhart` (63) | relatively-strong |
| Aerith Gainsborough | 42 | 40 | `aerith_gainsborough` (39); `keqing_(genshin_impact)` (1) | relatively-strong; weak |
| Yuffie Kisaragi | 19 | 9 | `yuffie_kisaragi` (8); `mikasa_ackerman` (1) | weak; weak |
| Jessie Rasberry | 20 | 0 | none | cohort-only |

| Corpus | Reference images | Tagged reference images | Direct-supported pairs | Relatively-strong pairs |
|---|---:|---:|---:|---:|
| pilot | 145 | 112 | 5 | 2 |
| review | 145 | 112 | 5 | 2 |
| similarity | 145 | 112 | 5 | 2 |

**Weak -> direct moves:** two pairs moved from cohort-only weak support to
relatively-strong direct support (`tifa_lockhart` median .9956; `aerith_gainsborough`
median .9915, 39/40 tagged images). Three direct pairs stay weak: `yuffie_kisaragi`
(8 images, median .843 below the .85 median gate) and the single-image model mis-tags
`mikasa_ackerman` / `keqing_(genshin_impact)`. Every other pair remains weak
retrieved-cohort evidence. Candidate totals rose 21/48/18 -> 25/51/22 only because the
new direct tags add pairs the cohort never surfaced.

**Honest verdict:** WD does emit usable character evidence for reference crops —
**112/145 (77%)** carried at least one character tag above the .35 worker threshold —
so direct support is now real, not structurally empty. It is uneven: Jessie Rasberry
has **no** tagged reference crop, and two crops carry a different character's tag.
The alias path for Jessie (and for pairs below the median gate) still needs human
judgement or a different reference-evidence source. **Zero real aliases were
confirmed. No real eligible improvement or accuracy/precision is claimed**, and no
thresholds were tuned to manufacture support. All demoted/eligible counts are
unchanged from baseline. The review corpus still has **143** gate-passing
`2b_(nier:automata)` proposals, all demoted (similarity: 11; pilot: 0).

Cost of this regeneration (CUDA provider): backfill hashed 1,145 source files per
corpus (~80 s total); `identity-tag` processed 1,494 / 3,836 / 597 unique crops in
206.6 / 502.4 / 73.8 s wall; `tools/alias_receipt.py` regenerated both candidate
sidecars, all three galleries and the receipts in 47.6 s.

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

Reference-side evidence for a new or legacy corpus (crops persist automatically when
`identity-anchor` runs; the backfill is only for corpora anchored before this change):

```powershell
.venv\Scripts\python.exe tools\backfill_anchor_crops.py config.yaml out\<OUTPUT>
.venv\Scripts\python.exe -m artcurator.cli identity-tag --out out\<OUTPUT> --wd-provider CUDAExecutionProvider --wd-cuda-dlls .venv-identity/Lib/site-packages/torch/lib
```

## Verification and limitations

- Root command: `uv run --no-project --python .venv/Scripts/python.exe -m pytest -q`:
  **433 passed, 1 failed, 2 warnings**. The failure is
  `tests/test_ingest_process.py::test_background_when_client_exits_owner_finishes` in
  uncommitted parallel ingest work (Windows GBK subprocess decode) and is outside this
  change's scope; the checkout contains parallel work, so no baseline test-count delta
  is inferred from the earlier 320-test receipt.
- Reference-crop red phase: the new tests failed collection/assertions on missing
  `TaggedAnchor`, `TagDocument.anchors`, `persist_crops`, `restore_crops` and
  `verified_anchor_crops`. Green suite now covers old-`wd-tagger.json` parsing,
  anchor observations entering the direct join, full-digest binding failing closed
  on crop-only resemblance, degradation to weak-only for missing/corrupt crops, and
  digest-verified crop persistence/restore (9 new tests).
- Existing red/green coverage retained: human-only activation, no-alias regression,
  rejection persistence, imports/exports, ownership conflicts, rename/merge/delete
  and lineage.
- Actual browser downloads were applied to deterministic disk-backed synthetic
  evidence: confirm -> eligible/unverified; reject -> demoted/persisted.
  [Browser-to-API receipt](../specs/evidence/alias-browser-apply.json).
- Synthetic and all three real dialogs checked at **1280 / 768 / 375 × 900**:
  no horizontal dialog overflow, zero final console errors and external requests.
  Enter/Space/Tab/Escape, focus restore, reload persistence and export exercised.
  [UI evidence](../specs/evidence/alias-reconciliation-ui.json).
- Both changed JS modules pass `node --check`; all four gallery builds passed.
  New Python modules/helpers pass the programming audit. LSP unavailable:
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
- Reference-crop WD coverage is now measured rather than structurally empty:
  112/145 crops carry a character tag and two pairs are relatively-strong. Still
  open: the Jessie Rasberry bank has **zero** tagged crops (cohort-only), the two
  single-image model mis-tags remain weak review items, and human review of the
  real proposed aliases and post-confirmation metrics is outstanding. No fabricated
  confirmations were used to make the real eligible counts improve.
