# WD candidates v2 and curated character memory

Requirements: FR-CANDIDATES-005/006/007 and FR-WD-001 in
`specs/features/FR-IDENTITY-CANDIDATES.md`. All recognition evidence is experimental.

## Local execution

The model is pre-provisioned at `out/zero-shot-candidates/model`. CPU and CUDA use
the isolated `.venv-wdtagger` interpreter; the main scoring environment is unchanged.
The measured environment uses `onnxruntime-gpu==1.24.4`, `numpy==2.5.3`,
`Pillow==12.3.0`, and Pydantic 2.13.5. CUDA 12/cuDNN 9 libraries may be provided by
an existing isolated GPU environment. ORT GPU 1.30 required CUDA 13 on this host;
it was replaced with 1.24.4 rather than claiming silent CPU fallback as GPU work.

```powershell
.venv\Scripts\python.exe -m artcurator.cli identity-tag --out out/library
.venv\Scripts\python.exe -m artcurator.cli identity-tag --out out/library --wd-provider CUDAExecutionProvider --wd-cuda-dlls .venv-identity/Lib/site-packages/torch/lib
.venv\Scripts\python.exe -m artcurator.cli identity-candidates --out out/library
```

Tagging uses saved JPEG face crops, not full-image model results copied to all faces.
The long-lived subprocess is polled at most every 60 seconds, with a 240-second
per-request deadline. Cache publication happens after each validated microbatch,
so an interrupted stage can resume. Output publication happens after the stage.
No hidden window flag is used. The model/tag digests, runtime, provider and
preprocessing identity are retained. CPU and CUDA cache entries are not interchangeable.

## Human decisions

Add `"mark":"baseline"` or `"mark":"variant"` to a normal confirm/new label
in the existing version-1 review-studio envelope, then run:

```powershell
.venv\Scripts\python.exe -m artcurator.cli identity-apply --out out/library --labels out/library/character_labels.json
.venv\Scripts\python.exe -m artcurator.cli character-memory --out out/library --memory-op list
.venv\Scripts\python.exe -m artcurator.cli character-memory --out out/library --memory-op rename --name Hero --target NewName
.venv\Scripts\python.exe -m artcurator.cli character-memory --out out/library --memory-op merge --name Alias --target NewName
.venv\Scripts\python.exe -m artcurator.cli character-memory --out out/library --memory-op export --memory-file out/library/memory-export.json
.venv\Scripts\python.exe -m artcurator.cli character-memory --out out/library --memory-op import --memory-file out/library/memory-export.json
.venv\Scripts\python.exe -m artcurator.cli character-memory --out out/library --memory-op delete --name NewName
```

Renaming adds an explicit alias; merging preserves visual references and reattributes
current assignments through new journal events. Deleting only deletes curated memory,
not images or the immutable WD vocabulary. Imports can include variant notes. Visual
IDs cannot transfer across corpora without corresponding saved embeddings. Exported
corpus/profile bindings prevent accidentally treating foreign face IDs as local support.

Memory similarity is maximum individual-reference cosine, but suggestion gates retain
the conservative centroid/individual-margin agreement rule. No confirmed references
means WD candidates can be present while **every suggestion remains null**. Baseline,
variant and ordinary assigned faces are equally eligible retrieval evidence; no learned
weights or automatic online training are introduced. Hair-color profiles are descriptive,
not identity gates. The three fixed buckets remain visible with the final other/new actions.

## Measurements and limits

On the same eight crops, inference batches took CPU **28.63 / 26.41 seconds** and
CUDA **1.283 / 0.692 seconds** (first/warm repeats). Warm rates are approximately
**3.30 s/crop CPU**, **0.0865 s/crop CUDA**; this tiny sample is not a universal speedup
claim. Model loads were 3.56 / 3.09 seconds. Full-corpus wall receipts include additional
initialization/first-use overhead, decode, hashing, IPC and serialization.

The three task snapshots contain 1,349 / 3,701 / 452 faces, with model-candidate
coverage 81.91% / 87.54% / 68.14%. Curated memory starts empty (zero invented labels),
therefore memory candidates and suggestions are zero. The named confusable appears
0 / 204 / 18 times. These are **tag occurrences, not false-positive rates**.

Private exact receipts: `wd-tagger.json`, `identity-candidates-report.json`, and
`wd-throughput.json` under the respective output directories. Public generic receipt:
`specs/evidence/wd-memory-integration.json`. Tight face crops cannot reproduce the
clothing evidence available to the supplied full-image probe. Numerical equivalence,
recognition accuracy, multi-file crash recovery and studio/UI behavior are not certified.
