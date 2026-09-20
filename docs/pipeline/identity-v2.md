# Identity v2: fixed-weight crop execution profiles

Identity v2 is an **additive, experimental ranking aid**, not identity verification.
It does not replace `identity_sim`, change legacy CSV columns, alter routes, train
weights, or authorize corpus moves. The GPU lane changes execution, not the model
or crop definition. CPU remains a functional low-end profile.

## Models, immutable revisions, and terms

| Component | Immutable identity | Terms and use |
|---|---|---|
| Anime face detector | `deepghs/anime_face_detection@784dc4c0bb692351ddcdbe6131a050b17d3025d5`, `face_detect_v1.4_n/model.onnx` | Pinned card advertises MIT; ONNX Runtime CPU provider |
| Default face representation | `google/siglip-so400m-patch14-384@9fdffc58afc957d1a03a25b10dba0329ab15c2a3` | Pinned card advertises Apache-2.0; fixed vision tower only |
| Optional CCIP | `deepghs/ccip_onnx@eb2acdd29af1703388d3d0c04221add322bc9110`, `ccip-caformer-24-randaug-pruned/model_feat.onnx` | Pinned card advertises **OpenRAIL**, not unrestricted MIT/Apache; explicit `ccip_license_accepted` required; CPU only |
| Grouping | scikit-learn HDBSCAN, `min_cluster_size=min_samples=3`, normalized Euclidean distance | BSD-3-Clause; probabilities mean membership persistence, not identity correctness |

Detector weight SHA-256, verified on loading:

- n: `fd860b650a4377046842c3cd80d01b0b408bdfbdb4acee5759630f82c6ef04a9`
- Optional s: `403b5bc93b6ff789b7d183418df4a1364049bac00c24acd927604a7ff6891483`

SigLIP-crop is the default because it reuses the exact cached incumbent vision
model, introduces no character-specific weight download or OpenRAIL acceptance,
and enables a controlled whole-image versus crop comparison. **This does not
establish superiority to CCIP.** CCIP's published learned-distance thresholds and
F1 values do not transfer to this adapter's normalized cosine or to these corpora.
The precise OpenRAIL use/distribution terms still need artifact-level review;
the card alone is not commercial or redistribution clearance. No CCIP benchmark
or certification is claimed here. YuNet remains explicit and separately
unqualified; it is never an automatic substitute.

Sources: [pinned SigLIP card](https://huggingface.co/google/siglip-so400m-patch14-384/blob/9fdffc58afc957d1a03a25b10dba0329ab15c2a3/README.md),
[pinned detector card](https://huggingface.co/deepghs/anime_face_detection/blob/784dc4c0bb692351ddcdbe6131a050b17d3025d5/README.md),
[pinned CCIP card](https://huggingface.co/deepghs/ccip_onnx/blob/eb2acdd29af1703388d3d0c04221add322bc9110/README.md),
[third-party notices](../../THIRD_PARTY_LICENSES.md).
Project AGPL does not relicense dependencies, weights, datasets or private images.
The legacy quality pipeline's pyiqa noncommercial restriction remains separate.

## Semantic versus execution identity

Detection remains pinned CPU ONNX inference on legacy decoded RGB, stretched to
640×640 with bilinear interpolation, confidence 0.3, NMS IoU 0.5, minimum face
side 24 pixels. Crops are xywh, longest side 256, LANCZOS, JPEG quality 90,
4:4:4, no EXIF/ICC; the official pinned SigLIP processor then produces 384×384
input. Preprocess version is `crop-jpeg-v1-siglip-official`.

| Request | Actual execution |
|---|---|
| `identity.device: cpu` | CPU FP32, batch 1, four threads by default |
| `identity.device: cuda` | Explicit CUDA FP32 by default, bounded configured batch; unavailable CUDA is an error, never silent CPU fallback |
| `identity.device: auto` (default) | CUDA only when the numerical certificate matches runtime, GPU, precision, batch, weights and preprocessing; otherwise CPU |

Inference uses `torch.inference_mode()`, `eval()`, disabled gradients, explicit
SDPA, disabled TF32, and FP32 normalization after the GPU result is copied back.
`identity.precision: float16` remains an explicit **uncertified experiment**:
the measured FP16 candidate failed the predeclared numerical budgets. CPU uses
FP32 regardless of the GPU precision preference. The corpus matrix remains FP16
and is normalized to FP32 for clustering; FP16 storage is tested separately from
FP16 inference.
GPU batch size is independent of the legacy scorer's batch setting. Changing
embedding device/batch does not invalidate existing detector/crop provenance.

Cache design:

```text
execution = device + precision + batch + kernel + runtime versions + GPU identity
embedding-profile = SHA256(canonical JSON(execution, model@revision, preprocess))
namespace = SHA256(embedding-profile + detection semantic-profile digest)
entry = cache/identity-embedding/<namespace>/<full crop SHA256>.npy
```

Each entry has a SHA-256 integrity sidecar. Every crop is checked against saved
provenance before either a hit or inference. Hits and fresh vectors must be
finite/nonzero; batching preserves ordered face association, including ragged
tails. The final matrix is published only after all rows are available, and its
ledger binds matrix digest and exact face order. Old CPU namespaces are retained
but **never consulted for CUDA keys**, even after numerical certification. A
profile change re-embeds every face; interruption resumes only that exact profile.
Do not run concurrent identity writers to the same output.

## Numerical experiment and predeclared budgets

`tools/certify_identity.py` selects 128 faces from each of `out/library`,
`out/review`, and `out/similarity`, sorting SHA-256 of a fixed seed plus face ID.
The 384 crop digests and ordered face IDs are retained in the private sample
manifest. Fresh CPU FP32 serial and CUDA FP16 batch 1/8/16/32 outputs are computed
on exactly those RGB crops. No partial historical CPU cache supplies references.

Budgets are written before inference:

- Every normalized component: `abs(gpu - cpu) <= 0.001 + 0.001 * abs(cpu)`.
- Maximum per-face cosine deviation: `1 - cosine(cpu, gpu) <= 1e-5`.
- Pairwise cosine absolute error: at most 0.002.
- A diagnostic cosine cutoff of 0.85 has ambiguity band ±0.002; no flips outside
  that band. This is a numerical probe, **not a calibrated identity threshold**.
- Sample HDBSCAN adjusted Rand index at least 0.99; outlier changes at most 1%.
  Passing components alone does not certify clustering or downstream decisions.
- Also compare FP16 persisted vectors and GPU batched versus serial vectors.

GPU batch timing uses ten randomized-order repetitions per batch size on the
same 128-crop slice, after warmup. Timing includes preprocessing, transfer,
synchronized inference and FP32 normalization, but not model load or corpus
cache writes. Whole-corpus timings separately include those costs. Allocator
allocated/reserved VRAM is not total-board usage; process peak working set is
not an admission guarantee. Historical CPU 6.2 s/face is not a controlled paired
speed benchmark of this newly isolated runtime.

### Rejected FP16 candidate

The initial experiment completed in approximately 42.4 minutes, dominated by
fresh CPU reference inference: **2239.409 s / 384 = 5.831795 s/face**. GPU FP16
batch 16 took 14.245 s / 384 = 0.037096 s/face, but that speed is **not admitted**.

| Corpus (128 faces each) | Maximum cosine deviation | Maximum component error | Original numeric gate |
|---|---:|---:|---|
| library | 1.24850e-4 | 1.95865e-3 | fail |
| review | 1.00500e-4 | 1.9571e-3 | fail |
| similarity | 8.8310e-5 | 1.6582e-3 | fail |

Pooled batch-16 pairwise cosine error reached 0.00357014, above 0.002.
GPU FP16 serial additionally produced four directed probe flips outside the
ambiguity band. Sample cluster ARI=1 and no outlier changes do **not** override
these failures. No tolerance was relaxed and no production corpus was embedded
under FP16. Raw negative evidence stays in `out/identity-certification/results.json`.

The next candidate, CUDA FP32, reuses those exact CPU reference vectors and crop
digests. `tools/certify_identity_fp32.py` records its budgets before inference:
the original budgets remain, with an additional stricter component diagnostic
`abs(gpu - cpu) <= 1e-5 + 1e-4 * abs(cpu)` and zero rank inversions outside a
pairwise gap of 0.004. [ADR-0004](../../specs/adr/ADR-0004-gpu-fp32-admission-criterion.md)
records the subsequent approved classification of the strict component check as
diagnostic-only: its measured failure is retained, not relabeled a pass. All
primary budgets remain unchanged. Only matched CUDA FP32 batch 16/four threads
is admitted, with ARI ≥0.99, zero outlier changes, zero probe/rank changes outside
ambiguity, and batch/storage equivalence. `tools/publish_identity_certificate.py`
checks saved measurements and hashes, writes `admission-receipt.json` alongside
the private evidence, then installs `src/artcurator/identity-certification.json`.
Strict kernel equivalence and identity-v2 semantic graduation remain unqualified.

### Scoped CUDA FP32 results

**The original normalized/stored embedding contract passes. The additional
strict FP32 component test does not pass on the review sample.** The admission
criterion and its scope are recorded in ADR-0004 above; no claim that all global
quality gates or strict FP32 kernel equivalence passed is made.

Tested hardware/runtime: Windows, RTX 5060 Ti 16 GB (sm_120), driver 610.88,
PyTorch 2.11.0+cu128, Transformers 4.57.6, Pillow 12.3.0, NumPy 2.5.2,
ONNX Runtime 1.30.0, four CPU threads, CUDA FP32 SDPA, TF32 off, batch 16.

| 128-face sample | Cosine deviation max / median | Component error max / median | Strict FP32 component test |
|---|---:|---:|---|
| library | 4.73747e-9 / 2.76166e-11 | 1.08033e-5 / 1.45286e-7 | pass |
| review | 1.60080e-8 / 1.68927e-11 | 2.59280e-5 / 1.17201e-7 | **fail** |
| similarity | 1.24367e-9 / 1.33566e-11 | 8.02800e-6 / 1.04308e-7 | pass |

All three have ARI=1, zero changed outliers, zero diagnostic flips outside
ambiguity, and zero strict rank inversions outside the 0.004 gap. Across GPU
batch 16 versus serial, maximum component error is 2.38419e-7 and cosine
deviation at most 1.30119e-13. FP16 **storage after FP32 inference** also passes
the original contract: worst component error 1.23203e-4 and cosine deviation
3.20389e-8. FP16 storage is not FP16 computation.

Thus the measured CPU and GPU profiles are numerically interchangeable **within
the original declared embedding/storage tolerance on these samples**, but not
under the stricter FP32 test, not bitwise, and not proven interchangeable for
full-corpus clustering. Sample clustering agreement is evidence, not a guarantee
on untested boundary faces or future corpora. All production matrices were
re-embedded under one GPU profile regardless; no CPU cache reuse was authorized.

The certificate binds package/device identity, not the driver; driver/OS changes
require manual recertification. Evidence chain (private receipts, public digests):

- `out/identity-certification/fp32-results.json`:
  `f9d0c6a5e59f5342805a4841cd76fe2a58f8ba08546fde50c5066d83a7cf48c3`.
- Ordered sample manifest:
  `4441b12db918b52280937dc14dbae1832be6691d1beae9ca7d4ee14ac030d0c4`.
- CPU FP32 reference array:
  `cc129fcc640c5c1fbbffa1c72a9c706f31104db3f572d9095ba2ae98cd57650b`.

### Batch selection and measured cost

An initial FP32 timing sweep had possible transient contention. It is retained,
but **not used for the final cost claim**. The final run repeated all three batch
sizes ten times in deterministic randomized order, with no other inference job.
Each repetition processes the same 128 crops, not 384.

| Batch | Median s/face | p95 s/face | Peak allocated GiB | Peak reserved GiB |
|---:|---:|---:|---:|---:|
| 8 | 0.088930 | 0.089733 | 1.908 | 2.215 |
| **16 (default)** | **0.088641** | **0.089513** | **2.210** | **2.596** |
| 32 | 0.087444 | 0.088079 | 2.808 | 3.352 |

Batch 32 is about 1.35% faster, but batch 16 reserves about 22.6% less VRAM;
that small throughput difference does not justify the larger default. The
default is a measured memory/throughput tradeoff, not a claim that 16 is fastest.
Raw repetitions: `out/identity-certification/uncontended-benchmark.json`.

Historical CPU **6.2 s/face → GPU 0.08864 s/face**, approximately **69.9×** at the
inference boundary. The freshly measured CPU reference was 5.83179 s/face,
approximately 65.8× the GPU median. These ratios are observations, not a
ten-pair CPU/GPU end-to-end regression certificate.

| Corpus | Images / faces | Historical detection s (s/img) | GPU embedding stage s (s/face) | Cluster s | Report s | Fresh GPU rerun wall s |
|---|---:|---:|---:|---:|---:|---:|
| library | 1207 / 1349 | 163.375 (0.13536) | 181.834 (0.13479) | 5.931 | 0.297 | 189.353 |
| review | 3688 / 3701 | 217.809 (0.05906) | 517.429 (0.13981) | 40.522 | 0.587 | 559.954 |
| similarity | 448 / 452 | 69.940 (0.15612) | 62.640 (0.13858) | 0.676 | 0.072 | 63.481 |

Full embedding stage includes crop reads, model load, hash checks, durable cache
writes and final publication, so it is slower than inference-only timings.
Inference-only corpus rates are respectively **0.08921 / 0.08919 / 0.08840 s per
computed face**. All 5502 face rows now use CUDA FP32. Review has 3691 distinct
crop digests for 3701 faces: ten identical-content crop hits were produced within
the new GPU namespace, not obtained from the partial CPU cache. Library and
similarity computed 1349 and 452 fresh vectors with zero hits.

Peak process working set: **2.367 / 2.373 / 2.734 GiB**. This is Windows process
high-water memory, including model loading; the review/similarity invocation
shares cumulative process history. Peak allocator VRAM allocated is approximately
2.210 GiB; reserved is **2.596 / 2.596 / 2.783 GiB**. Reserved memory in the later
corpus includes allocator history. These are not sampled total-board peaks.

Detection was not unnecessarily repeated. Adding its historical stage time to
the fresh GPU rerun gives composite totals **352.728 / 777.763 / 133.421 s**;
these are **not single uninterrupted measured wall times**. Fresh GPU reruns total
812.788 s (13m33s), excluding environment setup, certification and historical
detection. Source receipts: each output's `identity-timings.jsonl`,
`identity-embedding.json`, `identity-gpu-run.json`, plus generic aggregates
`out/identity-certification/{corpus-runs,summary}.json`.

Before/after hashes of legacy `scores.csv`, `families.json` and `manifest.sqlite`
match for every corpus. Old CPU caches and archived sidecars are preserved;
`tools/build_gallery.py` and image corpora were not modified. Two abandoned
process locks were removed only after their owning PIDs were confirmed absent;
the successful run receipts preserve fresh-run costs rather than hot-cache reruns.

## Leave-one-out A/B method

For query face vector `v` and target member set `C`, use
`cos(v, sum(C) - v)` when the query belongs to `C`; otherwise use `cos(v, sum(C))`.
Only nonexcluded members contribute. A singleton self-query or zero-norm target
is unavailable. For several targets, take the maximum available cosine, then
take the maximum available face score per image. Missing scores never become 0.

Without human references the largest cluster is an **unlabeled ranking proxy**.
With confirmed references, only the selected confirmed character's clusters are
targets. Reports label the method `leave-one-out-target-centroid-v1`. LOO removes
direct self-inclusion, but not cluster-selection bias, related-image dependence
or leakage from another face in the same image. Reports are not held-out tests.
Applying the old whole-image numeric cutoffs to crop cosines is deliberately
reported as an uncalibrated diagnostic, not a production routing policy.

### Regenerated LOO A/B results

| Corpus | Clusters / outlier faces | Paired images / unavailable | LOO image mean / median | Pearson / Spearman versus incumbent |
|---|---:|---:|---:|---:|
| library | 11 / 302 | 1081 / 126 | 0.943025 / 0.952983 | 0.285917 / 0.235813 |
| review | 3 / 6 | 3688 / 0 | 0.939883 / 0.955231 | 0.497466 / 0.420607 |
| similarity | 2 / 4 | 448 / 0 | 0.936521 / 0.944335 | 0.686302 / 0.639991 |

Same-number legacy cutoff diagnostics (old-below/new-above; old-above/new-below):

| Corpus | P10 cutoff: directional counts | P20 cutoff: directional counts | P90 cutoff: directional counts |
|---|---|---|---|
| library | 0.600903: 62; 2 | 0.643239: 162; 0 | 0.851473: 927; 1 |
| review | 0.694368: 369; 1 | 0.725985: 738; 1 | 0.836366: 3097; 2 |
| similarity | 0.727575: 45; 0 | 0.758418: 89; 0 | 0.860311: 380; 0 |

**Culled-corpus re-check:** the similarity corpus has **426/448 unique images**
with a non-outlier face in the largest target cluster (429 faces). These are
review candidates, **not 426 proven false kills**. The corresponding conditional
counts in library/review are 939/3687. In particular, review's dominant cluster
contains 3687 of 3701 faces: such broad grouping cannot establish identity
discrimination. No labels means neither these high cosines nor disagreement
counts establish improved quality, precision or recall.

All three outputs now contain regenerated `identity-faces.csv`, `identity-ab.json`
and `identity-ab-report.md`. Report SHA-256 values in corpus order:

- `f94af29b4a25f7a6e61c5146c3b529e5dccf4c66f26d9c43f3d44002b6f3216a`
- `b466ea7ed7cd995e76964ddf39ec16658d139b37eac8236dab524bde8892ee51`
- `a8535af2293c89bccc325b7869ae4caec1a88e413cd64ba21c47b0a6f7e7f462`

## Synthetic naming loop

`tools/check_identity_labels.py` drives the **actual CLI** on 12 synthetic faces:
confirm one face in the second cluster → pin the character → regenerate the
LOO assignment-change report → recluster → reapply the same envelope.

Observed: one changed face, one changed cluster, **12 changed image assignments**;
the confirmed character survives reclustering; replay changes zero faces and
zero clusters. Matrix and manifest digests are unchanged. Private receipt:
`out/identity-labels-e2e/receipt.json`. This tests retrieval state, not training;
it does not qualify merge/split/undo or crash-atomic naming publication.

Regression coverage includes option validation, auto admission/mismatch,
unavailable explicit CUDA, independent detection semantics, cache profile
invalidation, ragged batches, corrupt-entry recompute, clearing stale clusters,
LOO self-exclusion/singletons/zero centroids, and naming-to-changed-assignment
reports. Existing identity tests are retained. The configured LSP server was
unavailable and installation had previously been declined; LSP cleanliness is
therefore not claimed. Test/build results are separate from numerical admission.

## Operation

Use an isolated CUDA environment rather than altering existing quality-scorer
environments. A CPU-only PyTorch installation cannot use CUDA just because an
NVIDIA driver is present. The tested identity runtime is separately inventoried.
When invoking the tools through uv with the existing environment, include the
literal `python` before the script: this avoids PEP 723 creating a fresh overlay
without the locally installed package or the selected CUDA wheel.

```powershell
uv run --no-project --python .venv-identity/Scripts/python.exe python tools/certify_identity.py out/library out/review out/similarity
uv run --no-project --python .venv-identity/Scripts/python.exe python tools/certify_identity_fp32.py out/library out/review out/similarity
uv run --no-project --python .venv-identity/Scripts/python.exe python tools/run_identity_gpu.py out/library out/review out/similarity
uv run --no-project --python .venv-identity/Scripts/python.exe python tools/check_identity_labels.py
```

For individual stages use `python -m artcurator.cli identity-embed`, then
`identity-cluster`, then `identity-report`, with `--out` and `--config` as usual.
Do not rerun detection merely to change embedding device. The corpus runner
preserves prior CPU sidecars in `identity-cpu-baseline/`, hashes the legacy
manifest/CSV/families before and after, and writes `identity-gpu-run.json`.

## Qualification limits and risk

- Numerical evidence is scoped to the exact crops, model and execution identity.
  No blanket CPU/GPU, new-driver, new-runtime or cross-model interchangeability.
- No labeled hard-negative/confusable evaluation, calibrated precision/recall,
  false-merge/split budget or identity-v2 semantic graduation. The conditional
  culled-corpus count is a review list, not proven false kills of the incumbent.
- GPU batch timings are engineering evidence, not full NFR-GATE-007 cold/warm
  CPU/GPU end-to-end regression certification. No resource-pressure/admission,
  concurrent-writer or cancellation stress qualification is claimed.
- Legacy rendering still strips PNG ancillary ICC/EXIF; canonical rendering
  invariance remains unqualified. Faces may be missed, including small, occluded,
  profile and stylized faces. Hair, clothing and background remain in crops.
- HDBSCAN membership and public numeric cluster IDs can change with execution
  roundoff or corpus growth. No frozen membership promise. Nearest-other-centroid
  `cluster_margin` is confusability, not a calibrated target-versus-other margin.
- Human events are hash chained, but registry/document/report publication is not
  a multi-file transaction. Maintain backups; unknown/outlier cases stay reviewable.
- No model weights, private images, machine paths or private corpus names are
  distributed in this document. Generated production outputs stay private.
