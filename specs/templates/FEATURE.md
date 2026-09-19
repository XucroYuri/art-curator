> 中文摘要
> 功能模板从用户触发条件与可观察结果开始。
> 每条要求附带范围、状态、测试夹具和证据。
> 未知预算先标明，不能以形容词代替验收。

# Feature: <name>

Status: <proposed/implemented/verified/experimental/deferred>. Owner: <name>. Dependencies: <IDs>. Current code/schema: <paths and gaps>. Non-goals: <list>.

## Requirement record (allocate ID on use)

ID: `<FR-domain-number>`
When <trigger>, the <system> shall <observable response>.
Scope: S:<semantic profiles> / E:<execution profiles> / T<tiers>.
Status: <status>; implementation/test links: <paths>.
AC: `<AC-requirement-ID-NN>`; method: <procedure>; fixture: <immutable ID + full digest>; comparator/budget: <predeclared values>; mandatory evidence: `<evidence/AC-ID.json>`.

## Design and release

Inputs/outputs and invalid policy: <contracts>. Provenance, rendering and licenses: <IDs>. Failure/abstention/undo: <behavior>. Semantic versus execution impact: <version changes>. Adversarial cases: <list>. Affected gates: <IDs>. Graduation/rollback: <evidence and revocation>. TBDs block qualification. This form inherits NFR-SPEC-001 and INV-4; placeholders are not allocated requirements.
