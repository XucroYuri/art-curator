# Offline mode-negotiation surface — execution record

## Scope and safety

The studio's **整理方式** tab renders a frozen NegotiationReport and exports a
Decision JSON file. It never invokes ingest-confirm, writes a receipt, establishes
a mapping, performs undo, or changes model scores. No commit was made.

The frozen contract, frozen example, backend modules and `specs/**` were not edited.
All screenshot data is synthetic. The gallery fixture's analytic values are UI
test inputs, not measurements of model accuracy or a real corpus. Its Decision
downloads must not be used as authority against a real ingestion job.

## Inputs and integration

- Optional `negotiation-report.json` beside `scores.csv` is embedded verbatim.
  Missing input stays unavailable; malformed/unsupported input fails the build.
- Existing local raster representatives under the output directory are embedded
  as data URIs. External, outside-root and missing paths are not fetched. Imported
  reports with a different digest cannot reuse the previous report's thumbnails.
- The local file picker accepts a fresh report without a server endpoint.
- `tools/build_gallery.py:850`: optional report loader.
- `tools/build_gallery.py:867`: local representative embedding.
- `tools/build_gallery.py:884`: compatibility payload adds `negotiation` and
  `negotiation_assets`; compact payload keys `ng` / `na` at lines 1086–1087.
- `tools/gallery_negotiation.js`: appends the mode button to `.mode-switch` and
  the labelled panel to `#main-region`; no template copy is hardcoded in markup.
- `tools/build_gallery.py:1536`: `setMode` integrates panel visibility and ARIA.
- `tools/build_gallery.py:1645`: isolates the studio's global shortcuts.
- `tools/build_gallery.py:1673`: existing module-injection tuple loads report
  rendering, then negotiation controls. CSS is inlined by the same builder.

## Implemented behavior

Measured cluster and directory sections retain denominators, nullable evidence,
coherence methods/limits, sample basis, purity intervals, candidate provenance,
all four detector gates and their threshold outcomes. Additional evidence is
available through native details controls, including all remaining clusters.

The three modes and three scopes retain their recorded consequence tokens.
Folder checkboxes expose relation type and current-snapshot/direct-only policy.
Limitations precede an initially unchecked affirmative acknowledgement.
All nine exported combinations were parsed by the CLI's actual strict Decision
model in pytest. Every confirmation received a fresh operation ID.

Waiting, local dismissal, stale, exported-but-unsubmitted and invalid-report
states are explicit. Escape clears acknowledgement and does not export. It cannot
recall a file already downloaded. Stale export stays blocked until a different
report is loaded and reviewed. Mapping and reserved undo controls are disabled,
with visible explanations; even a future true mapping capability would not cause
this export-only client to execute it.

## Verification

Final command: `uv run --no-sync python -m pytest -q --tb=short --durations=10`

**503 passed, zero failures, one warning, 264.20 seconds.** The warning is sklearn's
existing HDBSCAN future default for `copy`. An earlier run hit the 240-second
terminal limit and exposed a duplicated dismissal-copy fragment. That fragment
was removed; the final complete run above passed. No backend fix was needed.

Fixture generation and gallery regeneration succeeded. Both injected negotiation
JS modules also passed Node syntax checks.

Playwright ran installed Chrome (`channel: chrome`, headless), using only a
loopback server restricted to `tests/fixtures/gallery`. The browser-tool transport
closed during its download test; running the same flow directly through the
installed Playwright package completed successfully.

| Viewport | Document visible / scroll | Negotiation region visible / scroll | Clipping findings |
|---|---|---|---|
| 520 | 520 / 520 | 505 / 505 | 0 |
| 900 | 900 / 900 | 885 / 885 | 0 |
| 1440 | 1440 / 1440 | 1425 / 1425 | 0 |

The region's stable scrollbar accounts for the 15px difference. Both dimensions
were measured; the internal scroll owner and element overflow checks supplement
the document check because the existing shell uses overflow containment.

Keyboard walkthrough: ArrowRight/End across mode tabs; Tab to radio groups;
native arrows select auto-first and selected scope; Space checks one folder;
arrows select work/direct-only; Tab/Space acknowledge; Enter downloads the exact
Decision. Visible focus was checked and captured. Escape gives non-consent and
disables export. Tab exits the last control to BODY without a focus trap.

The tested run recorded **zero external requests and zero console/page errors**.
Checks also covered same-stale-digest refusal, fresh-report acknowledgement reset,
old-asset isolation, frozen copy, unavailable/census distinction, hostile text
remaining inert data, and unbound copy failing closed.

## Evidence

All files are under [assets/negotiation](assets/negotiation/).

- `width-{520,900,1440}.png`: viewport overview / waiting.
- `choices-{520,900,1440}.png`: choice-column scroll positions (at narrower widths
  these frame the directory-choice portion, not the entire radio group).
- `regimes-{520,900,1440}.png`: expanded detector values and thresholds.
- `confirmation-{520,900,1440}.png`: acknowledgement, export and locked actions.
- `keyboard-focus.png`, `dismissed.png`, `stale.png`, `capability-disabled.png`.
- `exported.png`, `unavailable-evidence.png`, `invalid-report.png`.
- `qa-results.json`: machine results, request log, screenshot list, nine decisions.
- `decision-{human-first,auto-first,inherit-only}-{all,selected,none}.json` and
  `keyboard-decision.json`: actual browser downloads; schema validation only.

## Contract gaps and verification limits

1. Frozen contract line 40 says all four binding digests are echoed, but its
   Decision example and the strict backend model accept only report_digest,
   snapshot_digest and profile_digest. The exporter follows the exact accepted
   envelope; analysis_profile_digest and seal_digest remain displayed, not added
   as forbidden extra fields. No contract or backend patch was made.
2. The report has no live freshness feed or stale-state field. An offline page
   cannot detect external corpus mutations. Explicit invalidation/import clears
   local consent; the CLI remains authoritative for currentness and retraction.
3. The frozen prose says coherence `medium`; actual data uses `median`. The
   renderer uses the actual frozen data field without changing the contract.
4. Independent visual approval was **not obtained**. Two read-only reviewer
   agents could inspect source/evidence metadata but lacked image-input support.
   The executor opened screenshots; this is self-review, not independent sign-off.
5. LSP diagnostics could not run: TypeScript and basedpyright servers are not
   installed, with previous installation declines. No clean-LSP claim is made.
6. Direct `file://` browser QA was not completed (the MCP browser blocks it).
   Loopback offline behavior was exercised. Screen-reader testing, Lighthouse,
   real-corpus authorization/application and calibrated measurement are unverified.
