# Pipeline performance: bounded CPU overlap and review assets

This document describes implementation contracts and historical measurements.
Personal paths, corpus inventories, output hashes and private timing receipts are
not distributed. No production corpus was rerun to package this repository.

## Execution contracts

```yaml
workers: 8             # 1..12
prefetch_batches: 2    # 0..4; zero disables overlap
batch_size: 16
```

Scan runs hash/decode/pHash and thumbnail jobs through `ThreadPoolExecutor` with
submission bounded at `2 * workers`. Results are consumed in input order, then SHA
sorted. Only the caller writes SQLite/rejection records. `--limit` selects after
the entire corpus has been inventoried; it is not a fast inventory shortcut.
Duplicate content shares a thumbnail writer; truncated-hash collisions abort.

Reference inspection also uses workers. Greedy reference deduplication and score
reductions retain deterministic serial ordering. CPU preparation uses a single
producer plus a worker-sized decoder pool. All CUDA transfers and inference occur
on the caller; models are not run concurrently on the GPU. TOPIQ retains native
resolution and microbatch one, as does the isolated Q-ReAlign worker.

At most `prefetch_batches + 1` batches are submitted, including the active batch.
Errors propagate; early exit cancels pending work and joins running tasks. This
is an **object-count bound, not a RAM-byte bound**. Large native images can consume
substantial RAM; lower batch size/prefetch depth accordingly.

## Strict decoding

The decoder tries a fresh strict Pillow decode twice, then incremental
`ImageFile.Parser` in 64 KiB blocks. Every attempt strips PNG ancillary chunks
except pixel transparency before the decoder sees bytes. Truncated-image mode
is never enabled and placeholder pixels never enter scoring. Resource/bomb errors
are not downgraded into permissive reads.

Recovered retries log diagnostics; exhausted scan inspection/thumbnail failures
are recorded in `scan-rejected.json`. If no images survive, scan fails. Other
scoring/preview paths propagate persistent decode errors. A historically observed
transient broken-data-stream error has no confirmed root cause; retry success
alone does not identify one.

## Review assets

```powershell
.venv\Scripts\python.exe -m artcurator.cli previews --out out/library
.venv\Scripts\python.exe tools/build_gallery.py --out out/library
```

`previews` opens the saved SQLite manifest in read-only mode. Each distinct sha16
gets `previews/<sha16>.jpg`: RGB, longest side ≤1024, no upscaling, LANCZOS,
JPEG quality 88, no EXIF/ICC/source metadata. An adjacent temporary file is
atomically published. Existing destinations are skipped, not repaired.
Run only one preview job per output directory. Timing receipts stay private.

Physical preview count equals **unique content hashes**, not manifest file rows.
The studio resolves preview → thumbnail → explicit placeholder. Thumbnails remain
384px/quality 82. Viewing assets never feed scoring; opening originals is separate.

## Copy/verify overlap

Apply prepares bounded waves of independent copy/verify jobs. Worker threads never
unlink sources or write the disposition ledger. All workers join before the caller
commits/rolls back. Source-target dependencies and aliases force serial ordering;
undo remains serial. Failed waves can leave verified but uncommitted extra copies
alongside intact originals. These are retained for inspection, not silently deleted
or included in undo. See [apply.md](../apply.md).

## Historical measurements

Measured on Windows, 6 cores/12 CPU threads, approximately 32 GB RAM and one
RTX 5060 Ti 16 GB. A fixed 300-row saved-manifest slice was used in position/SHA
order. Fresh scan/thumb/prediction outputs prevented prediction-cache hits.
Safety inference used the same local Falconsai model revision, FP32 processor,
batch 16 and one equal-shaped warmup. Model load is excluded below.

| Stage / 300 images | Before (s) | After (s) | Speedup |
|---|---:|---:|---:|
| Scan + thumbnails + manifest | 50.048137 | 12.448021 | **4.02×** |
| Safety inference including decode/cache I/O | 21.059356 | 17.693579 | 1.19× |
| Sum of these stages | 71.107493 | 30.141600 | 2.36× |

Recorded comparisons showed equal scan rows and scores, with maximum score
difference 0.0 on this slice. This was **one sequential before/after pair**, not
randomized repetitions or controlled cold-cache testing. Model-load times were
81.93 s and 26.41 s: do not attribute this difference to prefetch; warmed weights
and OS caches confound it. Other GPU passes were not all re-benchmarked.

Gallery measurements across data shapes showed about **66–90% payload reduction**
for columnar gzip transport versus legacy row-object JSON; gzip bytes and base64
bytes are distinct boundaries. Prior larger reports showed approximately 73%
reduction at the embedded payload boundary. The generator prints raw JSON,
columnar JSON, gzip, base64 and HTML sizes so a new dataset can be measured
without confusing compressed payload size with total HTML size.

## Reproduction and testing

`tools/benchmark_pipeline.py before` and `after` label the implementation currently
installed; running both today does not recreate a historical unoptimized baseline.
The helper expects local runs named `out/library`, `out/review`, `out/similarity`
and cached model revisions. Its benchmark destinations must not already exist.
`tools/pipeline_receipt.py` checks those runs' previews and score digests.
All benchmark evidence remains ignored because manifests can expose local paths.

The wider tests cover ordered bounded work, prefetch overlap/error/early exit,
strict decoder recovery/truncation rejection, metadata-free previews and skip
semantics, duplicate content sharing, and copy-worker barriers. They use temporary
generated data. Minimal CI runs only `tests/test_build_gallery.py`, which needs no
NumPy, Pillow, torch, model downloads or CUDA.

Remaining limits include unconfirmed transient decode causes, count-bounded memory,
external corpus mutation during reads, cache-confounded single-run benchmarks,
retained speculative copies after move failure and stale existing previews.
