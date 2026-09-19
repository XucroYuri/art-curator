> 中文摘要
> 认证只覆盖具名模型、执行配置、语料与设备。
> 数值、排序和决策边界分别验证，不能只看平均误差。
> 缺少证据或安全失败时不授予兼容性。

# Compatibility certificate: <ID>

Status: <proposed/verified/experimental/revoked>; owner/date: <values>.
Claim: <bounded equivalence/support>; S ID: <digest>; reference E and candidate E: <digests>; model/processor/calibration artifacts: <digests/licenses>.
Tier/device/provider scope: <explicit>; corpus/fixture/method: <IDs/digests>; limitations/excluded configurations: <list>.

## Predeclared comparison
Per-scorer `(a_m,r_m)`: <table>; BF16/INT8 explicit approval: <reference>. Embedding/rank/family/coverage budgets: <values>. Boundary ambiguity policy and completion proof: <artifact>. Reference outputs: <digest>.

## Evidence ledger
Requirement → AC → fixture → method/budget → artifact/digest → result: <rows for all affected gates>.
Reversibility/provenance/license vetoes: <pass or blocked>. Actual provider and resource peaks: <receipts>. Reviewer and expiry/retest triggers: <values>. Changed weights, preprocessing, provider/runtime or decision thresholds trigger scoped recertification, not inherited compatibility (FR-ARCH-001, NFR-GATE-003).
