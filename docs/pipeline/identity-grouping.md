# Reference-anchored character grouping

This additive experiment groups a library by known characters supplied through
user-organized folders. Folder names are human labels, not query-image features.
It does not train weights, change identity-v2 clusters, alter scores/routes, or
move corpus files. Normative contract: [FR-IDENTITY-GROUPING](../../specs/features/FR-IDENTITY-GROUPING.md).

## Commands

Configure `characters_root` with one immediate directory per character. Explicitly
list non-character directories under `identity.anchor_exclude_folders`; nested
directories inherit the immediate character label. The configured input/output
and source directories in existing sibling output manifests are automatically
excluded. Review `anchors.json` exclusions before trusting labels.

```powershell
.venv-identity/Scripts/python.exe -m artcurator.cli identity-anchor --from-folders --config config.yaml --out out/library
.venv-identity/Scripts/python.exe -m artcurator.cli identity-group --config config.yaml --out out/library
.venv-identity/Scripts/python.exe -m artcurator.cli identity-apply --labels out/library/labels.json --out out/library
.venv-identity/Scripts/python.exe -m artcurator.cli identity-group --out out/library
```

Repeat for `out/review` and `out/similarity`. `tools/run_identity_grouping.py`
accepts these three outputs in order, preserves legacy hashes and writes private
`identity-grouping-run.json` receipts. It reuses existing anchors, otherwise builds
them; remove/replace derived anchors deliberately when changing source folders.
Do not run concurrent writers against the same output.

`identity-anchor` requires the exact installed numerical certificate, even when
CUDA was explicitly requested. It reads sources, accepts only single-face images,
filters detection confidence >=0.7 and crop-pHash distance >4, and samples at most
64 content-hash-ordered references per character. Fewer available references are
reported, not fabricated. Only crops in memory and vectors/provenance in output
are produced; originals are unchanged.

## Retrieval and thresholds

The query's normalized face vector is compared with each character centroid and
with each individual anchor. A named decision requires similarity >= min_sim,
centroid margin >= min_margin, and the same winner's individual-anchor margin
>= min_margin. Equal winners abstain. Exact matching crop identities are removed
from the query's reference set; fewer than two supported characters abstain.

Omitted/null `identity.anchor_min_sim` and `identity.anchor_min_margin` use the
predeclared reference-only leave-one-crop-out heuristic: strongest wrong-character
centroid P95; max(0.005, positive stable-margin P10). Explicit values override
these defaults and appear in exports. There is no query-yield tuning and no
precision/recall guarantee. Reference distributions and defaults live in
`anchors.json`; Chinese reports include their quantiles and limitations.

Current measured defaults: **0.9484045148 / 0.0068218708**, from 145 references:
64 蒂法, 42 爱丽丝, 20 杰西 and 19 尤菲. Reference source rights remain unknown;
these labels are user-supplied, not independently verified ground truth.
Detector MIT and SigLIP Apache-2.0 card declarations do not clear image rights.

Current confirmations from `identity-apply` are replay-validated and merged at
every grouping invocation, not copied from suggested cluster names. Effective
sources, event IDs and source types are saved in `identity-group-references.json`.
Duplicate crop labels have one vote; conflicting crop labels are excluded.
Retraction is reflected on the next grouping invocation. The folder anchor files
remain the reproducible base; the effective-reference receipt identifies the merge.

## Frozen outputs

- `character-groups.json`: version 1; known roles → unique image IDs and face counts;
  abstained faces → nullable original cluster IDs. Zero-count known roles remain.
- `character-groups-by-image.csv`: `sha16,filename,characters`, including zero-face
  images; roles sorted and `|`-joined, including anonymous fallback roles.
- `character-groups-by-character.csv`: `character,sha16,filename,face_id,sim,margin,decision`;
  one row per face, including abstentions.
- `identity-groups-report.md`: Chinese counts, threshold distributions, terms and caveats.

Multiple faces can associate an image with multiple known or anonymous roles.
Anonymous roles are `新人物NN`; null/outlier clusters use `未知人物`. This is not
forced assignment to the nearest known character. No-face images have empty roles.
Short hashes preserve the frontend contract; the fingerprint and source provenance
retain the full-content identity binding.

## Observed run (not accuracy qualification)

| Snapshot alias | Unique images | 蒂法 | 爱丽丝 / 杰西 / 尤菲 | Unnamed images | Abstained faces | Multi-known-role images |
|---|---:|---:|---:|---:|---:|---:|
| library | 1207 | 489 | 0 / 0 / 0 | 718 | 848 / 1349 (62.86%) | 0 |
| review | 3687 | 1799 | 0 / 0 / 0 | 1888 | 1902 / 3701 (51.39%) | 0 |
| similarity | 448 | 166 | 0 / 0 / 0 | 282 | 285 / 452 (63.05%) | 0 |

Review contains 3688 image records but 3687 unique content IDs; image exports
deduplicate content, while face counts preserve the existing face document.
Named images can also contain abstained faces. Any-abstained-image counts are
642 / 1891 / 283, distinct from completely unnamed-image counts above.

Of the **426** conditional similarity-review candidates from the old largest
cluster, **166** receive 蒂法, **260** remain unnamed and none pass another known
role. These are retrieval proposals, not 166 proven incumbent mistakes or proof
that the other 260 depict different characters.

| Snapshot alias | Anchor build wall s | Group invocation wall s |
|---|---:|---:|
| library | 62.399 | 2.579 |
| review | 47.946 | 5.303 |
| similarity | 40.554 | 0.597 |

The first anchor CLI end-to-end wall was 63.972 s; subsequent anchor coordinator
invocations were 47.994 / 40.606 s. The library grouping reused that just-built
anchor file, not a second timed construction. All use certificate-matched CUDA
FP32 batch 16/four threads for embeddings; saved-vector cosine grouping runs on
CPU. OS/model-cache warming confounds the sequential timings. There is no paired
speedup/regression claim. Source receipts are private output files.

Before/after digests of `scores.csv`, `families.json`, `manifest.sqlite`,
`identities.json` and `identities.npy` remained equal for all three runs.

## Verification and limits

Tests: `tests/test_identity_grouping.py` and `tests/test_identity_grouping_exports.py`.
They cover visual rename/move invariance with real decoding/cropping, filename
invariance through exports, thresholds/ties, individual-anchor disagreement,
self-exclusion, calibration, sampling/dedup/exclusions, many-to-many schema,
profile/digest rejection, confirmation/retraction/conflict and actual grouping CLI.
The synthetic pixel feature extractor is a test seam, not a new model certificate.

Generated gate receipts and the full regression JUnit report live under
`out/identity-grouping-evidence`. Global resource/cancellation/crash qualification,
cross-driver numerical agreement, held-out difficult negatives, calibrated
recognition accuracy and image redistribution rights remain unverified. Numerical
admission does not graduate grouping semantics. Real corpora did not contain a
multi-known-character accepted result; many-to-many behavior is verified synthetically.
