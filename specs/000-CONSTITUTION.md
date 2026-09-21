> 中文摘要
> 零训练、纯视觉、可撤销和证据约束优先于性能与便利。
> 固定模型文本常量允许，但用户文本不能进入评分。
> 任何数值通过都不能掩盖来源或恢复失败。

# Constitution

The following four records use S:* / E:* / T0–T4. Status: proposed unless explicitly amended below (binding qualification policy; existing implementation is not fully qualified).

### INV-1 — Zero-training
When processing user content or feedback, the system shall keep model weights fixed and reject user-corpus training, fine-tuning and online weight adaptation.
- Fixed pretrained weights are allowed. Quantization calibration is allowed only against a declared fixed **non-user** dataset and a separately versioned artifact. User-confirmed reference accumulation is retrieval state, not weight training; label-driven threshold changes still version the semantic profile and require evaluation.
- AC-INV-1-01: audit loading, gradients, optimizer calls and artifact digests before/after a naming session on ID-SYN-v1; zero user-derived weight/calibration changes, every calibration has dataset and artifact digest; evidence `evidence/AC-INV-1-01.json`.

### INV-2 — Pure-vision
When scoring or grouping images, the system shall consume canonical visual tensors only as corpus evidence and reject filenames, paths, timestamps, captions, camera metadata and engagement signals as features, except for the narrowly governed context-assisted grouping layer below.

Scope: S:* / E:* / T0–T4. Status: approved constitutional amendment under ADR-0005, 2026-09-21; implementation and exception acceptance criteria remain unverified.
- EXIF orientation and color profile are **rendering inputs**, not quality evidence. File names can locate/display images or select declared dataset roles; content hashes identify/deduplicate/tie-break, never raise quality scores.
- Explicit immutable-constant exception: `aes_v25`'s fixed pretrained aesthetic head and any bundled fixed prompt constants are permitted only within the pinned artifact/preprocessing profile; the repository adapter supplies no image-specific text. There is no permission to add dynamic aesthetic prompts. HPSv3's pinned empty image-specific prompt, upstream evaluation instruction/chat framing and `<|Reward|>` token are permitted immutable model constants. Changes to either exception change semantic identity. HPS is not literally text-token-free and its instruction includes safety preference.
- SigLIP image features, TOPIQ-IAA/NR, Q-ReAlign quality task and NSFW remain pixel-input adapters; no caption generator or user-prompt channel is authorized. An undeclared internal prompt path excludes that artifact from qualification until inspected and pinned.
- Governed grouping exception: only explicit folder/session membership may act as a weak prior in a separate versioned proposal layer under [ADR-0005](adr/ADR-0005-measured-context-assisted-grouping.md) and [INV-P](features/FR-ALBUM-VISION.md#inv-p--provenance-as-measured-weak-evidence). All ADR conditions are mandatory: measured and reported coherence/purity with its stated method and admission limits; snapshot-bound affirmative consent; per-image inherited provenance and evidence references; exact residue-free retraction of contextual influence; and an always-available manual inheritance path. Context always loses to visual contradiction, never silently overrides visual evidence, never changes model inputs/raw scores/context-free retrieval, and never bypasses identity gates or creates confirmed references. Missing or stale conditions fail closed to context-free behavior; manual organization remains available. Approval is not implementation or qualification.
- AC-INV-2-01: compare same rendered pixels under renamed paths and metadata variants in VISUAL-v1; exact canonical-tensor digest and scorer deltas within NFR-NUM-001; separately rotated/profile-tagged fixtures match their pinned rendering goldens; evidence `evidence/AC-INV-2-01.json`.
- AC-INV-2-02: Method: analytic admission/report replay at sample-size, cosine-quantile and purity-bound boundaries, including absent/invalid vectors, duplicates, unresolved labels and self-labelled purity; fixture: ALBUM-FOLDER-v1, frozen per the album fixture registry; comparator: exact ADR-0005 eligibility and denominators, Wilson/quantile values within absolute 1e-6 of independently calculated goldens, zero unmeasured or falsely labelled purity admissions; evidence `evidence/AC-INV-2-02.json`.
- AC-INV-2-03: Method: consent-state and per-image lineage replay with missing fields, stale digests, dismissal, timeout and newly added members; fixture: ALBUM-FLOW-v1 and ALBUM-MAP-v1; comparator: zero unconsented/stale uses, every affected image has source=inherited, verified=false, resolving evidence_refs and baseline/contextual results, all uses visibly disclosed even for unchanged results; evidence `evidence/AC-INV-2-03.json`.
- AC-INV-2-04: Method: paired context-free/assisted replay with misleading membership, maximum admitted purity, independent visual contradiction and absent/ambiguous evidence; fixture: ALBUM-CONFUSABLE-v1 and VISUAL-v1; comparator: zero overridden visual contradictions or gate bypasses, exact saved tensors/embeddings/raw scores/retrieval results, no contextual confirmed references, no assistance on invalid/missing visual evidence; evidence `evidence/AC-INV-2-04.json`.
- AC-INV-2-05: Method: enable/retract/restart replay including transitive derived state, interrupted withdrawal and later human edits; fixture: ALBUM-MAP-v1; comparator: exact context-free effective-state digest without later edits, otherwise exact baseline plus independent human-event replay, zero active contextual mapping/cache/index/reference residue or resurrection, inactive audit history only and unchanged source bytes/paths; evidence `evidence/AC-INV-2-05.json`.
- AC-INV-2-06: Method: scripted manual-inheritance/undo walkthrough with no model, absent/failed measurements, low purity and denied AI consent, then separately consented recognition; fixture: ALBUM-FLOW-v1 and ALBUM-FOLDER-v1; comparator: manual organization and undo always reachable, inherited unverified provenance preserved with unavailable reasons, zero implicit AI permission or source writes; evidence `evidence/AC-INV-2-06.json`.

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

## Revision history

- 2026-09-21 — ADR-0005: approve the narrow INV-2 context-assisted grouping exception and INV-P governance; add AC-INV-2-02–06. Preserve INV-1/3/4, existing AC-INV-2-01 and invariant numbering; no implementation or qualification claim. This previously unversioned document retains date/ADR-based revision identity rather than introducing a semantic version.
