> 中文摘要
> 目标是本地图库的策展智能层，而非另一套云相册。
> 借鉴成熟产品的命名、元数据与浏览体验，不照搬训练机制。
> 多评分共识、弃权、同族择优与可撤销计划构成差异。

# Vision

Product context below is supplied, research-confirmed comparator information, not a fresh audit of those projects or blanket model-license clearance.

| Comparator | Strength to borrow | Boundary / lineage |
|---|---|---|
| Picasa | People albums, naming-as-learning, light single-machine UX | EBGM/Gabor + human naming loop; never open-sourced; borrow interaction, not proprietary implementation |
| digiKam | Professional tags/metadata, Unknown → name → Unconfirmed → Confirm/Reject | Cumulative face-recognition learning and rebuild-training-data workflow; GPL-2.0; weight training is not adopted |
| Immich | Modern web UX, timeline/search, merge/split/hide | AGPL-3.0; InsightFace buffalo_l/buffalo_s models non-commercial; DBSCAN-derived incremental clustering: core-point minFaces=3, maxDistance=0.5 (recommended 0.3–0.7), minScore=0.7, nightly re-cluster |
| PhotoPrism | Quiet design and semantic search | AGPL-3.0, docs CC BY-NC-SA; YuNet MIT + SFace Apache-2.0; per-model calibration (e.g. sface clusterDist=0.72); bad-match reports adaptively lower thresholds |

These thresholds are comparator-specific, not transferable cosine cutoffs. Human naming here accumulates confirmed references with fixed embeddings, consistent with INV-1; adaptive thresholds require explicit profile revision rather than invisible learning.

### FR-VISION-001 — Local curation layer
When a user reviews a local image library, the system shall offer evidence-backed multi-scorer proposals, disagreement-based abstention, counterfactual gaming inspection, family best-of review and explicit reversible move plans without uploading images.

Scope: S: curation / E:* / T0–T4. Status: implemented (legacy subset; qualification proposed).
- Five current quality means: `aes_v25`, `topiq_iaa`, `topiq_nr`, `qrealign`, `hpsv3_mu`; `hpsv3_sigma` is native uncertainty, not a sixth vote. SigLIP provides references; `nsfw_prob` supplies safety routing. Single-file offline review is the distinguishing human surface.
- Non-goals: sync/backup, mobile apps, multi-user authentication, video pipeline and web-scale server. Tiers do not expand product scope.
- AC-FR-VISION-001-01: trace an offline SYN-STUDIO-v1 review to evidence, manual journal, frozen dry-run plan and synthetic undo; zero image-network requests and zero moves without explicit confirmation; evidence `evidence/AC-FR-VISION-001-01.json`.

Success is useful, inspectable prioritization, not an unsupported precision/recall claim. Labelled identity accuracy, curator agreement, time saved and all-abstain usefulness floors remain **TBD/unqualified**; graduation requires declared fixtures and budgets before evaluation (040).
