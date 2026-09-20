# Art Curator

[简体中文](README.zh-CN.md) · [Design](DESIGN.md) · [Gallery tools](tools/README.md) · [Safe apply / undo](docs/apply.md)

A **fully local, zero-training, pure-vision image-library curation pipeline** and
an **offline review studio**. Turn a large image collection into explainable
review queues without uploading images or training a custom model.

Quality, identity-similarity and safety proposals use decoded pixels—not filenames,
prompts, EXIF, or embedded generation metadata. Paths select dataset roles and locate
files; hashes identify content, break ties and select deterministic audit samples.
Names remain available for human search, but never become model features.

**Human decisions stay in charge.** Model proposals are not deletion commands,
identity verification, or a safety certificate.

> Project source: **AGPL-3.0-only**. The inference stack is **not unrestricted for
> commercial use**: pyiqa uses **PolyForm Noncommercial**, and model weights have
> separate terms. Read [third-party licenses](THIRD_PARTY_LICENSES.md) before use.

![Offline review studio with synthetic placeholders only](docs/assets/studio.png)

## Architecture

```text
Read-only images → strict RGB decode → content-addressed manifest + thumbnails
                                      ↓
         SigLIP references + safety signal + four quality scorers
                                      ↓
 Eligibility gates → corpus-relative ranking → queue construction + abstention
                                      ↓
             scores.csv + families.json → offline review studio
                                      ↓
         Human decision journal (JSON/CSV; separate from model proposals)
```

- **Eligibility:** safety/identity routes take precedence; uncertainty, gaming
  suspicion and near-duplicate runner-up flags prevent an automatic queue proposal.
- **Relative ranking:** the default `five-means-v1` profile requires aesthetic v2.5,
  TOPIQ-IAA, TOPIQ-NR, Q-ReAlign and HPSv3 means, plus HPS sigma as uncertainty
  evidence. Means contribute equally after population z-normalization; zero
  variance is guarded. An explicit `four-means-v1` profile supports legacy runs
  without HPS; absence never selects it automatically. Missing required quality
  evidence makes cohort consensus/thresholds unavailable and widens abstention
  to review, not a surviving-scorer average. Per-signal reasons are exported in
  `flags`; safety/identity assessment routes retain precedence. These are
  within-corpus scores, not universal quality units.
- **Queue construction:** default queue threshold P90 plus safety, identity and
  family gates. P75+ or flagged items go to review; failing a queue gate abstains
  to review. Lower unflagged items are archive *candidates*, with an approximately
  5% deterministic hash-based audit sample promoted to review.
- **Families:** connected components from pHash/cosine comparisons; a champion and
  runner-up remain inspectable. Novelty is shown to humans without an invented gate.
  Snapshot IDs digest the grouping profile and sorted unique full member hashes;
  unrelated additions preserve existing IDs, while bridges/member changes do not.

## Requirements and quickstart

The full inference path targets **Python 3.12, Windows and an NVIDIA CUDA GPU**.
CUDA 12.8 wheels were used with an RTX 5060 Ti 16 GB. Linux CPU-only CI verifies
the gallery generator, not the GPU pipeline. There is no advertised CPU inference
fallback. Keep the checkout writable: output and cache paths must remain inside it.

From a new checkout, in PowerShell:

```powershell
$env:PYTHONUTF8='1'
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe torch==2.11.0 torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv\Scripts\python.exe transformers==4.57.6 pyiqa==0.1.15.post2 aesthetic-predictor-v2-5 ImageHash Pillow numpy PyYAML 'pydantic>=2' accelerate
uv pip install --python .venv\Scripts\python.exe --no-deps -e .
Copy-Item config.example.yaml config.yaml
```

**Edit `config.yaml` before running.** Replace all `/path/to/...` placeholders with
your local input, reference, posted-image and subject-root paths. This file is
gitignored. Keep outputs under `out/`; the example uses `out/library`.
The input/reference folder names are arbitrary. Own references must be nonempty.
Optional other-subject references currently use the legacy discovery glob
`*参考图集*` under sibling subject directories; without them, confusion margins are
empty. This convention selects a dataset role, not an image score.

Q-ReAlign uses a separate environment because its newer Transformers requirement
must not change the aesthetic scorer's main environment:

```powershell
uv venv --python 3.12 .venv-qrealign
uv pip install --python .venv-qrealign\Scripts\python.exe torch==2.11.0 torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv-qrealign\Scripts\python.exe pyiqa==0.1.16 transformers==5.17.0 'pydantic>=2' ImageHash
uv pip install --python .venv-qrealign\Scripts\python.exe --no-deps -e .
```

### Model downloads and first run

The first scoring pass downloads upstream weights over the network; **images are
not uploaded**. Models include SigLIP, aesthetic v2.5, TOPIQ-IAA/NR,
`Falconsai/nsfw_image_detection` and `q-future/Q-ReAlign-Mini-0.8B`. Q-ReAlign is
pinned to revision `fe1f45a7574c9e9d908875af9f7e90cb946aa19f`.
Hugging Face revisions are recorded on first resolution and weights/preprocessing
fingerprints key prediction caches. Shared weights live under
`out/library/cache/{huggingface,torch}`; per-run predictions stay in that run's cache.

```powershell
.venv\Scripts\python.exe -m artcurator.cli run-all --config config.yaml --out out/smoke --limit 12
.venv\Scripts\python.exe -m artcurator.cli run-all --config config.yaml --out out/library
.venv\Scripts\python.exe -m artcurator.cli previews --out out/library
.venv\Scripts\python.exe tools/build_gallery.py --out out/library
```

Once every required model/revision is cached, use `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` for disconnected inference. A missing cache is an error,
not a reason to send images to a service. The generated studio needs no network.

## Pipeline stages and CLI

| Command | Purpose |
|---|---|
| `scan` | Inventory/decode/hash PNG, JPG, JPEG and WebP; manifest and thumbnails |
| `score` | Pixel-only embeddings, reference signals, quality/safety scores and gaming audit |
| `cluster` | Relative consensus, duplicate families, flags and proposed tiers |
| `report` | Export frozen-column `scores.csv`, summary and provenance |
| `run-all` | Run scan → score → cluster → report (not previews or gallery) |
| `previews` | Read saved manifest; produce metadata-stripped, ≤1024px JPEG review assets |

Common options: `--input`, `--out`, `--config`, `--limit`. Scan/run-all inspect the
whole inventory before choosing SHA-sorted limited rows; other stages use the saved
manifest. `score --pass` accepts `siglip`, `aes_v25`, `topiq_iaa`, `topiq_nr`,
`qrealign`, `nsfw_prob`.

**Resume the same scoring command after interruption; do not rerun scan**, which
starts a fresh manifest. Then rerun cluster and report:

```powershell
.venv\Scripts\python.exe -m artcurator.cli score --out out/library --pass qrealign
.venv\Scripts\python.exe -m artcurator.cli cluster --out out/library
.venv\Scripts\python.exe -m artcurator.cli report --out out/library
```

Outputs include SQLite manifest, float16 embeddings, CSV scores, families, previews,
thumbnails, logs and caches. **All are private local outputs, not repository assets.**

## Offline review studio

The primary workspace has a **big preview, score inspector, six-action belt and
neighbor filmstrip**. UI labels are currently Chinese. Human decisions are stored
in browser `localStorage` under a corpus fingerprint, separately from `proposed_tier`.
The action journal exports JSON/CSV; export regularly because browser storage is
not a backup. It does not directly execute filesystem moves.

| Key | Action |
|---|---|
| `←` / `→`, `J` / `K` | Navigate |
| `1`–`6` | Select, approve queue, archive, confirm safety route, question identity, skip |
| `U` | Undo current image's manual action |
| Space / `F` / `?` | Fit/100% zoom, fullscreen, shortcut help |

The secondary **virtualized table** keeps all metrics, sorting, filtering, family
details and a metric legend. A short-key columnar payload is gzip/base64 embedded;
native **`DecompressionStream("gzip")`** decodes it. No framework, CDN or cloud API.
Use current Chrome/Edge; unsupported browsers show a blocking compatibility message.

![Synthetic audit table](docs/assets/table.png)
![Metric legend and caveats](docs/assets/legend.png)

Try the committed **60-row synthetic fixture**, with no model downloads or images:

```powershell
python tools/build_demo.py
python -m http.server 8765 --bind 127.0.0.1 --directory tests/fixtures/gallery
```

Open `http://127.0.0.1:8765/gallery.html`. Serve only the fixture directory, not the
repository/corpus. Real galleries may also open directly as local files; browser
policy can block original-file links when served over HTTP.

## Safety model

- **Read-only corpus during curation.** PNG ancillary metadata is stripped before
  decoding (pixel transparency retained). Strict retries do not fabricate pixels.
- Scoring writes are confined to the project at the Python audit-hook boundary;
  this is not an OS sandbox against malicious native code or concurrent mutation.
- **Dry-run by default:** standalone `artcurator.apply` creates a plan only.
  Explicit execution requires the stored plan, unchanged CSV digest and a confirmation token.
- Moves use **copy → fsync → verify both hashes → journal → unlink source**.
  Collision handling never overwrites an existing different file; undo uses a
  reverse ledger. Failed/partial copies remain for inspection.
- **Never delete as a curation decision.** Archive means a candidate lane, not
  destruction. Explicit moves/undo do unlink a verified redundant source copy;
  they are not literally “no unlink” operations. Keep independent backups.

See [apply/undo contracts and recovery limits](docs/apply.md). Never run competing
apply operations on the same corpus from different output directories.

## Measured performance

- A 300-image before/after run measured scan + thumbnail + manifest time of
  **50.048 s → 12.448 s (4.02×)** with eight workers. Safety inference was
  21.059 s → 17.694 s (1.19×), excluding model load/warmup.
- Gallery payload reductions observed across reports/fixtures are approximately
  **66–90%**, depending on data and whether gzip bytes or base64 transport bytes
  are compared. Earlier production comparisons were about 73% at the embedded
  payload boundary. This is not a promise of the same reduction in total HTML.
- Bounded CPU preparation overlaps single-GPU inference; virtual rows and bounded
  neighbor prefetch reduce browser work. No device-independent FPS guarantee.

These are historical measurements, not new benchmarks for every platform. The scan
comparison was one sequential pair with OS-cache confounders; private receipts and
corpus paths are intentionally excluded. See [methodology and limits](docs/pipeline/wave2.md).

## Limitations

- **No calibrated precision/recall without human labels.** Relative scores change
  when the corpus changes; percentiles are not probabilities of quality.
- **The NSFW classifier is not a safety certificate.** It can miss harmful content
  and falsely flag benign images. Similarity is not identity verification.
- Pretrained models still have training data and domain bias; “zero-training” means
  this workflow does not train/fine-tune them. Illustration domains may differ.
- The main environment pins Transformers because an upgrade changed aesthetic
  scores; there is no complete dependency lockfile. Verify numerical drift on upgrades.
- Q-ReAlign uses a Windows-style worker interpreter path; Linux GPU portability
  is not established. Reference kernels can be slower than optional GPU kernels.
- Family construction is quadratic, and connected-component endpoints need not
  meet the direct-pair threshold. Prefetch bounds object counts, not RAM bytes.
- Existing previews are skipped, even if externally corrupted. Rebuild affected
  assets deliberately. The shared model cache location is fixed under `out/library`.
- The minimal CI job tests only the stdlib gallery builder. It does not certify
  GPU inference, throughput, model licenses, or real-corpus move recovery.

## Development and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for the lightweight test command. Source code
is licensed under [GNU AGPL v3](LICENSE) (SPDX `AGPL-3.0-only`), without warranty.
Copyright © 2026 XucroYuri. Dependencies, weights and any images you process retain
their own rights; see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
