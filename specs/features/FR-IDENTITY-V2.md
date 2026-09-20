> 中文摘要
> 身份 v2 采用固定权重与人工确认参考，不训练用户图库。
> 动漫人脸、未知桶和易混淆边界以 CPU/GPU 双轨实验验证。
> 在证据充分前保留现有整图 SigLIP，不自动替换。

# Identity v2

Current: `references.py` deduplicates references greedily at pHash≤4, derives whole-image SigLIP cosine `identity_sim`, confusable margin and posted novelty. Background/clothing/composition can dominate. `config.example.yaml` uses identity route/queue quantiles 0.10/0.20, margin 0.05. Review summary has 65 own references, zero confusable references: it cannot validate confusion rejection.

### FR-IDENTITY-001 — Fixed-weight execution-profile identity experiment
When evaluating character identity v2, the pipeline shall run a fixed-weight crop/reference candidate under an explicit CPU or GPU execution profile alongside existing whole-image SigLIP identity_sim and retain the incumbent until predeclared A/B graduation criteria pass.

Scope: S: identity-v2 candidate versus legacy identity / E: CPU FP32 or explicitly selected CUDA FP32/FP16 profiles / T0–T1 CPU, T2 single GPU; T3–T4 unqualified. Status: implemented experiment; semantic graduation remains unqualified.
- `identity.device=auto|cpu|cuda` defaults to auto. Auto admits CUDA only against a matching numerical certificate; explicit CUDA permits a disclosed experiment, never a CPU fallback. CPU remains the low-end lane. Whole corpora are re-embedded on profile changes: cache identity includes device, precision, runtime/kernel/batch, immutable model revision, preprocessing and full crop digest. Embeddings from different executions are never mixed.
- Execution change does not change detection/crop semantic identity. A/B target scores use leave-one-out centroids, omitting the query face itself; singleton/zero-norm targets are unavailable, not zero. Image aggregation remains maximum available face cosine. LOO removes direct self-inclusion, not full-corpus cluster-selection bias.
- AC-FR-IDENTITY-001-02: test isolated cache namespaces, CPU fallback, explicit unavailable CUDA, cached crop resume, ragged batches and synthetic LOO edge cases in `tests/test_identity_profiles.py`; measure 128 fixed crops per corpus and batches 1/8/16/32 under predeclared NFR-NUM-001 budgets. Evidence/method and the exact scope of numerical versus downstream compatibility are recorded in `docs/pipeline/identity-v2.md`; no incumbent route changes are authorized.
- Scoped numerical admission follows [ADR-0004](../adr/ADR-0004-gpu-fp32-admission-criterion.md): only measured CUDA FP32 batch 16, four threads, and exact execution/model/preprocessing matches. Primary component atol/rtol 1e-3, cosine deviation 1e-5 and pairwise error 0.002 are unchanged; require ARI ≥0.99, zero probe/rank changes outside declared ambiguity, zero outlier changes and batch/storage equivalence. The additional strict FP32 component check remains a reported diagnostic, not an admission blocker. Evidence manifest and limitations are in the ADR; regression coverage adds `tests/test_identity_admission.py`. This does not graduate the semantics or the global numerical gate.
- Detection candidate: `deepghs/anime_face_detection` ONNX v1.4, MIT; immutable artifact digest still TBD. License-clean fallback candidate YuNet MIT + SFace Apache-2.0 is an explicitly selected separate profile, not an automatic substitute.
- Character representation: CCIP with exact OpenRAIL restrictions assessed; WD-v3 Apache-2.0 taggers for closed-set character labels, not universal identity truth. Package license never replaces artifact review.
- Clustering candidates: HDBSCAN BSD-3, Chinese Whispers MIT, or DBSCAN with **per-model calibrated** distance/core-point thresholds. Immich's minFaces=3 and PhotoPrism's sface 0.72 are comparators, not copied defaults. Unknown/outlier bucket and minimum core-support gate prevent forced identity assignment.
- Target-versus-confusable margin is calibrated on labelled hard negatives; unknown identities do not get routed to the nearest named character by default. Cropping/rendering and threshold changes version semantics.
- AC-FR-IDENTITY-001-01: parallel paired CPU A/B on ID-SYN-v1 across anime styles, occlusion, multiple faces, no-face, confusables and unknowns; report detection coverage, false merges/splits, unknown rejection, precision/recall, margin and latency/RAM; per-slice budgets and digests TBD **before** execution; no switch while unqualified; evidence `evidence/AC-FR-IDENTITY-001-01.json`.

### FR-IDENTITY-002 — Human naming without training
When a user names, confirms, rejects, merges, splits or hides an identity suggestion, the review system shall append a reversible provenance-bound event and accumulate only confirmed references without changing model weights.

Scope: S: identity-v2 naming / E: CPU/GPU fixed-weight profiles / T0–T4. Status: naming/pinning prototype implemented; full undo/merge/split qualification remains proposed.
- Workflow: Unknown → named suggestion → Unconfirmed → Confirm/Reject. Uncertainty-first “active-learning” queue means **human review prioritization**, not optimizer training. Conflicting labels remain reviewable; hidden clusters remain recoverable. Confirmation records bind actor-local ID, content/crop hash, profile, event lineage and reference-set version.
- Bad-match reports can propose a new calibrated threshold profile, never silently adapt the current one. Weight-training “rebuild training data” behavior from digiKam is explicitly out of scope; rebuilding derived references is permitted with identical weights.
- AC-FR-IDENTITY-002-01: repeat/undo conflicting naming and merge/split sessions on ID-SYN-v1; exact event replay, no unconfirmed references admitted, byte-identical weights and explicit reference-version changes; evidence `evidence/AC-FR-IDENTITY-002-01.json`.

Dependencies: INV-1/2/4, FR-STABLE-001, FR-CACHE-001, FR-PROTOCOL-001, NFR-GATE-009. Protocol prototype supports phase 1; general protocol graduation remains phase 2. No identity-verification or commercial clearance claim is made.
