> 中文摘要
> 离线审阅采用列式短键数据、gzip 与浏览器原生解压。
> 表格虚拟化减少节点，但压缩体积不等于内存峰值。
> 不支持解压的浏览器明确阻塞，而非隐式联网回退。

# ADR-0003 — Columnar gzip offline payload

Status: accepted, retrospective. Trace: NFR-DATA-001, NFR-UX-001, FR-UX-001; no new normative requirement.

## Context and decision

`tools/build_gallery.py` builds payload v4 from short-key columns, gzip and base64; native `DecompressionStream("gzip")` reconstructs data. It retains offline single-file review without framework/CDN/fetch dependencies and virtualizes the table. `tests/test_build_gallery.py` checks compact payload and decoder/virtualization contracts; these string/data checks are not full browser QA.

Sources: `README.md` offline studio section, `DESIGN.md` performance contract, `docs/pipeline/wave2.md`. Historical transport reductions span about 66–90%; 012 preserves supplied absolute figures and boundary uncertainty. Current HPS raw columns are ignored by gallery even though consensus/disagreement include HPS.

## Alternatives and consequences

Rejected legacy row-object duplication and a required hosted application. Costs: modern browser dependency and simultaneous compressed/decoded representations; a single HTML artifact still has a memory ceiling. Compatibility error is explicit rather than a network decoder fallback. Native JSON/CSV remains the evidence escape hatch.

Future acceptance: AC-NFR-UX-001-01 covers real-browser offline/accessibility behavior; AC-NFR-DATA-001-01 measures memory; AC-FR-UX-001-01 covers raw-signal visibility. Exceeding browser budgets invokes FR-DEFER-001 segmented-artifact/local-service review, not an assumed unbounded HTML solution.
