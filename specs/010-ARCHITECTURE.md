> 中文摘要
> 语义、执行和运行身份分离，硬件档位不改变模型含义。
> 降级只能缩小批次或切换已认证执行配置，否则扩大弃权。
> 固定流水线由协调器持有状态，扩展不能直接移动文件。

# Architecture

## Actual module boundaries (informative)

`cli.py` exposes scan/score/cluster/report/run-all/previews; `run-all` does not build gallery or move files. `scan.py` hashes/strictly decodes; `models.py` adapts SigLIP/aesthetic/TOPIQ/NSFW; `cache.py` persists predictions; `references.py` derives identity/confusable/posted similarity. `score.py` invokes `qrealign_worker.py` and `hpsv3_worker.py` in isolated environments. `cluster.py` evaluates corpus-relative means, disagreement and connected components; `report.py` exports. `previews.py` makes viewing-only JPEGs; `tools/build_gallery.py` embeds offline data. `_moves.py`, `apply.py`, `undo.py` are separate mutation boundaries. `verify.py` and receipt tools audit results.

### FR-ARCH-001 — Three identities
When creating or resuming work, the coordinator shall bind a semantic profile, an execution profile and a distinct run identity without substituting a model automatically at any tier.

Scope: S:* / E:* / T0–T4. Status: proposed.
- Semantic profile: signal roster, immutable weights/text constants, canonical rendering and model preprocessing, grouping policy, thresholds/normalization, reference-set digest, uncertainty and decision policy; content-addressed semantic config digest. Changed corpus statistics are run-bound evidence, not silently comparable absolute scores.
- Execution profile: provider/device placement, precision/quantization artifact, runtime/build/lock digests, kernels, batching and scheduling. Same semantic intent is only a candidate for compatibility until certified; changed boundary behavior is not excused by the label “same semantics.”
- Run identity: unique invocation/resume lineage, snapshot digest, both profile IDs, seed/order, actual placement, tier, requested/completed/unavailable signals and degradation events. Resource tiers are scheduling hints, never semantic identities or quality rankings.
- AC-FR-ARCH-001-01: vary tier, provider and requested model on PROFILE-v1; no model substitution, all three identities independently inspectable, incompatible resume rejected and cross-profile comparison requires certification reference; evidence `evidence/AC-FR-ARCH-001-01.json`.

Implemented no-substitution subset: requested SigLIP load failures are recorded
in `signal_unavailable_siglip` metadata with requested model, resolved ledger
revision (null if unresolved), error type and reason, then re-raised. No alternate
variant is attempted. Successful retry removes stale unavailable metadata.
`report.py` exposes these records. Evidence:
[four-gap-regressions.json](evidence/four-gap-regressions.json), GAP-2. This is not
three-identity registry, provider-placement or resume-compatibility qualification.

### FR-ARCH-002 — Ordered coordinator pipeline
When executing a curation run, the coordinator shall enforce `snapshot → canonicalize/decode → infer → persist evidence → group/evaluate → review/export → plan → execute/undo` with explicit barriers and sole ownership of authoritative state.

Scope: S:* / E:* / T0–T4. Status: proposed.
- Snapshot binds full content hashes; source mutation invalidates evidence before consumption. Canonicalizer supplies tensors; adapters cannot interpret source paths as evidence. UI/export can inspect metadata without feeding it back into scoring.
- Inference plugins return versioned results only; move authority remains separate. No evaluation of incomplete committed batches; no plan reconstructed during execute. Human decisions never overwrite model proposals.
- AC-FR-ARCH-002-01: inject stage failure and changed source bytes on PROTOCOL-v1; assert zero downstream authorization before predecessor durable commit, zero scorer writes/moves and no changed-content cache reuse; evidence `evidence/AC-FR-ARCH-002-01.json`.

### FR-DEFER-001 — Complexity admission
When an extension requests infrastructure beyond the local architecture, the maintainer shall defer it until a recorded budget failure and a reviewed benchmark justify the added component.

Scope: S:* / E:* / T0–T4. Status: deferred (prohibition active for qualification).
- Do not build yet: distributed scheduler/service mesh/network GPU/multi-node DB; plugin marketplace/hot reload; universal tensor interchange/custom allocator; TensorRT/custom kernels without measured need; ANN/vector DB before exact blocked search exceeds budgets. Automatic model substitution and user-corpus adaptation remain prohibited, not future optimization options.
- Escalation: blocked exact grouping over budget → evaluate ANN with candidate-recall and downstream decision tests; single-node admission failing concurrent workloads → consider multi-node; single-file HTML exceeding measured browser budgets → segmented artifacts or an explicitly approved local service. Escalation grants investigation, not automatic adoption.
- AC-FR-DEFER-001-01: review PROFILE-v1 architecture-change manifest; reject additions lacking measured failure, alternative comparison and applicable gate evidence; evidence `evidence/AC-FR-DEFER-001-01.json`.

## Failure register and accepted limitations

Acceptance means disclosure, not a waiver of the linked rule. Mitigation qualification remains proposed.

| Failure / limitation | Required control / trace |
|---|---|
| Tier divergence makes corpora incomparable | Profile/run identity and no model substitution; FR-ARCH-001, FR-DEGRADE-001 |
| “Same semantics” hides boundary changes; ONNX average errors hide changed decisions | Pairwise/decision certification; NFR-NUM-001, NFR-GATE-003 |
| Cache poisoning or source changed after snapshot | Full hashes, provenance and invalidation; FR-CACHE-001 |
| Prefetch RAM blowout; provider fallback destroys performance | Byte admission, actual placement and measured fallback; NFR-RESOURCE-001, NFR-GATE-006 |
| Subprocess worker drift | Rejected handshake/result; FR-WORKER-001 |
| Graph bridges/corpus growth destabilize families | Content-set IDs do not promise stable membership; FR-STABLE-001 |
| Ledger/filesystem disagreement; undo versus later user edits | Reconciliation, preserve evidence, explicit conflict; INV-3, FR-PERSIST-001 |
| All-abstain safety versus usefulness | Preserve safety, publish coverage; FR-DEGRADE-001, FR-UX-001; useful-coverage target TBD |
| Benchmark gaming / favorable slices | Paired stratified repeated measures; NFR-GATE-007 |
| Offline HTML exceeds browser memory | Measure decompression+decoded image peak; FR-DEFER-001, NFR-DATA-001 |
| AGPL source mistaken for weight redistribution rights | Separate artifact license clearance; NFR-GATE-009 |

Existing union-find permits bridge-connected endpoints below direct similarity thresholds. Whole-image identity encodes background/clothing. Native HPS sigma and NSFW are not calibrated correctness/safety certificates. These limitations remain visible even after engineering gates pass.
