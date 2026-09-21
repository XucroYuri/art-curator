# Offline cluster-naming surface — execution record

## Scope and safety

The **簇命名** mode renders frozen G3 representatives and member bindings. It
previews and downloads drafts only. No browser fetch, companion endpoint, mapping
publication, reference deletion, source-file operation or commit was introduced.
Backend modules, `specs/**`, and the two frozen pipeline documents were not edited.
All new imagery and snapshots are synthetic, not a real corpus or live authority.

## Input and hook points

The optional `cluster-payload.json` next to `scores.csv` is a **presentation
wrapper**, `gallery-clusters-v1`; it is not a new backend wire version. It carries:

- `parent`, `profile`, `corpus_fingerprint`, `manifest`, `manifest_digest`;
- `clusters[]` with a display `label`, backend `ClusterSnapshot`, and backend `Wall`;
- `subjects` keyed by manifest legacy ID, retaining disposition/accepted relations;
- `entities[]` with stable ID, one of six namespace types, and display name;
- optional backend `discovery` and/or `pool` outputs;
- `assets` keyed by legacy ID, containing embedded local raster data URIs.

Representatives are consumed in backend order. The browser does not recluster,
sample representatives, invent missing vectors, or infer membership from names.
Missing assets have an explicit unavailable label; external URLs are not loaded.
Missing/unsupported payloads show an unavailable surface. Malformed wrapper input
fails the builder; incomplete member/entity bindings fail closed in the browser.
Production assembly of this wrapper is manual/local; no backend producer was added.

Hooks follow the negotiation implementation:

1. `build_payload`: adds `clusters`; `compact_payload`: adds `cl`.
2. `installClusters`: appends a native tab to `.mode-switch` and a labelled sibling
   `#clusters-view` to `#main-region`.
3. `setMode`: toggles panel visibility, selected state and the shared compact shell.
4. The studio global shortcut handler ignores both negotiation and cluster modes.
5. The JS injection tuple loads `gallery_clusters_wire.js`, then
   `gallery_clusters.js`; the builder also inlines `gallery_clusters.css`.
6. Shared safe DOM, details/evidence, download, card and focus primitives are reused.

## Operations and exported wire

Naming selects an existing entity or creates a stable-ID typed entity from
`work`, `artist`, `original-series`, `character`, `ordinary-person`, `undetermined`.
No members or export acknowledgement are preselected. The preview names exact
affected subjects. Sibling faces and future members receive no implied assignment.
Only authoritative CLI confirmation creates human/verified relations; a preview's
prospective fields are not committed evidence.

Split uses one partition selector per member: A, B, or automatic remainder.
This makes overlap impossible through the controls; the wire guard also rejects
overlap, empty partitions, unknown members and empty remainder. Outlier/exclusion
requires a nonempty proper subset and is labelled **visual membership only**, not
identity rejection, reference deletion or source-file deletion.

Merge selects another disjoint frozen parent and previews all accepted typed IDs.
Conflicts block export unless the curator explicitly chooses `defer`. That draft
retains all accepted relations and proposes deferred state for all merged subjects.
The existing frozen deferred subject is visibly labelled separately from proposed
deferral. Nothing performs entity merge or majority overwrite.

`name/split/merge/outlier/exclusion` export the documented `BrowserEnvelope`:
`album-mapping-decisions-v1`, exact parent/profile/manifest binding, actor and
fresh export ID, typed entities for naming, empty explicit operations, and an
Artifact containing exact UTF-8 journal bytes, SHA-256, byte length and hex payload.
The separate journal download contains those same bytes. The manifest download
is a separate CLI input. The existing legacy localStorage journal is not rewritten.

Use `album-map --album-db <db> --album-op stage --album-file cluster-envelope.json
--album-manifest cluster-manifest.json`. Save and inspect the returned StagedImport;
then separately invoke `album-map --album-db <db> --album-op confirm --album-file
<staged.json> --album-authorize <exact staged fingerprint>`. **Not executed here.**

Promotion is deliberately different: the frozen contract requires a
`DiscoveryDecision` via `--album-op promote`, not a fabricated journal action.
The UI exports `cluster-promotion.json` with the original discovery, actor, entity,
cluster ID and exact selected members. That command also only stages; confirmation
is separate. The displayed pool includes membership digest, profile, parameter
change flag, incompatible members, arithmetic comparison bound, missing vectors,
noise and lineage. A default ten-distinct-image gate counts selected full hashes,
not faces. Smaller sets remain manually nameable when supplied as frozen clusters.

## Executed verification

- Fixture generation and committed gallery regeneration succeeded.
- New UI/wire JavaScript passed Node syntax parsing and real Chrome execution.
- Actual browser downloads for naming, split, merge/defer, outlier, exclusion and
  promotion passed the real backend staging boundary in pytest, without publishing.
- Full suite: `uv run --no-sync python -m pytest -q --tb=short --durations=10
  --junitxml=docs/assets/clusters/pytest.xml`.
- **610 passed, zero failures, one warning, 202.39 seconds.** The warning is the
  existing sklearn HDBSCAN `copy` future-default warning. No second passing run.
- Browser QA: installed Chrome via Playwright; fixture-only loopback server.
  **Zero external requests and zero console/page errors.**

| Width | Document visible / scroll | Cluster region visible / scroll | Checked-element clipping |
|---|---|---|---|
| 520 | 520 / 520 | 505 / 505 | 0 |
| 900 | 900 / 900 | 885 / 885 | 0 |
| 1440 | 1440 / 1440 | 1425 / 1425 | 0 |

The 15px difference is the region's stable vertical scrollbar. Screenshots are
viewport captures at 1000px height, with targeted scroll positions, not full-page
captures. Element-overflow checks cover headings, paragraphs, labels, buttons,
definition lists, preformatted text, summaries and captions; they are not a proof
of every browser-native popup or every possible ancestor-clipping condition.

Keyboard-only walkthrough: Tab to mode row → End opens cluster mode → native
select arrows choose artist → type name → Space selects a member → Enter previews
→ Space acknowledges → Enter downloads. The focused export control had a visible
outline. Tab then exited the region without a trap. Escape and input-change
invalidation also passed. Structural/promotion flows were exercised through native
browser controls, but were not each repeated as full keyboard-only walkthroughs.

## Evidence inventory

Under [assets/clusters](assets/clusters/):

- `width-{520,900,1440}.png`: wall overviews.
- `editor-{520,900,1440}.png`: editor and full wrapping existing Chinese entity name.
- `keyboard-focus.png`, `deferred.png`, `merge-conflict.png`, `merge-deferred.png`.
- `promotion-9.png`, `promotion-10.png`, `split.png`, `outlier.png`, `exclusion.png`.
- `capability-unavailable.png`: disabled actions and boundary explanation.
- `qa-results.json`: measurements, network/error lists and walkthrough checks.
- `keyboard-envelope.json`, `{merge,split,outlier,exclusion}-envelope.json`,
  `promotion.json`, `manifest.json`: real downloads, schema/staging tested only.
- `pytest.xml`: complete passing JUnit result.

## Gaps and unverified claims

1. There is no single documented browser envelope for discovery promotion.
   The existing separate `promote` contract is followed; no backend/schema change.
2. Backend Wall/Discovery outputs lack a complete studio presentation bundle of
   local images, subject states and entities. The wrapper is explicit and synthetic
   fixture generation is supplied; automatic real-library assembly is not implemented.
3. Currentness, snapshot digests and accepted-state authority remain CLI checks.
   The offline page cannot observe external changes or turn download into a receipt.
4. Browser apply/undo, entity merge, reference-support rejection/retraction,
   re-embedding and measured pricing remain unavailable with visible explanations.
   G5 image-row undo granularity and all existing backend qualification gaps remain.
5. **Independent visual approval was not obtained.** Both read-only reviewers
   lacked image-input support. The executor opened the requested width/conflict/
   promotion/capability screenshots; this is self-review, not independent sign-off.
   The reviewers found no demonstrated functional contract defect. Their concern
   about discovery cluster ID differing from snapshot ID does not describe the
   current backend: `recluster` sets `cluster_id=snapshot.snapshot_id` explicitly.
6. LSP attempts were rejected with `LSP file path must be inside request cwd`,
   despite the supplied project paths. No clean LSP/type-check claim is made.
7. Direct `file://` QA was blocked by MCP policy. Loopback was tested instead.
   Screen-reader testing, Lighthouse, exhaustive keyboard-only structural flows,
   real-corpus application, and independent pixel approval remain unverified.
8. QA results are not cryptographically bound to source digests. Do not treat this
   evidence bundle as release certification or held-out identity qualification.

## Authored-code review

The new modules have separate responsibilities: wire construction, DOM surface,
synthetic fixture generation and browser evidence capture. Each is under 200 lines;
the existing large builder was changed only at the requested hooks, not refactored.
No framework, external font, network library, backend modification or logging
system was added. Untrusted visible strings use textContent; external image URLs
are rejected. CLI staging remains the authoritative schema/content check.
