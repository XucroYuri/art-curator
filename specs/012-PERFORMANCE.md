> 中文摘要
> 历史实测与未来预算分开记录，未知项明确标注。
> 内存准入按实际可用容量计算，队列同时限制字节与条目。
> 性能优化不能改变语义，离开 Python 必须有端到端收益证据。

# Performance and resource profiles

## Historical measurements, not certification

Machine: Windows, 6 cores/12 threads, approximately 32 GB RAM, RTX 5060 Ti 16 GB; HPS record driver 610.88. Evidence: `docs/pipeline/wave2.md`, `docs/pipeline/hpsv3.md`, `out/review/summary.md`. Private receipts are referenced, not reproduced. Models/revisions below bind these observations; missing source receipts/digests remain unqualified under INV-4.

| Boundary | Historical value | Method / limitation |
|---|---|---|
| Review scan | 0.09513 s/img | 350.843 s / 3688 rows, earlier single-thread run |
| 300-row paired scan+thumb+manifest | 50.048137 → 12.448021 s; 4.02× | workers=8 after; 0.16683 → 0.04149 s/img; one sequential pair with OS-cache confounding |
| SigLIP / aes_v25 | ≈0.13 / ≈0.12 s/img | review 0.12938 / 0.12002; inference includes decode/cache I/O, load separate |
| TOPIQ-IAA / TOPIQ-NR / NSFW | ≈0.15 / ≈0.15 / ≈0.11 s/img | native TOPIQ microbatch 1; review 0.14561 / 0.14665 / 0.11114 |
| Q-ReAlign | ≈0.65–0.77 s/img | isolated venv; 0.64872 sampled review progress; resumed tail 0.03110 is NOT fresh inference cost |
| HPSv3 8-bit | ≈0.84–0.95 s/img | 0.84073 / 0.87352 / 0.95477 by corpus; isolated venv, batch 1, load excluded |
| HPS peak | 9.69 GiB allocated / 10.97 GiB reserved | PyTorch peaks, not total-board VRAM; loading included; 16 GB card |
| Four-scorer wall | 1207: 17m54s; 3688: 1h50m45s; 448: 26m08s | historical supplied baseline; review summary confirms 6645.377 s; other exact receipt digests TBD |
| Five-scorer re-tier | 154 / 429 / 19 rows changed | same three corpora; not improved-quality counts |
| Review workload after HPS | ≈22% / ≈22% / ≈11% | 272/1207, 813/3688, 48/448; excludes additional routed assessments |
| Review payload | 1274.7→429.4 KB (−66%); 3693.3→1052.9 KB (−71%); fixture −89.5% | supplied historical payload figures; exact gzip/base64 boundary and receipt digests TBD; not total HTML reduction |
| Virtual table | ~20 mounted DOM rows for 3688 rows | observed viewport, not all viewport guarantee; DESIGN allows roughly 48 |
| Tests | 70 passed in 12.25 s | historical `docs/pipeline/hpsv3.md`; not rerun by these specs |

**Correction:** 0.09513→0.04149 is approximately 2.29× across different runs, not the paired 4.02× experiment. A dense 10,000×1,152 FP16 matrix is 23,040,000 bytes ≈23.0 MB (21.97 MiB). Any “~15 MB” claim can only describe a compressed/other representation with a named artifact, not that dense matrix. A 100,000² FP32 similarity matrix is 40,000,000,000 bytes ≈40 GB before overhead.

### Historical identity ledger

| Signal | Revision / execution context |
|---|---|
| SigLIP | `google/siglip-so400m-patch14-384@9fdffc58afc957d1a03a25b10dba0329ab15c2a3`; official BF16 normalized |
| aes_v25 | same backbone revision; head SHA-256 `a6caf256b3dc434273c98dcb12f6bf17c5d4fc647d8df11f038386923dd06220`; official BF16 |
| TOPIQ-IAA | pyiqa 0.1.15.post2; weight `393b41b49c41bf0ffa43ab7e13b26f374e211085f5fe2eba3408e89c8b67f935`; FP32 native |
| TOPIQ-NR | pyiqa 0.1.15.post2; weight `9a73138beb3748dd6a83365610ac88fa1cd53225342c77fc9ed44a3be461354c`; FP32 native |
| Q-ReAlign | `q-future/Q-ReAlign-Mini-0.8B@fe1f45a7574c9e9d908875af9f7e90cb946aa19f`; pyiqa 0.1.16, Transformers 5.17.0 |
| NSFW | `Falconsai/nsfw_image_detection@96cb0d0342c7afb80cab76ecc58b265fa44da256`; FP32 softmax |
| HPSv3 | `MizzenAI/HPSv3@4f81e3e09edd82fe3c5f636444c721b592a735ca`; processor `eed13092ef92e448dd6875b2a00151bd3f7db0ac`; Transformers 4.45.2, SDPA, LLM.int8, BF16 vision, FP32 reward head, exp-sigma |

Main Transformers 4.57.6; dependency inventories in `environment-versions.json` are not a reproducible lock certificate. Full preprocessing strings are in the review summary, lines 159–170. HPS single-image BF16→INT8 mu drift +0.144258 is a warning, not an accepted tolerance.

### NFR-RESOURCE-001 — Admission and tier defaults
When admitting a run or allocating another batch, the scheduler shall reserve host and per-device GPU budgets from current available memory and reject or degrade work that cannot fit its estimated peak.

Scope: S:* / E:* / T0–T4. Status: proposed; all tier qualifications TBD, T3/T4 **specified, unqualified** on this single-GPU machine.

| Tier | Resource intent (not model roster) | Proposed host tier cap | Default batch / prefetch batches / shared CPU threads |
|---|---|---:|---|
| T0 | Small CPU-only / identity v2 candidate | 4 GiB | 1 / 0 / 1 |
| T1 | Larger CPU-only workstation | 8 GiB | 4 / 1 / 4 |
| T2 | Single accelerator workstation | 20 GiB | 16 / 2 / 8 |
| T3 | Large single-node multi-device | 48 GiB | 16 per admitted device / 2 / 12 total |
| T4 | High-memory multi-device single node | 96 GiB | 32 per admitted device / 2 / 16 total |

- Host cap = `min(tier cap, 0.65 × physical RAM, 0.75 × available RAM)`; GPU cap **per device** = `min(0.80 × VRAM_total, 0.85 × available VRAM)`. No summing fragmented devices into a fictitious fit. T0/T1 allocate no GPU. Defaults are proposed ceilings, not measured capability; scorer manifests can demand smaller batches (TOPIQ/Q-ReAlign/HPS currently 1).
- Peak memory = **models + runtime + activations + decode + queues + cache + transients**. Reservations include loading, decompression and non-framework/device overhead, with measured estimates before qualification. Explicit byte and item queue limits derive from remaining admitted budget; unknown estimates fail admission, not optimistic allocation.
- AC-NFR-RESOURCE-001-01: replay RESOURCE-v1 pressure/load/decode cases and external contention; sampled peak and reservations stay within both caps, no paging-dependent fit, shared thread count within admitted total; evidence `evidence/AC-NFR-RESOURCE-001-01.json`. Absolute per-profile browser/CPU scratch ceilings and all unmeasured tiers: TBD before admission certification.

Scoped implementation: `resources.py` applies these formulas and records chosen
caps. Decode estimates include source staging, pixel/tensor copies and fixed
scratch; reservations occur before decoding and release on consumption/error.
Queue cap is at most 512 MiB and one quarter of admitted host memory. Inference
prefetch is reduced to zero rather than speculating about overlapping peaks.
Scan/thumbnail/preview paths share byte reservations within each stage. Deferrals
and peak reserved bytes are persisted as run metadata and exposed in the report.
GPU allocator ceilings are applied before scorer loading, independently per GPU.
This is reservation-accounting coverage, **not** measured whole-process/board
memory qualification: model/runtime/activation/loading estimates, contention,
shared multi-process reservations and dynamic re-admission remain open.
Tests: `tests/test_architecture_resources.py`; evidence
[architecture-gap-regressions.json](evidence/architecture-gap-regressions.json), GAP-C.
`NFR-MEM-002` is not allocated in this tree; do not silently invent an alias.

### NFR-DATA-001 — Data-oriented hot paths
When processing corpus-scale evidence, the pipeline shall use bounded typed data paths with explicit ownership rather than unbounded object graphs or quadratic scratch matrices.

Scope: S:* / E:* / T0–T4. Status: proposed.
- Contiguous typed columns; one versioned FP16 embedding matrix reused across grouping/evaluation; blocked exact similarity with bounded scratch, never unrestricted N×N materialization. Loss of FP16 precision remains governed by NFR-NUM-001.
- Byte-and-item bounded queues, owner/lifetime for each buffer and cancellation release; one shared CPU thread budget across decoders, inference workers, BLAS/runtime pools and subprocesses. Batched evidence persistence but independently durable move records. Long-lived workers use batched requests without state leakage.
- Browser peak includes base64 text, compressed bytes, decoded columns, UI indices and decoded images; smaller transport does not prove smaller peak memory.
- AC-NFR-DATA-001-01: instrument allocations/thread counts/buffer lifetimes on RESOURCE-v1 and synthetic 10k/100k embeddings; zero unrestricted N×N allocations, bounded scratch/queues, one reusable matrix per version, no leaks after cancellation and move durability unchanged; evidence `evidence/AC-NFR-DATA-001-01.json`.

### NFR-OPT-001 — Leave-Python threshold
When proposing a native component for a hot loop, the maintainer shall require that loop to exceed 15% of representative wall time and the candidate to demonstrate at least 10% end-to-end improvement without semantic or safety regression.

Scope: S:* / E: optimized versus reference / T0–T4. Status: proposed.
- No “SIMD via Python loops” or `numpy.vectorize` performance claims; vectorized native operations need measured end-to-end evidence too. Include FFI/copy/startup costs, not just kernel speed.
- AC-NFR-OPT-001-01: profile and paired repeated benchmark BENCH-v1 with fixed corpus/model/output; accept only >15% hotspot and ≥10% end-to-end gain plus passing affected gates; evidence `evidence/AC-NFR-OPT-001-01.json`.
