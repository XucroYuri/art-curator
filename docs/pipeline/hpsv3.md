# HPSv3: fifth local quality scorer

Measured on 2026-09-19, Windows, **one RTX 5060 Ti 16 GB**, driver 610.88.
All 5,343 file rows completed locally; the review corpus contains one duplicate,
so 5,342 distinct-content evaluations were performed across the three runs.
No corpus files were written, moved, renamed, or used for training. No images
were sent to a service. Network access downloaded public dependencies/weights only.

## Upstream identity and API

- [Official implementation](https://github.com/MizzenAI/HPSv3), PyPI **hpsv3 1.0.0**.
- [Reward checkpoint](https://huggingface.co/MizzenAI/HPSv3/tree/4f81e3e09edd82fe3c5f636444c721b592a735ca):
  `MizzenAI/HPSv3`, revision `4f81e3e09edd82fe3c5f636444c721b592a735ca`,
  `HPSv3.safetensors` (736 state-dict keys, complete fine-tuned backbone and head).
- [Architecture configuration and processor](https://huggingface.co/Qwen/Qwen2-VL-7B-Instruct/tree/eed13092ef92e448dd6875b2a00151bd3f7db0ac):
  `Qwen/Qwen2-VL-7B-Instruct`, revision `eed13092ef92e448dd6875b2a00151bd3f7db0ac`.
- The HPS model card/config metadata mentions Qwen2.5, but the official inference
  YAML and implementation instantiate **Qwen2-VL-7B** with a RankNet reward head.
  We follow that implementation, not `AutoModel` against the misleading HPS config.
- The wheel exposes `reward(image_paths, prompts)`; current GitHub source has the
  positional arguments reversed. We use **keyword arguments**, decoded PIL RGB
  objects rather than source paths, `prompts=[""]`, and inference mode.
- The raw second head channel is **log sigma**, despite informal `(mu, sigma)`
  descriptions. In `hpsv3/model/qwen2vl_trainer.py`, the uncertainty loss uses
  `sigma_chosen = torch.exp(rewards_A[:, 1])`. Exported `hpsv3_sigma` therefore
  equals `exp(raw[:, 1])`; it is not the signed raw log value.

### What prompt-free means here

There is **no image-specific prompt/caption** and no filename, path, EXIF, PNG
text or generated caption in the model input. The upstream fixed evaluation
instruction, chat framing and `<|Reward|>` token remain. Thus this is pixel-only
with respect to corpus information, **not literally a text-token-free VLM**.
Upstream does not expose a separately validated image-only inference mode.
Empty-prompt use is an evaluation adaptation, not evidence that published
prompt-alignment benchmarks transfer to this corpus. The fixed instruction
also contains a safety preference, so HPS quality can correlate with safety.

## Isolated environment and reproduction

Main `.venv` still has Transformers **4.57.6**, pyiqa **0.1.15.post2**;
`.venv-qrealign` still has Transformers **5.17.0**, pyiqa **0.1.16**.
Neither environment's dependency pins were changed.

HPS environment: Python **3.12.13**, torch **2.11.0+cu128**, torchvision
**0.26.0+cu128**, Transformers **4.45.2**, tokenizers **0.20.3**, hpsv3 **1.0.0**,
accelerate **1.8.0**, bitsandbytes **0.50.2**, peft **0.10.0**, trl **0.8.6**,
huggingface-hub **0.36.2**, safetensors **0.8.0**. Root
`environment-versions.json` records **all distributions in all three environments**
and both immutable revisions. `tools/hpsv3_versions.py` refreshes that ledger
without installing anything.

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv venv --python 3.12 .venv-hpsv3
uv pip install --python .venv-hpsv3\Scripts\python.exe torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv-hpsv3\Scripts\python.exe --no-deps hpsv3==1.0.0
uv pip install --python .venv-hpsv3\Scripts\python.exe transformers==4.45.2 peft==0.10.0 trl==0.8.6 accelerate==1.8.0 bitsandbytes==0.50.2 huggingface-hub==0.36.2 safetensors==0.8.0 qwen-vl-utils==0.0.11 diffusers==0.33.1 ImageHash pydantic omegaconf fire pandas opencv-python matplotlib tensorboard rich
uv pip install --python .venv-hpsv3\Scripts\python.exe --no-deps -e .
.venv-hpsv3\Scripts\python.exe tools/probe_hpsv3.py bf16
.venv-hpsv3\Scripts\python.exe tools/probe_hpsv3.py 8bit
```

The upstream Linux conda environment cannot be installed verbatim on Windows.
An ordinary wheel dependency install attempted to build DeepSpeed and failed;
the inference environment deliberately omits that training-only dependency.
Upstream imports pandas/matplotlib/training helpers transitively; our pipeline
does not use pandas or run training. Optional FlashAttention is absent; **SDPA**
is used. The JSON ledger, not the abbreviated command above, is the complete
resolved version inventory.

The loader constructs the **official wheel's reward-model class on meta tensors**,
checks the exact checkpoint key set, and loads the complete reward checkpoint
directly. It does not download another 7B base checkpoint just to overwrite it.
The tokenizer adds the upstream reward token (vocabulary 151658).
Upstream requests unsupported CUDA float32 autocast at its FP32 head; an explicit
FP32 input cast at that boundary makes the intended head computation executable.

## VRAM and quantization path

Baseline device usage before HPS loading was 1,787 MiB. Other pipeline models
were not loaded; workers ran sequentially on `cuda:0`. There is no `cuda:1` path.

1. **Unbounded bf16 probe:** completed one image, but needed 16,822,635,008 bytes
   peak PyTorch allocation and 17,106,468,864 bytes reserved; inference took
   **40.351 s**. On Windows WDDM, successful allocation does not demonstrate that
   a model fits dedicated VRAM: shared-memory paging can avoid an OOM exception.
2. To avoid relying on paging, the loader caps its PyTorch allocator at **85% of
   physical VRAM** (13.54 GiB on the reported 15.93 GiB device). With this explicit
   budget, **bf16 OOMed during loading** at 14,334,075,904 allocated bytes. This
   is an allocator-budget OOM, not a claim that the original unbounded run threw.
3. A monolithic 8-bit load also staged the entire archive on CUDA before
   quantizing, reaching 23,268,086,272 allocated bytes. The fix was **lossless
   safetensors sharding**, approximately 256 MiB per shard (individual tensors
   remain whole), with an atomically published index. Shards live beside the
   pinned archive in the project cache and contain the same tensors.
4. **Selected: bitsandbytes LLM.int8** for language linear layers. Vision and
   `lm_head` stay bf16; the small reward head stays FP32. There is no CPU/disk
   model offload. bitsandbytes casts its bf16 activation inputs to FP16 internally;
   its repetitive warning is retained once per worker, not once per layer/image.
5. Sharded 8-bit probe: **10,352,291,328 allocated / 10,875,830,272 reserved bytes**,
   **2.711 s** for the first image. Production peaks are below.
   **4-bit and CPU fallback were unnecessary and were not benchmarked.** Explicit
   worker `--precision 4bit` / `--precision cpu` paths exist, not automatic model
   substitution. CPU uses bf16 and has no advertised performance guarantee.

These are **PyTorch peak allocated/reserved bytes**, including loading and
inference, not sampled NVML total-board peaks; non-PyTorch/context/display memory
is additional. The largest production peaks were **9.69 GiB allocated / 10.97 GiB
reserved**. Sharding adds approximately one checkpoint's worth of local storage.
The unbounded and sharded probe receipts are retained under `out/library/`.

Quantization is not numerically neutral: on the single probe image, bf16 mu was
5.798818 and int8 mu was 5.943076 (delta **+0.144258**); sigma was 0.0118732 versus
0.0114963. This is **one diagnostic sample**, not a quantization-quality study.
Both monolithic and sharded int8 probes produced the same pair.

## Schema, consensus and uncertainty: exact rules

Frozen scorer order:

```text
aes_v25, topiq_iaa, topiq_nr, qrealign, hpsv3_mu, hpsv3_sigma, nsfw_prob, ...
```

All existing columns retain relative order. Scan initializes the two new optional
fields through `db.Row`; old SQLite JSON payloads migrate by defaults, and the
SQL view is rebuilt by the existing database boundary. HPS pairs are cached
together, keyed by checkpoint/processor revisions, preprocessing and precision.
The main `score`/`run-all` path invokes an isolated worker, never imports HPS into
the aesthetic environment. A `--max-new` content budget permits bounded resumes.

For each of the five quality means, standardize over the corpus using population
SD (`ddof=0`); a constant column becomes zero. Let their per-image z-values be
`z_ij`, and let `m_i` be the number present (five in all delivered outputs):

```text
a_i = sum_j(z_ij) / m_i
consensus_z_i = population_zscore(a)_i
d_between_i² = sum_j((z_ij - a_i)²) / m_i
s_H = population_sd(hpsv3_mu)
d_i = sqrt(d_between_i² + (hpsv3_sigma_i / s_H)² / m_i)
uncertain_i = (d_i > settings.uncertain)     # unchanged default 1.2
```

The native term is omitted when HPS is absent or `s_H <= 1e-12`. This is the
variance of an **equal-weight mixture of scorer estimates**, not a standard error
of the consensus mean. Sigma adds within-HPS variance **once, at weight 1/5**;
it is never a sixth score, an extra flag, a quality penalty or a reweighting of mu.
The result is stored in existing `disagreement`; no separate sigma-derived
uncertainty flag is added. Native sigma is not calibrated error on illustrations,
and scorer correlations are not modeled. Legacy all-missing HPS retains the
four-scorer behavior; partially completed HPS raises before clustering.

P90 queue/P75 review quantiles, identity/safety gates, family rules and audit
sampling are unchanged, but quantiles and family champions are recomputed.

## Measured cost

Batch one; all weights local after initial download. Inference includes strict
decode, official resize/preprocessing, CUDA work and cache I/O. It includes the
first image in each invocation; no warmup time has been subtracted.

| Corpus | File rows / unique | Inference s | s/file row | Load s (sum) | Worker wall s | CLI wall s | Peak allocated / reserved GiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| library | 1207 / 1207 | 1014.763 | **0.84073** | 320.359 | 1348.706 | **1375.286** | 9.66 / 10.75 |
| review | 3688 / 3687 | 3221.542 | **0.87352** | 464.027 | 3705.472 | **3739.230** | 9.69 / 10.97 |
| similarity | 448 / 448 | 427.737 | **0.95477** | 88.950 | 517.317 | **525.249** | 9.65 / 10.61 |

CLI wall is **sum of active scoring-command durations**, including interpreter,
load and shutdown costs: 22m55s, 62m19s and 8m45s. It excludes pauses between
commands, setup/download/probes, cluster/report and gallery generation. Worker
wall is a narrower boundary beginning after torch import; both are retained to
avoid conflating them. Review cost per unique evaluation is **0.87376 s**.

Pilot used new-content budgets 256/768/183; review 1000/1000/850/837 (the 850
batch covered 851 rows); similarity 448. All invocations completed below 1200 s,
so **no interrupted HPS timing prefixes are missing**. First pilot batch included
verbose upstream cast warnings; later batches deduplicated those warnings.
This and normal runtime variability prevent interpreting timing differences
between corpora as a controlled benchmark.

**HPS is now the slowest observed quality-scoring pass.** Prior complete Q-ReAlign
measurements were 0.65092 s/row (pilot) and 0.76635 (similarity), versus HPS
0.84073 and 0.95477. Review's historical Q-ReAlign table contains only a resumed
tail, so its 0.03110 s/all-rows figure is **not** a fresh inference cost. Historical
progress intervals cover 3,672 new evaluations in 2,382.109 s, or **0.64872 s/img**
(excluding load and short unsampled tails), also below HPS. Prior smaller scorers
were faster. These are historical comparisons, not simultaneous reruns.

## Tier movement (four scorers -> five scorers)

| Corpus | Archive | Queue | Review | Identity route | NSFW route | Rows changing tier |
|---|---:|---:|---:|---:|---:|---:|
| pilot | 710 -> 704 (-6) | 62 -> 71 (+9) | 275 -> 272 (-3) | 121 -> 121 | 39 -> 39 | **154** |
| review | 1979 -> 1973 (-6) | 186 -> 174 (-12) | 795 -> 813 (+18) | 357 -> 357 | 371 -> 371 | **429** |
| similarity | 134 -> 126 (-8) | 7 -> 9 (+2) | 42 -> 48 (+6) | 37 -> 37 | 228 -> 228 | **19** |

For pilot, transitions were archive->review 55, review->archive 50,
queue->review 20, review->queue 28, archive->queue 1. Net counts alone would hide
most of these 154 changed decisions. Source identities and all prior quality,
safety and identity scores were checked unchanged against saved baselines.

| Flag | pilot | review | similarity |
|---|---:|---:|---:|
| uncertain | 85 | 197 | 35 |
| gaming_suspect | 15 | 53 | 3 |
| near_dup_runnerup | 0 | 32 | 0 |
| audit_sample | 38 | 96 | 6 |
| id_low | 121 | 357 | 37 |
| nsfw | 39 | 371 | 228 |

Flags overlap; they are not a disjoint tier partition.

## Outputs, resume and verification

Each corpus has regenerated `manifest.sqlite`, `scores.csv`, `families.json`,
`summary.md`, and `gallery.html`. Local evidence: `hpsv3-before.json`,
`hpsv3-invocations.jsonl`, `hpsv3-receipt.json`, prediction caches and `run.log`.
Baselines are retained intentionally for paired comparisons, not corpus copies.

```powershell
# Repeat this bounded command until the worker prints remaining=0; do not rescan.
.venv\Scripts\python.exe -m artcurator.cli score --out out/library --pass hpsv3 --max-new 768
.venv\Scripts\python.exe -m artcurator.cli cluster --out out/library
.venv\Scripts\python.exe tools/hpsv3_receipt.py --out out/library
.venv\Scripts\python.exe -m artcurator.cli report --out out/library
python tools/build_gallery.py --out out/library
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m artcurator.verify --out out/library --expected 1207
```

Use each corpus's actual `--input` for report provenance. Receipt CLI-wall
aggregation assumes its most recent N score commands are these HPS invocations;
generate the receipt before running unrelated scorer commands.

**Gallery contract:** no gallery code was changed. Its parser safely ignores
unknown raw columns, while updated consensus, disagreement, flags, family
champions and tiers flow through to the regenerated payload. Consequently raw
HPS mu/sigma are available in CSV/SQLite, **not displayed as new gallery cards**.
This limitation is distinct from column tolerance. The new test exercises the
actual extended CSV header through that unchanged parser.

Tests cover additive frozen order, five equal-weight means, sigma's single
variance contribution, negative-sigma rejection, constant-column guards, partial
run refusal and gallery tolerance. `artcurator.verify` independently recomputes
five-scorer consensus/uncertainty and hashes original corpus/reference files.
Final verification: **70 tests passed in 12.25 s**; focused Ruff `E9,F` checks,
syntax compilation and wheel build passed. Independent verification passed for
all three outputs, including SQLite integrity, finite scores, exact CSV order,
consensus/uncertainty math and unchanged SHA256 hashes for 1,924 / 4,405 / 1,165
corpus-plus-reference entries respectively (reference entries repeat by corpus).
LSP diagnostics are unavailable: basedpyright is not installed and installation
was previously declined. Runtime tests, focused lint, syntax checks and a wheel
build provide the available verification; this is not a claim of a clean LSP run.

Remaining risks: empty-prompt domain shift, int8 score drift, uncalibrated native
uncertainty, fixed-instruction safety bias, correlated scorers and Windows-specific
worker paths. The 85% cap and production memory measurements are specific to
this device/setup. Changing precision/revisions invalidates prediction namespaces
and requires complete rescoring before clustering. No commercial-use clearance
is implied; the HPS model card lists Apache-2.0, while the existing pipeline's
other component/model licenses still apply.
