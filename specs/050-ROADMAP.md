> 中文摘要
> 顺序为身份 v2、策展协议、互操作，不并行扩大产品范围。
> 每阶段先满足安全与证据前置条件，再声明毕业。
> T3/T4 仅完成规范，当前单卡机器不能认证。

# Roadmap and qualification ledger

### FR-ROADMAP-001 — Evidence-gated graduation
When promoting a feature or resource profile, the maintainer shall complete its prerequisites and publish scoped graduation evidence before changing its status to verified.

Scope: S:* / E:* / T0–T4. Status: proposed.
- AC-FR-ROADMAP-001-01: audit CLAIMS-v1 milestone manifest; zero missing prerequisite/gate artifacts and zero T3/T4 certification based solely on the current single-GPU machine; evidence `evidence/AC-FR-ROADMAP-001-01.json`.

| Order | Work / status | Prerequisites | Graduation evidence |
|---|---|---|---|
| 0 | Contract foundations, proposed | INV review; immutable profile/snapshot registry; full-hash cache; worker isolation; budgets and durable recovery design | FR-STABLE/CACHE/WORKER/PERSIST ACs, completion-based degradation oracle, nine affected gates |
| 1 | Identity v2, proposed CPU-only | Licensed labelled crop/unknown/confusable fixture; fixed artifacts; per-model thresholds; reference protocol prototype | Parallel A/B against existing whole-image identity_sim; FR-IDENTITY ACs; visual/batch/device/license/resource gates; quality and coverage budgets declared first |
| 2 | Curation protocol, proposed | Stable identities and human naming events from phase 1; version registry; content binding and migration harness | FR-PROTOCOL ACs; unknown-version, truncation, stale-content and round-trip receipts; move gates before action authorization |
| 3 | Interop, deferred until phase 2 | Accepted sidecar protocol, declared target formats/licenses and loss matrix | FR-INTEROP ACs; synthetic bidirectional round trips, explicit lossy exports, no evidence pollution |

Resource qualification is orthogonal: T0/T1 CPU paths **specified, unqualified**; T2 historical single-GPU observations, **not certified** to these new contracts; T3/T4 **specified, unqualified**, require actual multi-device hardware, per-device contention tests and placement receipts. No automatic model roster change graduates a tier.

## Open decisions / TBD register

Scoped foundation repairs: the four code discrepancies recorded in
[the spec index](README.md#grounding-and-known-discrepancies) now have regression
coverage for conservative missing-signal abstention, refusal of SigLIP
substitution, fixed-member family digests and raw HPS inspection. Evidence is
[four-gap-regressions.json](evidence/four-gap-regressions.json). These repairs do
not graduate phase 0, any resource tier, or the nine qualification gates. No
inference/performance benchmark or corpus artifact regeneration was performed.

- Numerical budgets per scorer (including BF16/INT8), embedding/rank/family drift, identity precision/recall, target-confusable margins, gaming tolerance and usefulness/coverage floors need labelled evidence and pre-registration.
- Fixture content digests, release artifact storage/retention/access controls, evidence sign-off owner and certification expiry/revocation policy are TBD; unsigned hashes are integrity identifiers, not authentication.
- CPU identity latency/RAM targets, browser absolute memory/interaction ceilings, scratch/queue byte allocations and T0–T4 measured capacity are TBD/unqualified. Proposed tier caps are policy defaults, not measurements.
- Which crop model/artifact and clustering algorithm wins the CPU A/B? Is CCIP's intended distribution/use compatible with its exact OpenRAIL terms? Default to blocked distribution pending clearance.
- Which oriented/color-managed canonicalization profile supersedes legacy PNG ancillary stripping? It requires a semantic version and re-evaluation, not a decoder patch disguised as optimization.
- Which interop formats and application versions are first? XMP/JSON/CSV are candidates; Picasa/digiKam/Immich/PhotoPrism compatibility is not yet claimed.
- Historical payload boundary/digests and exact 1207/448 four-scorer receipts need reconciliation before stronger performance claims. There is no new benchmark run in this documentation delivery.
