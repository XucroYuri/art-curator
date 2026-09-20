# Offline Art Curator Gallery

`build_gallery.py` turns one pipeline output directory into a single static
`gallery.html`. The report embeds a short-key columnar payload compressed with
gzip and base64, then uses native `DecompressionStream` plus inline CSS and
vanilla JavaScript. It opens directly from `file://` with no framework, CDN,
external font, fetch, or XHR. Chrome/Edge are required for the native decoder.

## Usage

From the repository root:

```powershell
python tools\build_gallery.py --out out\library
python tools\build_gallery.py --out out\library --title "图片审计台" --subtitle "本地图片库 · 只读审计（离线可用）"
Start-Process (Resolve-Path out\library\gallery.html)
```

The same command against the checked-in synthetic demo is:

```powershell
python tools\build_demo.py
python -m http.server 8765 --bind 127.0.0.1 --directory tests/fixtures/gallery
```

## Input contract

The output directory must contain `scores.csv` and may contain
`families.json`. The generator accepts both the legacy header and the new
header with optional `qrealign` immediately after `topiq_nr`; extra or missing
columns are ignored safely. `thumb_rel` is normalized from Windows
backslashes to browser-friendly `/` separators. Empty numeric cells become
`null`; invalid non-empty numeric cells fail the command with a line number.

When `families.json` is absent, family membership is derived from the CSV
`family_id` column. Optional champion/runner-up labels remain unset in that
case. Missing or empty thumbnails render an explicit placeholder tile, and
missing referenced files switch to a `MISSING` placeholder in the browser.

The optional `identities.json` artifact adds the face/character layer without
changing the image ledger. Its `detector`, `embedder`, `clustering`, `images`,
`faces` and `clusters` fields follow the producer contract; omitted fields get
safe browser defaults, while unknown fields are carried through the compressed
payload. `characters.json`, when present, is read-only catalog metadata. If
`identities.json` is absent, face boxes, character controls and the character
drawer remain hidden.

The optional reference-grouping bundle is enabled only when
`character-groups.json` exists. The builder also reads
`character-groups-by-image.csv` (`sha16,filename,characters`) and
`character-groups-by-character.csv`
(`character,sha16,filename,face_id,sim,margin,decision`). Missing fields and
files use empty defaults; unknown JSON and CSV fields remain in the compressed
payload. The `人物分组` tab derives its image counts from the image CSV joined to
the score ledger, so cards and filters reconcile with the table. Empty roles and
abstained/fallback roles appear in the `未定` backlog.

The header's **Archive pass** is deliberately defined as
`archive_candidate / total`; `review` remains an audit lane rather than a pass.
This resolves the otherwise ambiguous `pass-rate` label without changing the
pipeline contract.

## Report navigation model

The generated report is a full-screen `100dvh` app shell rather than a centered
document. The primary `审查工作台` keeps a large image-first preview, all score
cards, flags, family state, the pipeline proposal, a distinct persisted
`manual_decision`, original-file and copy-path actions, a six-action belt,
neighbor filmstrip, progress, and keyboard help. `← →` / `J K` navigate,
`1–6` apply decisions, `U` undoes, Space toggles fit/100% zoom, `F` toggles
fullscreen, and `?` opens the shortcut dialog. The secondary `审计表格` keeps
all columns and spotlights while rendering only a bounded row window.

When grouping data is present, the third `人物分组` tab shows one card per
known character plus `未定`, threshold provenance (`min_sim` and `min_margin`),
and the experimental/uncalibrated retrieval disclaimer. Selecting a card sets
the shared table filter and studio navigation queue. `仅看未定` and `开始命名
未定人脸` enter the existing face naming, journal, and `character_labels.json`
export loop. Preview badges use the image CSV's multi-character set; face boxes
use by-character assignments with similarity, margin, and decision in the
tooltip, falling back to cluster ID for abstentions. The source note is explicit:
folder names are human-supplied labels and per-image decisions use pixels only.

The controls row keeps search, disposition cards, flag chips, removable active
filters, `清除筛选`, `仅看未审`, the global `显示 NSFW` toggle, and `指标说明`
within reach. At 900px and wider, the inspector reserves a right rail; below
900px it becomes a vertical review section inside the named main scroll owner.
The table owns its vertical and horizontal scrolling, so narrow screens do not
create page-level horizontal overflow.

The visible UI labels are intentionally Chinese:

- Dispositions: `入队候选`, `人工复核`, `归档候选`, `NSFW 复核`, `身份复核`.
- Flags: `评分分歧`, `刷分嫌疑`, `NSFW`, `身份低分`, `家族备选`, `审计抽样`.
- Columns: `缩略图`, `文件名`, `家族`, `美学 v2.5`, `TOPIQ-IAA`, `TOPIQ-NR`,
  optional `Q-ReAlign`,
  `NSFW 概率`, `身份相似度`, `新颖度`, `共识 Z`, `分歧度`, `刷分差值`,
  `标记`, `处置`.

Disposition cards filter the ledger by `proposed_tier`; flag chips can be
combined and removed individually. Search covers filename, `sha16`, and
`family_id`. Sortable headers expose visible `▲`/`▼` indicators and
`aria-sort`. NSFW rows (`nsfw_prob >= 0.65` or `route_nsfw`) blur previews until
`点击显示`. Row/file-name clicks open all 22 raw fields, copy actions for
`sha16`/`abs_path`, and the original `file://` link. Family IDs open the member
strip with singleton, champion, and runner-up states. The three collapsible
spotlights (`分歧焦点`, `刷分审计`, `不确定队列`) jump back to the matching row.
`指标说明` documents direction and caveats for every metric; `Q-ReAlign` is
shown only when the CSV column exists, and proposals remain explicitly
uncalibrated. Unknown flags remain visible as neutral badges using their raw
values. `审计抽样` means a random low-tier sample for finding missed good
images, not a defect marker.

Manual decisions and an action journal are stored in `localStorage` under the
embedded corpus fingerprint. The `动作日志` panel exports both JSON and CSV;
these files are intended to become future human labels. NSFW items remain
blurred until per-item reveal or the global toggle is enabled.

With identity metadata, the preview draws source-pixel face boxes over the
same rendered image rectangle used by `object-fit: contain`; 100% zoom and
pan use the transformed image bounding rectangle, so boxes stay aligned. Face
buttons open a Chinese naming popover, expose `N` / `Esc` / `Tab` keyboard
flows, and show confirmed chips. The character drawer virtualizes cluster
cards, lazy-loads representative crops with four concurrent loads, sorts
clusters by size, and offers naming, merge, split and outlier decisions. The
`待确认优先` toggle orders faces by low cluster probability, margin near zero,
singleton status and low detection score. Exporting人物标签 always downloads
the exact `character_labels.json` envelope consumed by `identity-apply`:

```json
{"version":1,"source":"review-studio","corpus_fingerprint":"…","labels":[{"face_id":"f_000001","image_sha16":"…","character":"name","action":"confirm"}]}
```

The allowed face actions are `confirm`, `new`, `ignore` and `wrong_box`.
Importing the same envelope restores the current face-label state; merge,
split and outlier decisions remain reversible journal events for the pipeline.

## Performance contract

The generator prints and embeds the legacy JSON size, columnar JSON size,
gzip/base64 size, row count, HTML size, and corpus fingerprint. The current
reports are 73% smaller at the payload boundary than their legacy JSON data
(`1207` rows: roughly `1.24 MB` → `331 KB`; `3688` rows: roughly `3.71 MB` →
`970 KB`). The table uses precomputed sort keys, one delegated table handler,
`DocumentFragment` batches, rAF scheduling, sticky headers, `contain`, and
bounded virtual rows. Preview assets are resolved as
`previews/<sha16>.jpg` → `thumbs/<sha16>.jpg` → placeholder when those files
exist; the generator records asset availability so missing candidates do not
create noisy 404 console errors. Six neighbors are prefetched with a four-item
concurrency cap, `Image.decode()`, stale-generation cancellation, and idle
viewport warmup.

## Synthetic fixture

`tests/fixtures/gallery/scores.csv` contains 60 synthetic rows covering every tier and
flag, empty optional numeric cells, a filename containing quotes/CJK and a
literal `</script>` sentinel, mostly empty `thumb_rel` values, and two
nonexistent thumbnail paths. The fixture intentionally has no `families.json`
so the CSV family-derivation path is exercised.

All fixture source paths are non-existent `/synthetic/...` placeholders. No real
thumbnails or source images are included. Open `http://127.0.0.1:8765/gallery.html`
after starting the loopback-only read-only server above.
`build_demo.py` uses relative provenance; the production builder intentionally
embeds local paths, so do not publish a generated production gallery.

## Local verification helpers

- `check_aesthetic_upgrade.py`: compare eight cached `out/library` aesthetic
  scores with fresh GPU inference before accepting a dependency upgrade.
- `benchmark_pipeline.py`: compare installed implementations using three local
  output names (`library`, `review`, `similarity`); see the [methodology](../docs/pipeline/wave2.md).
- `pipeline_receipt.py`: verify those outputs' score hashes and preview assets.
- `conservative_receipt.py`: derive local run intervals and image inventory
  evidence for `out/library` and `out/review`. It expects a report-completion log.
- `python -m artcurator.receipt`: record versions and run intervals for `out/library`.

Helpers require local outputs; no captured production receipts ship here. Review
their assumptions before use. They are not needed for the synthetic demo or CI.
