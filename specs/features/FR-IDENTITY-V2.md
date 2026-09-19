> 中文摘要
> 身份 v2 采用固定权重与人工确认参考，不训练用户图库。
> 动漫人脸、未知桶和易混淆边界以 CPU 双轨实验验证。
> 在证据充分前保留现有整图 SigLIP，不自动替换。

# Identity v2

Current: `references.py` deduplicates references greedily at pHash≤4, derives whole-image SigLIP cosine `identity_sim`, confusable margin and posted novelty. Background/clothing/composition can dominate. `config.example.yaml` uses identity route/queue quantiles 0.10/0.20, margin 0.05. Review summary has 65 own references, zero confusable references: it cannot validate confusion rejection.

### FR-IDENTITY-001 — Fixed-weight CPU identity experiment
When evaluating character identity v2, the pipeline shall run a CPU-only crop/reference candidate alongside existing whole-image SigLIP identity_sim and retain the incumbent until predeclared A/B graduation criteria pass.

Scope: S: identity-v2 candidate versus legacy identity / E: explicit CPU profiles / T0–T1, CPU lane on T2–T4. Status: proposed.
- Detection candidate: `deepghs/anime_face_detection` ONNX v1.4, MIT; immutable artifact digest still TBD. License-clean fallback candidate YuNet MIT + SFace Apache-2.0 is an explicitly selected separate profile, not an automatic substitute.
- Character representation: CCIP with exact OpenRAIL restrictions assessed; WD-v3 Apache-2.0 taggers for closed-set character labels, not universal identity truth. Package license never replaces artifact review.
- Clustering candidates: HDBSCAN BSD-3, Chinese Whispers MIT, or DBSCAN with **per-model calibrated** distance/core-point thresholds. Immich's minFaces=3 and PhotoPrism's sface 0.72 are comparators, not copied defaults. Unknown/outlier bucket and minimum core-support gate prevent forced identity assignment.
- Target-versus-confusable margin is calibrated on labelled hard negatives; unknown identities do not get routed to the nearest named character by default. Cropping/rendering and threshold changes version semantics.
- AC-FR-IDENTITY-001-01: parallel paired CPU A/B on ID-SYN-v1 across anime styles, occlusion, multiple faces, no-face, confusables and unknowns; report detection coverage, false merges/splits, unknown rejection, precision/recall, margin and latency/RAM; per-slice budgets and digests TBD **before** execution; no switch while unqualified; evidence `evidence/AC-FR-IDENTITY-001-01.json`.

### FR-IDENTITY-002 — Human naming without training
When a user names, confirms, rejects, merges, splits or hides an identity suggestion, the review system shall append a reversible provenance-bound event and accumulate only confirmed references without changing model weights.

Scope: S: identity-v2 naming / E: CPU fixed-weight profiles / T0–T4. Status: proposed.
- Workflow: Unknown → named suggestion → Unconfirmed → Confirm/Reject. Uncertainty-first “active-learning” queue means **human review prioritization**, not optimizer training. Conflicting labels remain reviewable; hidden clusters remain recoverable. Confirmation records bind actor-local ID, content/crop hash, profile, event lineage and reference-set version.
- Bad-match reports can propose a new calibrated threshold profile, never silently adapt the current one. Weight-training “rebuild training data” behavior from digiKam is explicitly out of scope; rebuilding derived references is permitted with identical weights.
- AC-FR-IDENTITY-002-01: repeat/undo conflicting naming and merge/split sessions on ID-SYN-v1; exact event replay, no unconfirmed references admitted, byte-identical weights and explicit reference-version changes; evidence `evidence/AC-FR-IDENTITY-002-01.json`.

Dependencies: INV-1/2/4, FR-STABLE-001, FR-CACHE-001, FR-PROTOCOL-001, NFR-GATE-009. Protocol prototype supports phase 1; general protocol graduation remains phase 2. No identity-verification or commercial clearance claim is made.
