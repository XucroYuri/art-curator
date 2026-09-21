> 中文摘要
> 角色目录名称是用户提供的人工标签，不是待分组图片的视觉特征。
> 固定权重人脸锚点按余弦与竞争间隔分组，不确定时保留新人物分组。
> 导出角色到图片、图片到角色的多对多关系，不改评分、路由或原图。
> 重命名不变性、来源许可证及实测阈值证据是发布门禁。

# Feature: Reference-anchored character grouping

Status: implemented experimental (spec written before implementation). Owner: Art Curator maintainers.
Dependencies: INV-1/2/3/4, FR-IDENTITY-001/002, FR-CACHE-001, NFR-SPEC-001,
ADR-0004. Current code/schema: `identity_schema.py`, `identity_embed.py`,
`identity_labels.py`, `identity_store.py`; identity v2 has face vectors and unnamed
clusters but no folder-label retrieval or many-to-many character export.
Non-goals: training, semantic graduation, identity verification, changes to legacy
columns/tiers/routes, corpus moves, commercial clearance, frontend changes.

All records below scope S: anchor-centroid-v1 / E: certificate-matched CUDA FP32
batch 16, four threads / T2; implemented experiment, with scoped verification only
where linked evidence exists. Implementation: `src/artcurator/identity_anchor*.py`
and `identity_group*.py`; tests: `tests/test_identity_grouping*.py`; operating
method and observations: `docs/pipeline/identity-grouping.md`.
Synthetic fixture GROUP-SYN-v1 is constructed in `tests/test_identity_grouping.py`;
its source digest and test receipt are release evidence, not a pre-existing certificate.
Real observations use private snapshots aliased `out/library`, `out/review`,
`out/similarity`. Fixture digests are recorded at execution; missing digests block
qualification, not local experimental operation.

### FR-GROUP-001 — Construct labelled anchors
When the user invokes `identity-anchor --from-folders`, the system shall discover
immediate character directories under `characters_root`, interpret directory names
as human-supplied labels, and sample at most `identity.anchor_faces_per_character`
(default 64) single-face references per character without modifying source files.

Discovery excludes configured `identity.anchor_exclude_folders` (root-relative
directory names), configured input/output, and source directories represented in
existing sibling output manifests. Exclusions and empty character folders are
reported. Nested directories are data containers, never additional labels.
References are content-hash ordered, detection-filtered (default score >=0.7), and
greedily crop-pHash deduplicated at Hamming distance <=4 within a character.
Multi-face source images are skipped rather than attributing every face to a folder.
Source/crop full hashes, bbox, score, folder name, source type, counts, errors,
model/revision, preprocess, exact execution and license inventory accompany the
ordered matrix in `anchors.json` and `anchors.npy`. Matrix digest is verified.

- AC-FR-GROUP-001-01: GROUP-SYN-v1 tests cap/filter/dedup/exclusion, zero source
  writes and exact row association; evidence `evidence/AC-FR-GROUP-001-01.json`
  plus private `anchors.json`. Comparator: exact expected synthetic rows.

### FR-GROUP-002 — Pixel-only assignment and abstention
When `identity-group` processes an identity document, the system shall compare
every face vector with normalized character centroids and individual anchors,
assign only a unique winner meeting both configured similarity and margin gates,
and otherwise abstain to the existing `新人物NN` cluster label (outliers: `未知人物`).

The cosine winner comes from centroids. Reported margin is the minimum of centroid
winner-minus-runner-up and that same winner's maximum individual-anchor similarity
minus the strongest other character's individual similarity. Thus individual-anchor
disagreement vetoes unstable centroid decisions. A tie, no anchors, fewer than two
supported characters, or an excluded face abstains; no invented second-best score.
Exact query crop hashes are omitted from references for that query, including human
confirmations. Zero-norm/empty centroids are unavailable. Paths, filenames, folder
names of query images, cluster membership and labels never enter similarity math.

`identity.anchor_min_sim` and `identity.anchor_min_margin` accept explicit finite
overrides. When omitted, defaults are measured on reference-only leave-one-crop-out
distributions: min_sim = 95th percentile of strongest wrong-character centroid
cosines; min_margin = max(0.005, 10th percentile of positive stable margins).
No usable calibration causes fail-closed construction, not a guessed threshold.
This predeclared heuristic is not calibrated precision/recall; folder-label noise,
style dependence and near duplicates may bias it. Query distributions are reported
but never used to silently tune thresholds.

- AC-FR-GROUP-002-01: GROUP-SYN-v1 exact-boundary, low similarity, low margin,
  nearest-anchor disagreement, ties, self-reference and unknown tests; zero forced
  labels; evidence `evidence/AC-FR-GROUP-002-01.json` and private threshold receipt.

### FR-GROUP-003 — Frozen many-to-many export
When grouping completes, the system shall publish these additive version-1 outputs
without changing existing identity/score columns, tiers, routes or source images:

```text
character-groups.json:
{"version":1,"provenance":{...},"thresholds":{"min_sim":number,"min_margin":number},
 "characters":[{"character":string,"image_count":integer,"face_count":integer,
 "images":[sha16,...],"mean_sim":number|null,"min_margin":number|null}],
 "abstained":{"face_count":integer,"cluster_groups":[{"cluster_id":integer|null,
 "face_count":integer,"images":[sha16,...]}]}}
character-groups-by-image.csv: sha16,filename,characters
character-groups-by-character.csv: character,sha16,filename,face_id,sim,margin,decision
```

Image CSV contains every unique image, including zero-face images (empty roles).
Roles are sorted unique `|`-joined strings, including fallback labels. Character
JSON entries represent known characters, including zero-count anchors; image counts
are unique, face counts count decisions. Face CSV includes abstentions explicitly.
Abstained JSON retains nullable cluster IDs. Provenance additionally records zero-face,
unassigned-image, multi-known-character-image and any-abstained-image counts, input
digests, reference version, algorithm and execution. Short hashes remain existing
frontend indexes; provenance binds authoritative full hashes.
`identity-groups-report.md` is Chinese: counts, abstention rate, multi-character
counts, distributions/threshold rationale, wall time, provenance/licenses and limits.

- AC-FR-GROUP-003-01: GROUP-SYN-v1 round-trip JSON/CSV and CLI tests; exact keys,
  many-to-many counts, deduplicated images and unchanged legacy bytes; evidence
  `evidence/AC-FR-GROUP-003-01.json` and the four private outputs.

### FR-GROUP-004 — Human-confirmed retrieval state
When `identity-apply --labels` has accepted confirmations, subsequent grouping shall
merge current content-bound confirmed faces with folder anchors, distinguish their
provenance, discard stale/retracted confirmations on rebuild, and keep weights fixed.

Only replay-validated registry references are accepted, never suggested cluster
names. Exact duplicate crop+label references do not increase weight; conflicting
labels for a crop are excluded from automatic retrieval. Group provenance binds
the registry and effective anchor digest. Re-running group refreshes this merge.

- AC-FR-GROUP-004-01: GROUP-SYN-v1 confirmation/replay/rejection/conflict tests;
  exact source membership, no unconfirmed anchors; evidence
  `evidence/AC-FR-GROUP-004-01.json` and private effective-reference provenance.

### NFR-GROUP-001 — INV-2 visual-input invariance
When a query image is renamed or moved while its rendered pixels and reference
snapshot stay unchanged, the system shall emit the same character decision.

INV-2 argument: folder labels are **user-organized folders treated as human labels**,
equivalent to a human naming a face. Selecting a labelled reference dataset does
not authorize inspecting the query's own path as a classification feature. The
decision function accepts vectors and reference crop identities only; query paths
are display/lookup data. The mandatory test moves a synthetic image into a misleading
character-named directory, decodes/crops it again and compares decisions and scores.

This record covers the unchanged **context-free** component, so relocation invariance
still holds exactly as before. The ADR-0005 context-assisted grouping layer is
separate, approved but not implemented, and does not alter this behavior. That layer
may let only explicit folder/session membership act as a measured, consent-bound weak
prior in its own versioned proposal; it never becomes a model feature and never
changes these vectors, raw scores or context-free decisions, and visual contradiction
always vetoes it. Nothing here authorizes query path, folder or session membership in
the pixel-only grouping math above.

- AC-NFR-GROUP-001-01: GROUP-SYN-v1 rename/move paired visual test, exact crop bytes
  and decisions, equal similarity/margin; evidence
  `evidence/AC-NFR-GROUP-001-01.json`. Gate: zero assignment changes.

### NFR-GROUP-002 — Evidence, integrity and licensing
When publishing grouping results, the system shall verify matrix/order/profile
binding, record stage wall times and source rights separately from model rights,
and label semantic accuracy and unresolved image rights unverified.

Anchor labels are user supplied; private source image rights are unknown unless
the user supplies clearance. No private images/anchors are redistributed. Detector
MIT and SigLIP Apache-2.0 card declarations do not clear source-image rights or the
legacy quality stack. Numerical certificate admission is not semantic certification.
Mismatch, nonfinite vectors, corrupt arrays and unknown versions fail closed.

- AC-NFR-GROUP-002-01: GROUP-SYN-v1 corruption/profile tests, full pytest regression,
  build and privacy audit; evidence `evidence/AC-NFR-GROUP-002-01.json`.
- AC-NFR-GROUP-002-02: execute all three private snapshots; record anchor/group wall
  times, counts and conditional candidate breakdown; evidence private
  `identity-grouping-run.json`. No speedup claim from a single run.

## Design and release

Affected gates: NFR-GATE-001/002/003/006/007/008/009. Reuse admitted embedding
execution unchanged; new semantics are experimental. Tests establish local behavior,
not global rendering, resource-pressure, crash-atomic multi-file publication or
held-out recognition qualification. No move engine change: NFR-GATE-005 not triggered.
Rollback removes additive exports only; the original identity pipeline remains usable.
Requalification is required for changed weights, rendering, runtime, reference
snapshot or thresholds. Concurrent writers to one output remain prohibited.
Adversarial cases: wrong folder labels, multi-face references, duplicate/cross-label
crops, zero-face images, missing characters, identical centroids, misleading query
names, profile mismatch and tampered matrices. No accuracy claim without independently
labelled held-out confusables. This feature inherits NFR-SPEC-001 and INV-4.
