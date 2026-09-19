> 中文摘要
> 对抗审查主动寻找边界改变、来源丢失与恢复漏洞。
> 每个反例绑定夹具与可复现结果。
> 无法证实的假设保留为阻塞或明确限制。

# Adversarial review: <change>

Status/owner/date: <values>; scope S/E/tiers: <values>; model/corpus/method/evidence: <identities>. Requirements/ACs: <links>.

| Attack on claim | Fixture + digest | Method / comparator | Result + artifact | Resolution |
|---|---|---|---|---|
| Filename/metadata changes score | <VISUAL> | <exact pixels + numeric budget> | <TBD> | <owner> |
| Missing signal silently changes ensemble | <PROFILE> | <completion oracle> | <TBD> | <owner> |
| Quantized/exported average hides boundary flip | <NUMERIC> | <all pairs/decisions> | <TBD> | <owner> |
| Worker/cache stale identity | <PROTOCOL/HASH> | <zero accepted invalid results> | <TBD> | <owner> |
| Crash or user edit breaks undo | <MOVE> | <zero loss/overwrite> | <TBD> | <owner> |
| Favorable benchmark slice / hidden provider fallback | <BENCH> | <predeclared strata and caps> | <TBD> | <owner> |
| License/source conflated with weights | <LICENSE> | <per-artifact clearance> | <TBD> | <owner> |

Verdict: <block/accept scoped limitation/pass>. Open failures and linked AC changes: <list>. Numerical wins never override INV-3/INV-4 failures. This checklist instantiates 040 gates rather than replacing their acceptance criteria.
