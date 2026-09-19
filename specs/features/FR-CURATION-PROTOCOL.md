> 中文摘要
> 策展侧车绑定完整内容哈希，独立保存人工决定与模型证据。
> 未知主版本保留但不授权操作，写入使用原子替换。
> 协议不代替移动日志，旧缓存也不能自动成为可信证据。

# Curation protocol

Current browser localStorage and JSON/CSV action exports are separate from `proposed_tier`. There is no implemented `.curation.json` protocol or generic import authority. Existing plan execution uses frozen `scores.csv` plus plan/token/digest; adding sidecars is a new capability, not a rename of that contract.

### FR-PROTOCOL-001 — Versioned content-bound sidecar
When importing or writing `.curation.json`, the coordinator shall validate major/minor version and full-content binding, preserve additive unknown data and atomically publish only a complete record.

Scope: S: curation protocol v1 candidate / E:* / T0–T4. Status: proposed.
- Proposed minimum envelope: protocol major/minor; document ID; content SHA-256 and byte length; semantic/execution/run provenance for evidence; separate model proposals and human events; reference-set version; extension fields. Event IDs and supersedes links allow idempotent replay without overwriting history. Locator/path is advisory, never authoritative identity.
- Minor revisions add optional fields without changing existing meaning. Unknown fields round-trip. Unknown majors are preserved opaque and cannot authorize actions. Invalid content binding, stale evidence, duplicate conflicting event IDs and nonfinite numbers fail closed.
- Adjacent temporary file, flush/fsync and atomic replace preserve last valid content; durability limitations of the actual filesystem are declared. A sidecar is not the authoritative move journal; references to plans do not grant execute permission.
- AC-FR-PROTOCOL-001-01: round-trip old/new minor and unknown-major payloads on PROTOCOL-v1; exact unknown-field value preservation, zero unknown-major/stale-content authorization, crash leaves old or new complete record, never a partial accepted record; evidence `evidence/AC-FR-PROTOCOL-001-01.json`.

### FR-PROTOCOL-002 — Explicit decision authority
When applying imported human decisions, the coordinator shall retain proposal/evidence history and require a newly reviewed frozen plan with unchanged content and confirmation before moving files.

Scope: S: protocol-to-plan / E:* / T0–T4. Status: proposed.
- Manual decision authority and model eligibility are distinct fields. Import is preview-first and reports conflicts; timestamps are audit data, not score inputs or automatic precedence over conflicting decisions. Undo delegates to INV-3/FR-PERSIST-001 rather than replaying arbitrary sidecar commands.
- AC-FR-PROTOCOL-002-01: import conflicting, duplicated and stale manual journals on PROTOCOL-v1/MOVE-SYN-v1; no proposal mutation or move during preview, all conflicts explicit, only approved content-bound plan executes; evidence `evidence/AC-FR-PROTOCOL-002-01.json`.

Dependencies: FR-STABLE-001, FR-CACHE-001, FR-PERSIST-001 and NFR-GATE-008. SQLite schema migration and ordered durable move records remain separate contracts. Protocol JSON Schema publication, digest and exact version negotiation fixtures: TBD before implementation graduation.
