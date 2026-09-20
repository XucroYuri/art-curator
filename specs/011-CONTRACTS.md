> 中文摘要
> 完整哈希才是内容身份，短哈希仅作索引提示。
> 扩展协议、缓存与持久化均须版本化并验证来源。
> 数值允许预先声明的误差，但边界决策不能偷偷改变。

# Contracts

## Existing schemas (informative, not the proposed wire protocol)

`db.Row` is a finite-valued Pydantic record with internal `sha256` and `mode`. `db.COLUMNS` exports exactly this relative order:

```text
sha16, abs_path, path_rel, filename, width, height, filesize, phash,
family_id, aes_v25, topiq_iaa, topiq_nr, qrealign, hpsv3_mu, hpsv3_sigma,
nsfw_prob, identity_sim, confusable_margin, novelty, consensus_z,
disagreement, gaming_delta, flags, proposed_tier, thumb_rel
```

SQLite currently stores `images(position,payload)`, `meta(key,value)`, `timings(pass,seconds,images,cached,load_seconds)` and rebuilds a `scores` view. `families.json` contains family_id/members/champion/runner_up. Existing prediction namespace is truncated SHA-256 of name|revision|preproc|variant; files are `<sha16>.npy`. Move plans bind CSV SHA-256, root, character whitelist, target mapping and moves under a canonical JSON digest; `APPLY-<digest[:8]>` is operator confirmation, not authentication. Existing journal fields: ts/sha16/src/dst/bytes/sha256_before/sha256_after/status. These formats need explicit migration, not silent reinterpretation.

### FR-STABLE-001 — Exact and approximate identities
When identifying content, replaying decisions or comparing runs, the system shall distinguish exact invariants from tolerance-bounded numerical outputs.

Scope: S:* / E:* / T0–T4. Status: proposed.
- Exact: full-content SHA-256, canonical semantic-config digest, canonical pixels within one pinned rendering/preprocessing profile, and frozen move-plan bytes/digest. `sha16` is only an index hint; full SHA-256 is authoritative for identity, cache and moves.
- Tolerance-bounded: scores, embeddings, ordering and family membership/IDs across certified execution profiles. Family ID within a fixed member set is exactly `SHA256(canonical(grouping-profile ID, sorted unique full member content IDs))`; serialization/version is pinned. Changed members/profile change identity; arbitrary sequential IDs do not qualify. No promise of stable families under corpus growth.
- AC-FR-STABLE-001-01: permute/duplicate rows and inject identical sha16 prefixes on HASH-v1; exact content/config/pixel/plan comparisons, exact fixed-member family digest and declared NFR-NUM-001 bounds for numeric comparisons; evidence `evidence/AC-FR-STABLE-001-01.json`.

Implemented snapshot subset: `content-set-json-v1` serializes the two-element
array `[grouping_profile_id, sorted_unique_full_member_sha256s]` as compact JSON
with separators `,` / `:`, ASCII escapes, UTF-8 bytes, no whitespace/newline;
`family_id` is the full lowercase SHA256 hex digest (no `fam_` prefix).
The current grouping profile is
`phash6-or-phash10-cosine096-connected-v1`; its version binds the existing
pHash/cosine thresholds and connected-component algorithm. `families.json` adds
`family_id_schema`, `grouping_profile_id` and `member_content_ids` for replay.
Existing short-ID `members`/champion fields remain compatibility hints, not
authoritative content identity. No separate lineage is inferred from old
sequential IDs. Unknown quality yields null champion/runner-up rather than a
quality winner. Evidence: [four-gap-regressions.json](evidence/four-gap-regressions.json),
GAP-3. Cache/embedding alignment/CSV full-hash migration remains open.

### NFR-NUM-001 — Predeclared numerical and decision budgets
When certifying numerical equivalence, the evaluator shall compare each scorer against a named reference using `|x−y| ≤ a_m + r_m·|y|` and test decision boundaries separately.

Scope: S: each named scorer/grouping profile / E: candidate versus reference / T0–T4. Status: proposed.
- Starting hypotheses, not certified budgets: FP32 atol=1e-5, rtol=1e-4; FP16 atol=1e-3, rtol=1e-3. Each scorer independently declares its pair before measurement. BF16 budgets TBD; INT8 gets **no automatic relaxation** (new budget needs justification and approval before testing).
- Intervals include measured numerical bounds and declared uncertainty; HPS sigma is not automatically a calibrated confidence interval. Require pairwise preference only for non-overlapping intervals. Overlap means ambiguous, with deterministic full-content-identity tie-break solely for presentation, never a quality claim. Ordering metrics and family membership budgets are predeclared, not inferred from a good mean error.
- AC-NFR-NUM-001-01: compare every value, near-boundary pair, decision and family on NUMERIC-v1 across batch/device/export variants; all per-scorer budgets met, zero unsupported strict preferences or changed actionable decisions outside the declared ambiguity set; evidence `evidence/AC-NFR-NUM-001-01.json`. Embedding/family/coverage thresholds: TBD before qualification.

### FR-SCORER-001 — Declarative extension boundary
When registering a scorer, the coordinator shall require a complete versioned manifest and restrict its adapter to evidence production without filesystem moves or coordinator-state writes.

Scope: S: scoring / E:* / T0–T4. Status: proposed.
- Manifest: stable signal ID; output-contract version; weight digest and code/weight licenses; preprocessing profile; units/range/direction/invalid policy; semantic and certified execution profiles; resource estimates; supported batching; timeout/cancellation; determinism limitations; certification-evidence reference.
- Invalid/missing evidence is typed unavailable, never zero. Adapter inputs are ordered canonical tensors plus opaque correlation IDs; outputs are keyed typed columns. The manifest names immutable prompt constants under INV-2. Licensing is not inferred from package metadata alone.
- AC-FR-SCORER-001-01: register incomplete/malicious synthetic adapters on PROTOCOL-v1; reject every missing field and unauthorized state/move request, accept only declared output schemas/ranges; evidence `evidence/AC-FR-SCORER-001-01.json`.

### FR-WORKER-001 — Versioned worker handshake
When connecting a worker or accepting a batch result, the coordinator shall validate protocol/build, environment/lock digest, model artifact, preprocessing profile, capabilities and request lineage before persisting evidence.

Scope: S: scoring / E: isolated workers / T0–T4. Status: proposed.
- Handshake binds major/minor protocol and execution identity. Requests carry run ID, request ID, ordered full content IDs, tensor schema and deadline. Responses bind all of these plus actual provider placement and output contract.
- Reject mismatched, misordered, nonfinite, duplicate, incomplete or stale responses; no zip-by-position repair. Timeout/cancellation leaves unavailable evidence, not partial success. Current `subprocess.run(check=True)` with direct SQLite writes is not this protocol.
- AC-FR-WORKER-001-01: inject each failure and cancelled late response on PROTOCOL-v1; zero invalid committed results, explicit reason per rejection and bounded shutdown within the manifest deadline; evidence `evidence/AC-FR-WORKER-001-01.json`.

### FR-CACHE-001 — Provenance-bound cache
When reading or publishing cached evidence, the coordinator shall bind full content SHA-256, semantic/output/preprocessing versions and certified execution provenance, verify payload integrity and reject stale or invalid entries.

Scope: S:* / E:* / T0–T4. Status: proposed.
- Atomic publication; finite/shape/range checks apply to hits as well as fresh inference. Reverify snapshot binding against changed source content before use. A sha16 collision cannot alias entries. Compatibility certificates may authorize explicit reuse across execution profiles; absence is a miss, not equivalence.
- AC-FR-CACHE-001-01: corrupt payloads, replace files after scan, collide prefixes and replay older profiles on HASH-v1/PROTOCOL-v1; zero poisoned/stale hits or silent overwrites; evidence `evidence/AC-FR-CACHE-001-01.json`.

### FR-PERSIST-001 — Durable state and recovery
When migrating state or executing/undoing a move, the coordinator shall preserve recoverable versioned state and reconcile one authoritative ordered move journal with filesystem contents before further mutation.

Scope: S: persistence/moves / E:* / T0–T4. Status: proposed.
- SQLite uses monotonic schema version plus migration ledger (from/to, migration digest, outcome), verified pre-migration backup and transactional/resumable migrations. Interrupted migration is tested at every boundary; no implicit view rebuild stands in for a ledger.
- Move journal uses increasing sequence, operation/run/plan IDs, full hashes, statuses and record-integrity framing. Records are independently durable before unlink, even when ordinary evidence writes are batched. On a torn final record, preserve original journal, recover only the validated prefix and reconcile both paths; midstream corruption fails closed. Durable reconciliation records extend the same authoritative journal; exports are non-authoritative views.
- Freeze plans and verify destination/source hashes; reconcile both-present, source-only, destination-only and neither-present states. Neither-present or mismatched bytes is explicit manual recovery, never fabricated success. Undo never overwrites later edits. Cross-output concurrent access needs corpus-level exclusion before qualification; current per-output lock is insufficient.
- AC-FR-PERSIST-001-01: migrate old manifests with interruption and backup-restore on PROTOCOL-v1; schema versions never regress and recovered logical rows equal baseline exactly; evidence `evidence/AC-FR-PERSIST-001-01.json`.
- AC-FR-PERSIST-001-02: crash/truncate/replay/concurrently execute on MOVE-SYN-v1; zero lost authoritative records, no unverified unlink/overwrite, every conflicting path reported and valid-prefix recovery reconciles exactly; evidence `evidence/AC-FR-PERSIST-001-02.json`.
