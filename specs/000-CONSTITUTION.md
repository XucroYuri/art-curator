> 中文摘要
> 零训练、纯视觉、可撤销和证据约束优先于性能与便利。
> 固定模型文本常量允许，但用户文本不能进入评分。
> 任何数值通过都不能掩盖来源或恢复失败。

# Constitution

The following four records use S:* / E:* / T0–T4. Status: proposed (binding qualification policy; existing implementation is not fully qualified).

### INV-1 — Zero-training
When processing user content or feedback, the system shall keep model weights fixed and reject user-corpus training, fine-tuning and online weight adaptation.
- Fixed pretrained weights are allowed. Quantization calibration is allowed only against a declared fixed **non-user** dataset and a separately versioned artifact. User-confirmed reference accumulation is retrieval state, not weight training; label-driven threshold changes still version the semantic profile and require evaluation.
- AC-INV-1-01: audit loading, gradients, optimizer calls and artifact digests before/after a naming session on ID-SYN-v1; zero user-derived weight/calibration changes, every calibration has dataset and artifact digest; evidence `evidence/AC-INV-1-01.json`.

### INV-2 — Pure-vision
When scoring or grouping images, the system shall consume canonical visual tensors only as corpus evidence and reject filenames, paths, timestamps, captions, camera metadata and engagement signals as features.
- EXIF orientation and color profile are **rendering inputs**, not quality evidence. File names can locate/display images or select declared dataset roles; content hashes identify/deduplicate/tie-break, never raise quality scores.
- Explicit immutable-constant exception: `aes_v25`'s fixed pretrained aesthetic head and any bundled fixed prompt constants are permitted only within the pinned artifact/preprocessing profile; the repository adapter supplies no image-specific text. There is no permission to add dynamic aesthetic prompts. HPSv3's pinned empty image-specific prompt, upstream evaluation instruction/chat framing and `<|Reward|>` token are permitted immutable model constants. Changes to either exception change semantic identity. HPS is not literally text-token-free and its instruction includes safety preference.
- SigLIP image features, TOPIQ-IAA/NR, Q-ReAlign quality task and NSFW remain pixel-input adapters; no caption generator or user-prompt channel is authorized. An undeclared internal prompt path excludes that artifact from qualification until inspected and pinned.
- AC-INV-2-01: compare same rendered pixels under renamed paths and metadata variants in VISUAL-v1; exact canonical-tensor digest and scorer deltas within NFR-NUM-001; separately rotated/profile-tagged fixtures match their pinned rendering goldens; evidence `evidence/AC-INV-2-01.json`.

### INV-3 — Reversible
When a move or undo removes a source copy, the move engine shall first verify destination content and recoverable durable state, never overwrite unrelated files, and explicitly report conflicts.
- No curation decision deletes originals. Verified redundant-copy unlink is permitted, not arbitrary deletion. Recoverability assumes readable plan/journal, at least one verified copy, writable storage and no conflicting user edits; it is not backup or protection against failed hardware.
- AC-INV-3-01: inject faults at every copy/fsync/hash/journal/unlink boundary on MOVE-SYN-v1, including later edits and full destinations; reconcile to at least one verified copy and durable explanation for every operation, with zero unrelated overwrites; evidence `evidence/AC-INV-3-01.json`.

### INV-4 — Evidence-based claims
When publishing a support, quality, equivalence or performance claim, the system shall name the model revision, execution profile, corpus, method, limitations and evidence artifact, and label untested configurations experimental.
- Historical receipts can document observations without granting compatibility. No numerical pass overrides reversibility or provenance failure. A quantized successful inference is not an equivalence certificate; corpus-relative percentiles are not calibrated quality probabilities.
- AC-INV-4-01: audit a CLAIMS-v1 release manifest against referenced receipts; reject every missing identity/method/artifact or unsupported certification claim; evidence `evidence/AC-INV-4-01.json`.

## Interpretation and priority (governed by INV-1–INV-4)

Safety/provenance veto (INV-3/INV-4) → zero-training and pure-vision boundaries (INV-1/INV-2) → semantic stability → usefulness → throughput → convenience. This ordering never licenses violation of another invariant; incompatible requests fail closed.

Examples: a filename identifying a favorite artist cannot boost score; honoring an EXIF rotation can change canonical pixels without treating metadata as merit. Naming a character adds a confirmed reference without updating weights. Removing HPS to fit RAM cannot silently turn a five-scorer profile into four. A faster ONNX export that crosses decision boundaries fails equivalence even if average error is low. A user edit at an undo destination produces a conflict, never a forced restore.
