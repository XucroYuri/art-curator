# WeMM spike — measured resumed run

Receipt publication (UTC): 2026-09-20T05:32:00.310930+00:00

## Verdicts under unchanged preregistration + A1/A2

**Crop: DO-NOT-ADOPT — measured accuracy gate failure.** Native gain is **1.3793 absolute percentage points**, below **+5**. MRL is diagnostic only.

**Search: DO-NOT-ADOPT — measured retrieval gate failure.** Measured top-10 prompt-to-own-image self-retrieval is **3/21 = 14.3%** (Wilson 95% 4.98–34.6%), far below the preregistered **≥60%**; even counting all 16 unresolved associations as hits gives 19/37 = 51.4%, still below 60%. Latency p95 **0.75 s** (≤2 s ✅) and the native index **30.97 MB ≤ 38.80 MB** budget ✅. The historical provisioning overrun (≥2,842 s vs 1,800 s) is recorded separately; A1/A2 do not reset it.

The sections below supersede historical unavailable values only where new measurements exist. A running or absent measurement is not zero and is not a model-quality failure.

## Weights and execution provenance

Pinned revision: `bbd6cd4bf52cfc6716f752a2df80b2706720bd95`.

Local weights: **5,441,695,216 bytes**; freshly recomputed SHA-256:

`e1a1ad752808c26965aa97d37bf4a9bca71d838513f41e83790cb1e71cac6e59`

Inventory: **16 top-level files / 17 recursive non-cache files**. Two stale `.incomplete` leftovers are **1,929,379,840 and 0 bytes**; neither is counted as a model file or loaded. Full inventory and file hashes: `out/wemm-spike/environment.json`.

Amended specification SHA-256: `90bd33e7ac757e43888c25f56ceee7b21ce8ebb6ac102581b0ae89b17cc69c61`.

WeMM uses the inspected upstream local code, single CUDA device, BF16, batch one, eval/inference, native PyTorch kernels, EXIF transpose + RGB + LANCZOS thumbnail ≤1024, no upscaling in the pre-resize step, and image-only messages with fixed upstream framing. Installed Transformers 5.2.0 selects the default fast image processor; no processor-version substitution was made. No quantization, training, offload, or precision fallback. Timing excludes model loading.

SigLIP was re-derived with the unchanged certified identity interpreter and predictor: `cuda/fp32/b16`, `crop-jpeg-v1-siglip-official`, TF32 off, SDPA. Certificate matching succeeded. Source lookup corrected an overbroad generic folder exclusion; selection stayed fixed by full source hashes, saved boxes, and exact JPEG crop hashes. No redetection. The original saved-matrix audit remains historical evidence, not the re-derived baseline.

## Experiment A: paired character LOOCV

Paired **145/145**; shortfall **0**; all four class shortfalls are zero. Per-anchor source/crop/vector hashes and original row mapping: `anchor-baseline-receipt.json`.

Rows are ordered by full source SHA-256 then original row. Self is excluded; cosine ties resolve to that order. Uniform chance **25%**; majority **64/145 = 44.1379%**.

| Class | SigLIP | WeMM-2048 | MRL-1024 diagnostic |
|---|---:|---:|---:|
| class-1 | 64/64 (100.00%) | 63/64 (98.44%) | 63/64 (98.44%) |
| class-2 | 39/42 (92.86%) | 40/42 (95.24%) | 40/42 (95.24%) |
| class-3 | 18/20 (90.00%) | 19/20 (95.00%) | 19/20 (95.00%) |
| class-4 | 16/19 (84.21%) | 17/19 (89.47%) | 17/19 (89.47%) |
| Overall | 137/145 (94.4828%) | 139/145 (95.8621%) | 139/145 (95.8621%) |
| Macro | 91.7669% | 94.5373% | 94.5373% |

### Anchor margin distributions

Best/second means maximum neighbor cosine per character, self excluded. Signed margin is true-class maximum minus best other-class maximum.

| Model / margin | min | p05 | p25 | median | p75 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| siglip / best_minus_second | 0.000377 | 0.004295 | 0.021230 | 0.044214 | 0.079502 | 0.112369 | 0.140317 |
| siglip / true_minus_best_other | -0.043943 | -0.000689 | 0.021230 | 0.044214 | 0.079502 | 0.112369 | 0.140317 |
| wemm_2048 / best_minus_second | 0.000827 | 0.010959 | 0.030837 | 0.062826 | 0.163136 | 0.240039 | 0.291852 |
| wemm_2048 / true_minus_best_other | -0.047947 | 0.005108 | 0.030837 | 0.062826 | 0.163136 | 0.240039 | 0.291852 |
| wemm_1024_mrl / best_minus_second | 0.001080 | 0.009788 | 0.030549 | 0.053736 | 0.158433 | 0.231210 | 0.287251 |
| wemm_1024_mrl / true_minus_best_other | -0.039108 | 0.002523 | 0.030549 | 0.053736 | 0.158433 | 0.231210 | 0.287251 |

Negative signed margin fractions: siglip **5.5172%**; wemm_2048 **4.1379%**; wemm_1024_mrl **4.1379%**.

### Resource measurements

| Metric | SigLIP baseline | WeMM anchor crops |
|---|---:|---:|
| Decode (WeMM includes hash verification), s | 1.016061800008174 | 0.29654709983151406 |
| Embedding, s | 13.564824300032342 | 78.2468331999844 |
| Persistence, s | 0.0013681999989785254 | 0.013325400010216981 |
| Stage wall, s | 14.625706799997715 | 78.6670613999886 |
| Seconds/anchor face | 0.10086694344826011 | 0.5425314579309558 |
| 5,500-face linear projection, s | 554.7681889654306 | 2983.923018620257 |
| CUDA peak allocated bytes | 2373451264 | 5492687360 |
| CUDA peak reserved bytes | 2787115008 | 5611978752 |

The 5,500-face figure is a linear projection, not a measured full run. CUDA allocator peaks are not total-board VRAM. Cold first inference is included in build/crop timing.

### Secondary clustering

**Pending/unverified:** full-face HDBSCAN comparison has not produced a completed receipt.

## Experiment B: frozen self-retrieval

The inherited 37 decode records contain 36 unique image IDs (one duplicate). Full source hashes and all matching sidecars were rechecked before rankings: **21 verified queries**, shortfall **16** versus 37. All 21 frozen prompts contain CJK and Latin text (mixed Chinese/English, character heuristic). No rewriting, translation, post-ranking selection, or distractor-pool reduction. This is prompt-to-own-image self-retrieval, not general Chinese relevance accuracy.

**Measured (complete).** Index = **3,687 previews**: the authored 3,688-row manifest minus one hidden non-image metadata entry (`.picasa.ini`), which has no preview and was never a valid index member (scope in `retrieval-index-scope.json`).

| Gate | Measured | Threshold | Result |
|---|---:|---:|---|
| top-10 hit ratio | **3/21 = 14.3%** (Wilson 95% 4.98–34.6%) | ≥60% | ❌ |
| query latency p95 | 0.75 s (median 0.66 s) | ≤2 s | ✅ |
| index size (fp32 2048 + metadata) | 30.97 MB | ≤38.80 MB | ✅ |
| association coverage | 21 of 37 (shortfall 16) | 37 | recorded |

Computed gates (derived from measurements, not hardcoded): `hit_ratio_ge_0_60=False`, `p95_le_2s=True`, `index_within_budget=True`, `provisioning_within_1800s=False`. Receipt: `out/wemm-spike/experiment-b.json` (per-query ranks, top-5 and latencies under `rows`).

## Explicit unverified list

- Full-face HDBSCAN ARI/purity/coverage and full-face timing.
- Retrieval is now measured (see above): hits/n + Wilson CI, index sizes, latencies and the ten top-5 lists are in `experiment-b.json`; the "ten anecdotes" remain anecdotal and cannot override the primary rule.
- Exact original 37 distinct sidecar associations (A2 uses frozen 21; shortfall 16).
- Independent near-duplicate/source-family leakage adjudication (historical exact source/crop duplicates=0; anchor pHash distance≤4 pairs=0).
- Production integration, ten-pair performance certification, cross-device generalization.
- Full dependency/corpus redistribution licensing and optional CCIP.
- LSP/type-check evidence: diagnostics tool rejected the changed paths as outside its request cwd.

## Receipts and hygiene

Private receipts are under `out/wemm-spike/`: `environment.json`, `anchor-baseline-receipt.json`, `experiment-a-measured.json`, `measured-anchor.json`, `frozen-retrieval.json`, and completed-stage B/face receipts when present. `inference-checkpoint.json` records partial progress; it is not completion proof. Model-quality verdicts do not erase the inherited download-budget violation. Source corpus, existing virtual environments and production scorers were not modified; no commit/push.

---

# Historical reports — retained verbatim; superseded where measured above

# WeMM 有界试验：终止收据与不采用判决

## 中文摘要：实测完成（与上方英文节一致，非历史记录）

**摘要：两个用途均为 DO-NOT-ADOPT，且都是实测结论，不是证据缺失。**

### 权重验证
`model.safetensors` = 5,441,695,216 字节，SHA-256 `e1a1ad75…cac6e59`，与固定 revision
远端逐字节一致；镜像（`HF_ENDPOINT=https://hf-mirror.com`）在禁用 hf-xet 后 17/17 文件完成。

### 实验 A —— 裁剪嵌入器（留一锚点 1-NN；145 锚点 / 4 类；随机 25%，多数类 44.1%）

| 嵌入器 | 总体 | Macro | 各类（64/42/20/19） |
|---|---:|---:|---|
| SigLIP-crop（现有基线） | 137/145 = **94.48%** | 91.77% | 100.0 / 92.9 / 90.0 / 84.2 |
| WeMM-2048 | 139/145 = **95.86%** | 94.54% | 98.4 / 95.2 / 95.0 / 89.5 |
| WeMM-1024（MRL 诊断） | 139/145 = 95.86% | 94.54% | 同上 |

Δ = **+1.38 个百分点**，门槛为 **+5** → **DO-NOT-ADOPT**。
WeMM 的间隔分布确实更宽（中位 margin 0.063 vs 0.044），但未转化为可用精度；
MRL-1024 与 2048 逐位相同（若将来引入，存储可减半）。收据：`out/wemm-spike/experiment-a.json`。

### 实验 B —— 中文文本→图检索（索引 3687 张预览，全量扰动池，无捷径）

| 门禁 | 实测 | 阈值 | 结果 |
|---|---:|---:|---|
| top-10 自检索命中率 | **3 / 21 = 14.3%**（Wilson 95%：4.98–34.6%） | ≥60% | ❌ |
| 查询延迟 p95 | 0.75 s（中位 0.66 s） | ≤2 s | ✅ |
| 索引体积（2048 维 fp32 + 元数据） | 30.97 MB | ≤38.80 MB | ✅ |
| 关联覆盖（对齐 37 条边车提示词） | 21 条（缺 16） | 37 | 缺口入档 |

`gates` 由脚本从实测值计算（`hit_ratio_ge_0_60=False`、`p95_le_2s=True`、
`index_within_budget=True`、`provisioning_within_1800s=False`）。
**即便把 16 条未决关联全部按命中计算（19/37 = 51.4%），仍低于 60%** → **DO-NOT-ADOPT**。
收据：`out/wemm-spike/experiment-b.json`；索引范围与排除项见 `retrieval-index-scope.json`
（清单 3688 → 可索引 3687，排除的 `.picasa` 为隐藏非图片元数据，理由入档）。

### 结论与后续
1. **裁剪嵌入器：维持 SigLIP-crop + 参考锚定**——现有架构被实证为最优（4 倍参数量只换来 +1.38pp，
   且需额外 5.4GB 权重与独立环境）。
2. **搜索用途：不引入 WeMM**（命中率差距过大；其模型卡亦仅声明 zh/en）。
3. 若未来重启：需**新的预注册**（更宽松的下载预算）与**更大的标注查询集**——21 条自检索样本
   不足以外推通用中文相关性。

---

## 历史：恢复检查点（当时尚未完成新实测）

以下原报告保留为历史记录，不代表镜像续传的最新完成状态。
本次已在规范末尾、任何新指标计算之前登记 **A1/A2**，状态均为 `amendment`：

- **A1：** 允许以同一认证 `cuda/fp32/b16` 和
  `crop-jpeg-v1-siglip-official` 配置重新推导锚点基线；必须核对相同裁剪哈希，
  不重检测，并新增逐锚点来源、裁剪、向量哈希收据。报告实际配对分母及缺失项；
  原生提高至少 **5 个绝对百分点** 的规则不变，MRL 仍只作诊断。
- **A2：** 先检查能否修正边车关联以恢复原始 37 条；否则冻结实际可验证的关联，
  报告 **hits/n、Wilson 95% 区间和与 37 的差额**，按实际 n 应用 **≥60%**。
  完整预览干扰池、**p95≤2 秒**、**10 KiB/图+1 MiB** 和所有时间预算不变。

恢复检查点：`out/wemm-spike/resume-checkpoint.json`。13:01:05（+08:00）
观察到用户启动的下载进程仍存在，最终 `model.safetensors` 尚未出现；本次没有终止它。
13:04:18（+08:00）第二次观察结果相同。本会话受两次状态检查的执行上限限制而停止，
不是下载失败判定；下载进程保留运行，没有后台评估器被启动。
已从固定 revision 的 HF API 获取远端清单，共 **17 个文件**。
权重期望大小为 **5,441,695,216 字节**，期望 SHA-256：

```text
e1a1ad752808c26965aa97d37bf4a9bca71d838513f41e83790cb1e71cac6e59
```

该字节数来自 API 文件清单的 `size`/`lfs.size`；`safetensors.total`
的 **2,720,809,792** 是参数数量，不能用作文件字节数。
尚未完成本地最终大小、SHA-256 和原下载收据的全量比对。

**本次没有产生 A/B 新指标，因此两个判决仍为 DO-NOT-ADOPT (inconclusive)，
不是模型效果实测失败。** 原报告中“没有修改规范”“没有镜像续传”等句仅描述之前的运行。
旧脚手架尚缺 A1 基线收据、可靠配对排序、A2 分母、预热排除、联合延迟计时、
元数据预算及累计推理监督，不应原样执行并宣称通过。准备/下载的历史预算超限仍保留，
两项修订没有将其重置。没有修改生产路径、语料或虚拟环境，也没有 commit/push。

未验证项：最终本地权重清单/摘要；A1 的 145 项重建及短缺；全部 LOOCV、macro、
MRL、margin、ARI/纯度/覆盖率；CUDA 峰值、分阶段耗时、秒/脸与 5,500 脸预测；
37 条恢复或冻结的实际查询分母；hits/n 和区间；完整索引、实际尺寸及构建时间；
含编码及排名的延迟、排除预热；十条定性 top-5。不得把下面历史 N/A 当成零。
本次对修改的规范和报告进行隐私扫描，无词边界语料名称或机器路径命中。
LSP 拒绝这两个 Markdown 路径（工具报告不在请求 cwd 内），未取得诊断通过证据；
本次仅修改文档及检查点，无适用的程序构建。

---

## 原终止报告（保留历史）

日期：2026-09-20。状态：**试验因下载预算超限终止，非完成的模型效果评测**。

## 结论

| 用途 | 判决 | 决定性证据 |
|---|---|---|
| 替换人脸裁剪嵌入器 | **DO-NOT-ADOPT (inconclusive)** | 下载已超过 30 分钟，权重不完整；145 个锚点与指定保存矩阵对应裁剪的精确配对为 **0/145**；无法检验原生 2048 维相对基线 **≥+5 个绝对百分点** |
| 搜索入口 | **DO-NOT-ADOPT (inconclusive)** | 无完成的索引、37 次排名或计时；原始 37 条查询关联未建立；无法验证 **≥23/37、p95≤2 秒、索引≤10 KiB/图+1 MiB** |

这是证据不足的判决，**不是模型准确率低、命中率为零或显存不足的实测结论**。
没有把缺失值写成零分，没有调整阈值，也没有把未测指标算作通过。

规范：[FR-SEMANTIC-SEARCH](../../specs/features/FR-SEMANTIC-SEARCH.md)。执行前记录的 SHA-256：

```text
a2955e204a39697daba2e32abbb93748dd51d8b6beb5e51f35c213fa3e160cb0
```

没有修改该规范，没有追加放宽预算的修订。以下 `out/library`、`out/review`、
`out/similarity` 均为逻辑语料别名。私有收据统一位于 `out/wemm-spike/`。

## 下载为什么没有继续

接手时，上一次启动的下载进程并未消失。进程创建时间为本地时间 **11:50:43**，
本次观察时间为 **12:38:05**：仅该进程的运行时间下界就有 **2,842 秒
（47 分 22 秒）**，超过预注册 **1,800 秒** 下载/准备上限至少 **1,042 秒**。
这还没有计入更早的环境准备时间。日志记录权重读取超时后尝试续传。

发现越界后已终止该下载进程树，保留缓存，不删除部分下载。不因代理重启而重置总预算。
因此，本次没有另起 `snapshot_download` 或镜像重试，也没有启动 WeMM 推理。
**镜像是否可成功下载仍未验证**；跳过原因是预算已经耗尽，而非已证明镜像不可用。
这记录的是接手前已经发生的预算违反，不声称此前的运行遵守了上限。

模型固定为 `tencent/WeMM-Embedding-2B`，revision：
`bbd6cd4bf52cfc6716f752a2df80b2706720bd95`。

### 已完成文件清单

每个文件的完整 SHA-256、HF 本地 revision 元数据及内容与 ETag 对照见
`download-receipt.json`。以下 16 个文件合计 **20,046,122 字节**，均通过本地
revision/ETag 一致性检查；这不是新获取的远端完整仓库清单证明。

| 文件 | 实际字节 |
|---|---:|
| `.gitattributes` | 50 |
| `additional_chat_templates/sentence_transformers.jinja` | 1,452 |
| `chat_template.jinja` | 7,755 |
| `config.json` | 2,853 |
| `config_sentence_transformers.json` | 245 |
| `embedding_chat_template.jinja` | 1,086 |
| `LICENSE` | 24,546 |
| `modeling_st_wemm.py` | 3,180 |
| `modeling_wemm_embedding.py` | 1,205 |
| `modules.json` | 106 |
| `patch_sglang_video.py` | 1,983 |
| `processor_config.json` | 1,192 |
| `README.md` | 7,993 |
| `sentence_bert_config.json` | 950 |
| `tokenizer.json` | 19,990,378 |
| `tokenizer_config.json` | 1,148 |

`model.safetensors` **未完成**。缓存中 `.incomplete` 文件长度为
**1,929,379,840 字节**；这不是已校验权重的大小、有效下载比例或模型可用证明。
缓存文件的逐项路径与大小也保存在下载收据中。

### 许可证与执行环境

已阅读实际 `LICENSE`，而非仅依赖模型卡的标签。原文声明 Tencent 公开的代码、
参数及权重采用 Apache-2.0；其中经 Tencent 修改的 Qwen3.5-2B 保留 Apache-2.0
及 Alibaba 的署名。完整原文保存在 `LICENSE.receipt.txt`，并嵌入下载 JSON。
许可证 SHA-256：

```text
e87f02efc35e9bdde65c8cd5cfa26fbd3a8dcb209c5b82ed91b274b2ff643b53
```

已静态阅读 `modeling_wemm_embedding.py`：清理位置缓存，调用 Qwen3.5，
抽取最后一个有效 token，执行 L2 归一化。**没有执行远程代码**，没有进行整体安全认证。
代码、权重条款不自动授予语料或整个依赖栈的再分发许可；CCIP 未独立清除许可风险，跳过。

`environment.json` 是扩展而非重建：保留原环境记录，追加本次包版本与来源摘要。
实读版本：Python 3.12.13；torch 2.11.0+cu128；torchvision 0.26.0+cu128；
transformers 5.2.0；qwen-vl-utils 0.0.14；accelerate 1.12.0；
huggingface_hub 1.32.0；numpy 2.2.6；Pillow 11.3.0；scikit-learn 1.7.2；
safetensors 0.8.0。

请求的配置保持：单 CUDA 设备、BF16、batch=1、eval/inference、原生 PyTorch；
Pillow RGB 解码、EXIF 转置、LANCZOS 最长边≤1024、不放大；固定上游聊天框架，
图像编码不含逐图文本。没有量化、CPU offload 或精度回退。
这些是**请求配置，不是已执行的推理配置**。原环境记录的 RTX 5060 Ti / CUDA 可用性
未通过本次 WeMM 推理再次验证。allocated/reserved 峰值均为 **N/A**，不是 0。

## 实验 A：配对审计

三个已有锚点清单各含 145 项，按顺序比较的图像哈希、裁剪哈希、类别均一致。
类别以数量顺序匿名标识。实际读取 `out/review/identities.npy`，核对其文件摘要与
保存的 embedding 收据、逐行 face ID 顺序及有限值；再对 **3,701 个已有裁剪**计算
完整 SHA-256，与锚点的 `crop_sha256` 精确连接。**匹配 0 个，缺失 145 个**。

保存矩阵 SHA-256：

```text
8e983f85b705c7fd30739721d69f1f0f8cc79d23089b187b670547e69e0905a8
```

`baseline-row-manifest.json` 含矩阵行号、裁剪完整哈希、向量字节哈希及伪标签。
`experiment-a.json` 含全部 145 项映射，按完整原图哈希、原始行号排序；缺失关联明确为空。
没有重检测、重新编码 SigLIP、用整图向量替代或按聚类 ID 推断角色。
另有 `anchors.npy`，但没有把它偷偷替换为本任务指定的 `identities.npy` 配对证据。

| 类别 | 锚点数 | SigLIP-crop 正确数/分母 | WeMM-2048 正确数/分母 | MRL-1024 诊断 |
|---|---:|---|---|---|
| class-1 | 64 | N/A / 64 | N/A / 64 | N/A |
| class-2 | 42 | N/A / 42 | N/A / 42 | N/A |
| class-3 | 20 | N/A / 20 | N/A / 20 | N/A |
| class-4 | 19 | N/A / 19 | N/A / 19 | N/A |
| 总体 | 145 | N/A / 145 | N/A / 145 | N/A |

LOOCV 总体、macro 与差值均不可计算。均匀随机基线为 **25%**，多数类基线为
**64/145=44.1379%**；两者不是同一个基线。

原图完整哈希重复 **0 组**，裁剪完整哈希重复 **0 组**；已有 anchor pHash 中
距离≤4 的配对 **0 对**。这不足以排除更宽泛的近重复、同源系列或其他泄漏。

HDBSCAN 预注册配置未改变：L2 归一化、Euclidean、min_cluster_size=3、
min_samples=3、eom、不调参。保存的脸记录中 **3,695 项有聚类伪标签，6 项没有**。
CPU 基线重聚类曾启动，后终止且未产生有效指标；WeMM 聚类未运行。
因此 ARI（含噪声）、噪声单例纯度及非噪声覆盖率都为 **N/A**。
伪标签始终不是角色真值。

以下同样全部 **N/A**：best/second-best gap 与有符号 margin 的
min/p05/p25/median/p75/p95/max、负 margin 比例、裁剪解码/嵌入/持久化耗时、
秒/脸、线性 5,500 脸预测、CUDA peak allocated/reserved。
原生 2048 维未通过证据门禁，MRL 诊断不能挽救它。

## 实验 B：检索夹具审计

全量清点 **3,688 张预览**并记录预览与原图完整哈希，未缩小干扰池。
`preview-manifest.json` 实际为 **897,317 字节**，仅是审计清单，
**不是已经建成的索引元数据尺寸**。

沿用旧脚手架“解码收据中的特定来源 JPEG 名称”候选提取方式，得到 **36 个唯一候选**，
不是要求的 37 条冻结测试集。对同名原图先比较完整内容哈希，再核对相邻文本边车：
其中 **21 个关联得到验证，15 个未得到验证**。不能据此认定其余查询永远不存在；
准确的结论是：**本次未建立原始 37 条的完整、无歧义关联**。
未用 21 条或 36 条代替 37 条进行采用测试。

已确认的 21 段文本均含 CJK 字符，检查到中英文混合提示词；其余语言未知。
这是部分候选的字符检测与文本观察，不是完整 37 条的语言分布认证。
即使未来完成该测试，它测量的也是 prompt-to-own-image 自检索，不是通用中文相关性准确率。

| 必须交付的实测项 | 本次结果 | 不变的门槛 |
|---|---|---|
| Hit@10、Wilson 95% 区间 | N/A / 37；区间 N/A | 至少 23/37 |
| 全部 37 个查询耗时 | 无实测样本；预热未执行 | 排除一次预热、含编码及精确排名 |
| 延迟 median / p95 | N/A / N/A | p95≤2 秒 |
| 2048 float32 NPY | N/A，未创建 | 与必要元数据合计≤38,813,696 字节 |
| 1024 重归一化 NPY | N/A，未创建 | 仅诊断 |
| 索引构建 wall time | N/A | 在总推理 90 分钟内完成 |
| 十条中文定性查询 top-5 / cosine | N/A，未排名 | 只能是轶事，不作准确率声明 |

3,688 图的预算计算为 `3688×10240+1048576=38,813,696` 字节。
这是预算，不是实测索引大小。未用理论上的每向量 8 KiB 冒充实际文件尺寸。
十条原先冻结的中文查询保持原字节不变，其 SHA-256：
`f1dd3c881440027d507a1a8fbf8d498fd5996deee768699da4061ee596324503`。

## 收据、验证范围与未验证项

| 私有文件 | 用途 |
|---|---|
| `termination.json` | 继承进程、时间下界、终止结果及为何没有新下载/镜像重试 |
| `download-receipt.json`、`LICENSE.receipt.txt` | 完成文件/缓存大小、哈希、元数据、完整许可文本 |
| `environment.json` | 保留原记录，追加实际包版本、规范与查询摘要、请求/执行状态区别 |
| `baseline-row-manifest.json`、`experiment-a.json` | 3,701 行基线审计、145 个配对失败及 A 判决 |
| `preview-manifest.json`、`experiment-b.json` | 全量预览、候选边车关联、缺失测量与 B 判决 |
| `verification.json` | 收据一致性测试、语法编译、文件摘要与工具限制 |

未验证清单：完整权重及其摘要；远端完整文件清单；镜像下载；WeMM 代码加载与设备实际
放置；推理输出有效性及纯图像行为；145 对 LOOCV/宏平均/MRL；所有 margin 与聚类指标；
显存、吞吐及 5,500 脸预测；完整 37 条查询关联和语言分布；检索命中率/置信区间；
实际索引尺寸、构建耗时、37 个延迟、median/p95；十条定性 top-5；更全面的近重复泄漏；
依赖栈/语料再分发许可；跨设备/性能认证。

收据脚本的 LSP 检查受限：basedpyright 未安装，且已有拒绝安装记录，未擅自安装。
语法编译与收据测试不等于静态类型检查、模型测试或生产构建认证。
本次只写新试验输出与本报告；没有改生产评分器、语料或既有虚拟环境，没有 commit/push。
旧评估脚手架还缺少完整配对证明、查询预热排除、编码加排名联合计时及预算监督，
**不应直接用于宣称通过**。本轮已闭合为不采用；未来重启须先解决夹具与执行许可，
不得沿用本轮报告声称已完成实测。
