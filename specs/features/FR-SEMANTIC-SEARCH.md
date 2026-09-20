> 中文摘要
> 中文搜图仅为用户检索入口，不得进入质量评分、分层或角色决策。
> 本次预注册固定同一批裁剪、留一锚点分类和提示词自检索指标。
> 人脸替换须领先基线至少五个百分点；搜索须命中率达六成且满足预算。
> 缺失配对证据、许可证或资源超限一律不采用，不把未知写成零分。

# Semantic search and bounded embedder spike

Scope: experimental local CUDA inference; fixed weights; no production integration.
Status: proposed, preregistered before environment creation or metric computation.
Registration date: 2026-09-20. Normative dependencies: INV-1–4,
FR-CACHE-001, NFR-GATE-006/007/009. Evidence: `out/wemm-spike/`;
public synthesis: `docs/pipeline/wemm-spike.md`. Corpus aliases below are logical,
not instructions to rename or write source directories.

### FR-SEARCH-001 — Query-only surface
When a user supplies Chinese text, the search surface shall rank image-only index
vectors by cosine similarity to the text vector and display source image links.
The system shall keep text, prompts and retrieval ranks out of scoring, tiering,
grouping and identity decisions (INV-2). No weights are trained or adapted.
- AC-FR-SEARCH-001-01: inspect the spike adapter; image encodings receive pixels
  only, text encodings are confined to search, and no production scorer is edited.
  Fixture: immutable input manifest; evidence: source and report.

### FR-SEARCH-002 — Paired crop comparison
When comparing embedders, the evaluator shall use existing face crops without
redetection and reuse saved SigLIP vectors without recomputation.
- Fixture: `out/review/faces`, `identities.json`, `identities.npy`, and existing
  anchor manifests from `out/library`, `out/review`, `out/similarity`.
- Primary: leave-one-anchor-out cosine 1-NN character accuracy on all 145 anchors
  (class counts 64/42/20/19). Remove self before neighbor selection. Report
  numerator/denominator per class, overall and macro accuracy. Uniform guessing
  is 25%; majority-class guessing is 64/145, so 25% is not the majority baseline.
- Require an exact, auditable mapping of each anchor crop to a saved baseline
  vector and the same WeMM input. Missing baseline anchors block the primary
  comparison; never substitute full-image vectors, label by cluster, or recompute
  SigLIP. A smaller paired subset may be diagnostic, never adoption evidence.
- Deterministic order: full input SHA-256 then original row number; ties resolve
  to that order. Report duplicate hashes and possible near-duplicate leakage.
- Secondary: HDBSCAN on L2-normalized vectors, Euclidean metric,
  min_cluster_size=3, min_samples=3, cluster_selection_method=eom; no tuning.
  Compare against existing cluster IDs as **pseudo-labels, not ground truth**.
  Report ARI including noise, purity with predicted noise as singleton groups,
  and non-noise coverage. Exclude rows lacking existing pseudo-labels explicitly.
- Anchor margins: maximum neighbor cosine per character, self excluded; report
  best minus second-best class gap and true-class minus best-other-class gap,
  min/p05/p25/median/p75/p95/max and fraction of negative signed margins.
- WeMM native 2048 dimensions is the adoption candidate; first-1024 dimensions
  followed by L2 renormalization is a separately reported MRL diagnostic.
  MRL cannot rescue a failed native primary rule. CCIP is optional and skipped
  unless source and weight licensing are independently cleared within the bound.
- AC-FR-SEARCH-002-01: manifest joins, saved vectors and metric receipts establish
  paired counts and all above statistics; unavailable entries remain unavailable.

### FR-SEARCH-003 — Retrieval evaluation
When testing search, the evaluator shall index all available review previews,
pre-resized to at most 1024 pixels on their longest edge, without image text.
- Labeled part: exactly 37 original sidecar prompts query the full preview index;
  success means the associated image ranks in top 10. No query rewriting,
  translation, cherry-picking, or reducing the distractor pool. Ties use hashes.
  Missing/ambiguous sidecar associations block the 37-query adoption test.
- This measures prompt-to-own-image self-retrieval, not general Chinese relevance
  accuracy. Report prompt language distribution; do not claim Chinese quantitative
  validity if prompts are not Chinese. Report hits/37 and Wilson 95% interval.
- Freeze ten Chinese qualitative queries from inspected corpus content before
  seeing rankings. Record top five opaque image IDs and cosines per query as
  anecdotes only, with no accuracy or human-relevance claim.
- Save float32 2048 and renormalized 1024 matrices; report actual NPY sizes,
  metadata size separately, build wall time, and query encoding plus exact cosine
  ranking latency after one excluded warmup. Report all 37 raw latency samples,
  median and p95; exclude model loading but include tokenization and GPU sync.
- AC-FR-SEARCH-003-01: frozen query/mapping manifest and result receipts contain
  all 37 ranks, complete index count, sizes and ten anecdotal top-five lists.

### NFR-SEARCH-001 — Execution and provenance bound
When running this spike, the evaluator shall create only `.venv-wemm` and new
spike outputs, leave corpus and existing environments untouched, and pin model
revision, package versions, preprocessing and execution profile in receipts.
- Model revision: `tencent/WeMM-Embedding-2B` at
  `bbd6cd4bf52cfc6716f752a2df80b2706720bd95`; inspect its actual LICENSE and code
  before `trust_remote_code=True`. Cache keys bind complete source SHA-256,
  model revision, code digests, resize/filter, dtype, dimensions and version.
- Profile: single CUDA device, BF16 weights, eval/inference mode, batch one,
  RGB Pillow decode, EXIF transpose, LANCZOS thumbnail <=1024, no upscaling.
  Fixed upstream embedding chat framing only; no per-image text. Native PyTorch
  kernels, no training, quantization, CPU offload or automatic precision fallback.
- Bound: at most 90 minutes total inference and 30 minutes provisioning/download;
  stop on OOM or invalid outputs. Partial outputs are diagnostic, not a pass.
  Download/inference commands are detached with logs; foreground commands <=240s.
- Report CUDA peak allocated/reserved bytes (not total-board VRAM), crop decode /
  embedding / persistence wall, seconds per face and linear 5,500-face projection.
  This spike is not NFR-GATE-007 certification: no ten-pair equivalence benchmark.
- AC-NFR-SEARCH-001-01: environment freeze, licenses and SHA-256 manifests,
  synchronized timings, completion coverage and report support only scoped claims.

### FR-SEARCH-004 — Preregistered adoption rule
When issuing the verdict, the evaluator shall adopt the native crop embedder only
if its complete 145-anchor overall accuracy exceeds saved SigLIP-crop accuracy by
at least **5 absolute percentage points**, with valid provenance and resource fit.
When issuing the search verdict, the evaluator shall adopt search only if complete
37-query Hit@10 is **at least 60%** (at least 23 hits), query p95 is **<=2 seconds**,
and the native float32 index is **<=10 KiB/image + 1 MiB fixed overhead**, with
build completion within the inference bound and valid licenses/provenance.
- These are exploratory adoption thresholds, not production certification.
  Index budget admits 8 KiB native vectors with bounded metadata overhead;
  two-second p95 targets interactive local UX. No post-result budget changes.
- Missing required evidence means **DO-NOT-ADOPT (inconclusive)**, not a measured
  model-quality failure. Report exactly which observed number or evidence gate
  fails. Secondary metrics and anecdotes cannot override the primary rule.
- AC-FR-SEARCH-004-01: compare immutable preregistration digest against report;
  provide separate crop/search verdicts with numerators, thresholds and limitations.
