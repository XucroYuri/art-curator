# Model suggestions v2.1 — scoped execution receipt

Date: 2026-09-21. Status: experimental policy, not accuracy certification.
Requirements: FR-CANDIDATES-008/009 in
[the candidate specification](../specs/features/FR-IDENTITY-CANDIDATES.md).

## Policy and compatibility

`wd-score-margin-v1`: WD score **>= .85**, competing margin **>= .20**.
These are pre-rerun engineering thresholds, not thresholds fitted to human labels.
The score cutoff selects strong evidence rather than every >.35 enumeration; the
gap rejects close competitors. High scores can still be confidently wrong.
When no runner-up survives compact-output censoring, use .35 as its upper bound,
report a lower-bound margin and label it `≥` in the UI. Never substitute zero.

The additive JSON envelope is numeric version 2.1. `suggested_model.verified` is
always false. `suggested_verified` mirrors `suggested`; legacy `abstained` remains
visual-tier abstention. Existing permissive consumers can retain their old
behaviour. Strict old version-2 parsers need updating; the new parser reads v2.
Neither tier writes human labels or strengthens memory automatically.

## Private snapshot results

Logical corpus labels below correspond to the local pilot, review and similarity
outputs. Corpus paths and images are deliberately not published. Counts are faces,
except the explicitly named gallery rows. Proposals include demoted proposals.

| Snapshot | Gallery rows | Faces | Model proposals | % faces | Primary model | Demoted | Verified tier |
|---|---:|---:|---:|---:|---:|---:|---:|
| pilot | 1207 | 1349 | 1013 | 75.09% | 0 | 1013 | 0 |
| review | 3688 | 3701 | 2885 | 77.95% | 0 | 2885 | 0 |
| similarity | 448 | 452 | 267 | 59.07% | 0 | 267 | 0 |

**Important limitation: empty curated memory is not the same as no references.**
These snapshots still have folder-reference banks. All proposals were demoted
by reference-name disagreements, not by memory (memory entries remain zero).
Those human-readable reference labels and raw WD tags have no curated alias
mapping. Thus the totals include unresolved namespace differences, including
different spellings of the same intended character. They are **not counts of
proven misidentifications**. No aliases were fabricated from corpus names or
silently added to the user's memory. Consequently these particular galleries
expose proposals inside conflict details, but still have no primary suggestion.
To promote compatible proposals here requires explicit name/alias curation or a
separately specified namespace-reconciliation policy. A genuinely reference-free
startup is covered by the actual producer test and the synthetic UI state.

Reference contradictions use the strongest non-self visual cosine >.35. This is
a conservative demotion rule even below the full verification threshold, not a
new verification gate. Tied leaders containing the model are not contradictory;
tied leaders excluding it are recorded. Confirmed assignments also take priority.
References are checked against saved embedding profiles; no image inference reran.

### Confusable finding, not hidden

| Snapshot | `2b_(nier:automata)` proposals | Demoted | Primary |
|---|---:|---:|---:|
| pilot | 0 | 0 | 0 |
| review | **143** | 143 | 0 |
| similarity | 11 | 11 | 0 |

The supplied review observation remains 204 enumerated occurrences, 199 top-1,
146 with score >.85. **143 still pass the new score-and-margin gate.** The gap
filter therefore excludes only three of those 146 high-scoring occurrences; it
does not solve this domain-shift confusable. All 143 retain `verified: false`.
No ground-truth labels were manufactured; occurrence is not false-positive rate.

### Proposal distributions

Quantiles are NumPy linear quantiles over gate-passing proposals, including
demotions. They describe evidence scores, not confidence in correct identity.

| Snapshot / quantity | min | p25 | median | p75 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| pilot score | .850753 | .991651 | .995666 | .997217 | .998412 | .999422 |
| pilot margin | .250412 | .641510 | .645662 | .647216 | .648396 | .649422 |
| review score | .850568 | .988661 | .995405 | .997235 | .998384 | .999402 |
| review margin | .209015 | .638381 | .645364 | .647228 | .648384 | .649402 |
| similarity score | .858907 | .986039 | .993139 | .996175 | .998248 | .999562 |
| similarity margin | .213556 | .635742 | .643029 | .646175 | .648248 | .649562 |

Margin bases (bounded / observed): pilot **1002 / 11**, review **2818 / 67**,
similarity **264 / 3**. The apparent concentration around .65 is largely the
effect of subtracting the .35 censoring bound from saturated scores, **not** an
observed concentration of actual runner-up scores. Full precision, source counts
and input/output SHA-256 digests are in each private `identity-candidates-report.json`.

## UI and verification

Durable browser observations: [UI evidence receipt](../specs/evidence/model-suggestions-ui.json).
Two independent source reviews corroborated the tier implementation; their models
could not decode screenshots, so **independent visual sign-off is unavailable**.
The primary executor inspected captures directly; the source reviewers' missing
documentation findings were addressed by this receipt and the screenshot index.

- Amber `模型建议（未核实）` displays WD score and signed margin; `≥` marks a bound.
- Green `已核实建议` explicitly says reference/memory gates passed and still requires
  human confirmation. It is not an accuracy certificate.
- Demoted model advice is secondary native conflict details, not a primary badge.
  Both source sections, fixed buckets, new-role action and marks remain present.
- Browser exercised cold-start model visibility, verified+demoted fixture, real
  reference demotion on each corpus, `B` baseline mark, `U` undo, numeric selection.
- Fixture viewports: **1280, 768, 375 × 900**. Fixed the inherited inner minimum
  width that made desktop popovers scroll horizontally; final popover widths are
  client/scroll **343/343**, **343/343**, **323/323**. Vertical scroll is intentional.
- All four galleries: **0 external asset references**, **0 external requests**,
  **0 script-src tags**, **0 stylesheet links**; browser console errors **0**.
  UI code and data are inline. Existing local preview assets remain local; this
  is not a claim that original images have been embedded into the HTML.
- Browser MCP blocks `file://`; browser QA used loopback-only HTTP. Direct-file
  navigation was not requalified. No network service or CDN was added.
- Root command: `uv run --no-project --python .venv/Scripts/python.exe -m pytest -q`:
  **264 passed** (baseline 252; +12), one existing sklearn FutureWarning.
  Final CSS-only overflow repair was subsequently checked by fresh gallery builds
  and browser geometry/screenshots, not another full pytest run.
- Both changed JavaScript modules pass `node --check`; all four gallery builds pass.
  LSP diagnostics unavailable: basedpyright is not installed and installation was
  previously declined. No clean LSP result is claimed.
- Word-boundary private-subject-name scan: no matches in `src`, `tools`, `tests`,
  `specs` or `docs` at the source-audit step. New repository prose remains generic.
- No commits, hidden process windows, model reruns or image-corpus writes.

Repository screenshots (synthetic only):

- [Model tier, desktop](assets/v12-fixture-model.png)
- [Verified tier and demoted model](assets/v12-fixture-demotion.png)
- [768px](assets/v12-fixture-768.png)
- [375px](assets/v12-fixture-375.png)

Each private output contains `v12-model-demotion.png`; none is a repository asset.
No Lighthouse, broad accessibility, calibrated recognition or cross-device claim
is made by this scoped receipt.
