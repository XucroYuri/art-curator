> 中文摘要
> 仅准入实测匹配的 CUDA FP32、批量 16 配置；FP16 推理仍不合格。
> 原定分量、余弦和决策预算不放宽；批量一致性与存储误差仍须通过。
> 额外严格 FP32 分量检查保留失败记录，但不作为本次准入阻断项。
> 数值准入不等于身份语义毕业；环境变化或决策漂移必须重新认证。

# ADR-0004 — GPU FP32 admission criterion

Status: accepted; date: 2026-09-20; owner: Art Curator maintainers.
Requirement and AC trace: FR-IDENTITY-001 / AC-FR-IDENTITY-001-02,
NFR-NUM-001 / AC-NFR-NUM-001-01 (scoped evidence only), NFR-SPEC-001.
Supersedes: the additional strict FP32 admission-blocker interpretation in the
identity-v2 experiment documentation; no primary budget or prior negative result.
Superseded-by: none.

## Context

The fixed-crop experiment compares 384 immutable crops (128 per corpus alias)
against fresh CPU FP32 vectors. CUDA FP16 inference failed the predeclared primary
cosine budget: maximum deviation approximately 1.25e-4 versus 1e-5. It remains
rejected, regardless of favorable timing or cluster ARI.

CUDA FP32 batch 16 passes the primary component/cosine budgets: maximum component
error 2.592802e-5 and maximum cosine deviation 1.600796e-8. All three samples have
ARI 1, zero probe flips, zero rank inversions outside ambiguity, and zero outlier
changes. Batch-versus-serial cosine deviation is at most 1.302e-13; FP16 storage
cosine deviation is at most 3.204e-8. The extra strict FP32 component diagnostic
fails for one sample and the pooled comparisons. Historical evidence retains
that failure; it is not rewritten as a pass.

CPU inference took 2239.409 seconds for 384 faces (5.831795 s/face). GPU FP32
measurements are approximately 0.10–0.118 s/face, about 53 times faster at the
representative 0.11 s/face rate. This is an engineering comparison, not a general
cold/warm performance qualification. Batch 16 is the measured selected profile.

## Decision and alternatives

Admit only measured `cuda / float32 / batch_size=16 / threads=4`, with exact
runtime, hardware, kernel, immutable weights and preprocessing matches. Under
AC-FR-IDENTITY-001-02 the issuer enforces the following conjunction:

1. **Unchanged primary budgets:** every normalized component satisfies
   `abs(candidate-reference) <= 1e-3 + 1e-3 * abs(reference)`; maximum per-face
   cosine deviation is at most `1e-5`; pairwise cosine error is at most `0.002`.
2. **Decision equivalence:** cluster ARI at least `0.99`, zero probe flips outside
   cutoff `0.85 ± 0.002`, zero rank inversions outside pairwise gap `0.004`, and
   zero outlier changes. Zero is stricter than the original 1% outlier allowance.
3. **Batch invariance:** batches 1/8/16/32 pass the same primary and decision checks
   against CPU; each sample's selected batch passes against GPU serial execution.
   Stored FP16 vectors are independently checked, not confused with FP16 inference.
   Missing required checks fail closed.

The additional `1e-5 + 1e-4 * abs(reference)` FP32 component check becomes a
**reported diagnostic, not an admission blocker**. NFR-NUM-001 describes these
precision-specific numbers as starting hypotheses, not universal certified
budgets. The scorer-specific primary budget was fixed before either candidate
ran and is unchanged. This is an explicit approved change of the additional
diagnostic's role after observing failure, not a claim that it passed or was
always nonblocking. Strict FP32 kernel equivalence remains uncertified.

High-dimensional FP32 reductions can differ with CPU/GPU accumulation order.
The supplied 2048-dimensional rationale gives the scale estimate
`2.59e-5 / 2048 ≈ 1.3e-8`; this is **not a measured component-relative error**
because 2048 is not a reference component magnitude. The saved SigLIP reference
matrix actually has shape **384 × 1152**, not 384 × 2048. Accumulation order is
a plausible explanation, not a proved kernel-level cause. Admission rests on
measured primary, angular, decision and batch checks, never on that heuristic.

Rejected alternatives:

- **FP16 inference:** violates primary budgets; speed cannot override failure.
  No relaxed budget or certificate is issued for it.
- **CPU-only:** avoids GPU roundoff but imposes roughly 53× inference cost despite
  passing the original numerical/decision contract. CPU remains the automatic
  fallback for absent/incompatible certificates.
- **Universal strict component gate:** preserves a stronger unachieved kernel
  claim but adds no observed decision protection on these samples. We narrow
  the claim rather than assert that stronger equivalence.

Semantic identity is unchanged: no detector, crop, model, route, legacy score or
threshold change. Execution/cache identities remain isolated. Certificate schema
version stays 1 (same fields and exact-match semantics); criterion identity is
ADR-0004 in the admission receipt. Other batches/runtimes are not auto-admitted.

## Consequences and evidence

Method: `tools/publish_identity_certificate.py` verifies evidence-chain hashes and
unchanged primary budgets, rechecks saved arrays without rerunning inference,
records strict diagnostics (including storage rank checks), and issues
`src/artcurator/identity-certification.json`. The certificate binds the original
FP32 evidence SHA-256; `out/identity-certification/admission-receipt.json` retains
complete evaluated measurements and array hashes. Synthetic admission regressions
are in `tests/test_identity_admission.py`; exact automatic fallback and model
compatibility are covered in `tests/test_identity_profiles.py`.

Private artifact manifest (paths relative to the project, SHA-256):

| Artifact under `out/identity-certification/` | SHA-256 |
|---|---|
| `predeclared-budgets.json` | `abcf236ba4ae15f6b12f56e2ac1dea245983fcb43bd193ddff5a41abd48c358f` |
| `fp32-predeclared-budgets.json` | `147397af1059b7a61b88acb1675b6a7a744b992447d89341b88069413dddc5c6` |
| `results.json` (rejected FP16, CPU timing) | `55b0e7cf0a86390bb41fce4f8a547023866f542aaf97a4a9f2819b814c6ddc49` |
| `fp32-results.json` | `f9d0c6a5e59f5342805a4841cd76fe2a58f8ba08546fde50c5066d83a7cf48c3` |
| `sample-manifest.json` | `4441b12db918b52280937dc14dbae1832be6691d1beae9ca7d4ee14ac030d0c4` |
| `cpu-fp32.npy` | `cc129fcc640c5c1fbbffa1c72a9c706f31104db3f572d9095ba2ae98cd57650b` |
| `gpu-fp32-b16.npy` | `97d58ef86272fa678d61e5fc01b23faec0708c39e5f8fdf3bf0ea7d6d90fd095` |

Acceptance scope: numerical admission on these fixed samples only, under
AC-FR-IDENTITY-001-02; the global NUMERIC-v1 gate and semantic graduation are not
declared verified. Corpus rerun evidence is `identity-gpu-run.json` per output
and `out/identity-certification/corpus-runs.json`; legacy artifact digests must
remain equal. A/B uses `leave-one-out-target-centroid-v1` and cannot authorize
replacement of whole-image `identity_sim`.

Revisit/revoke on any primary/decision/batch failure, changed evidence digest,
runtime/kernel/GPU/driver/weights/preprocessing change, or newly observed
out-of-ambiguity decision drift. A driver change requires manual requalification
because driver version is not currently an automatic profile key. Remove the
certificate to restore conservative automatic CPU placement; explicit CUDA
remains a disclosed experimental override. Never widen a primary budget after
seeing a failure. New semantic or numerical claims need predeclared comparators.

Limitations: three hash-selected samples are not labeled hard-negative coverage;
LOO removes self-inclusion but not full-corpus cluster-selection bias. Candidate
false-kill counts are human-review leads, not measured incumbent mistakes.
Allocator VRAM is not total-board usage. Resource-pressure, cross-driver,
concurrent-write, CCIP, and strict FP32 kernel equivalence remain unqualified.
