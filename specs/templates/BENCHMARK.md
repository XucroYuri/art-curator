> 中文摘要
> 基准先固定语义、语料与测量边界，再采集数据。
> 冷暖缓存、加载成本和设备放置均需记录。
> 噪声结果记为无法判定，不能挑选有利样本。

# Benchmark evidence: <ID>

Requirement/AC: <IDs>; status: <proposed/verified/experimental>; evidence artifact and SHA-256: <path/digest>.
Model revisions/weight digests: <values>; S/E/run IDs: <values>; code/env/lock: <digests>.
Corpus/fixture: <ID, digest, rows/unique, strata and exclusions>; hardware/OS/driver/provider placement: <values>.

## Pre-registration
Scope/tiers: <values>. Hypothesis: <claim>. Baseline: <artifact>. Timing boundary: <load/decode/infer/persist/export>. Repetitions/order/warmup/cache control/confidence method: <plan>. Comparator: median≤1.10×, p95≤1.15×, peak≤1.10× and absolute admitted cap (NFR-GATE-007); additional budgets: <values>.

## Results
Raw sample artifact: <path/digest>. Median/p95/intervals: <values or TBD>. Host/device/browser peak and measurement source: <values>. Payload boundary: <raw JSON/gzip/base64/HTML>; no conflation. Exact-output/numeric/decision checks: <AC evidence>. Degradation and actual placement: <events>.

Verdict: <pass/fail/inconclusive>; confounders/limitations: <list>. Unmeasured cells: TBD/unqualified. INV-4 and NFR-OPT-001 apply to optimization claims; no missing safety evidence can be overridden by timing.
