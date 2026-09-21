> 中文摘要
> 文件夹/会话参考名与 WD 标签可能只是命名空间不同，不代表已证实认错。
> 共现与分数只用于提出别名；只有人工确认才能合并命名空间，拒绝会持久保存。
> 离线工作台导出决定，由本地库 API 应用到人物记忆；不会自动确认真实语料。

# Feature: Human-confirmed alias reconciliation

Scope: S: WD-compact-v1 / saved profile-bound references / E: local saved evidence /
T: experimental desktop. Status: implemented experiment; scoped evidence in
`docs/alias-reconciliation.md`, not accuracy certification.
English is normative. Extends, but does not rewrite, FR-CANDIDATES-008/009.
Fixture ALIAS-SYN-v1: deterministic saved vectors in `tests/test_alias_reconciliation.py`.

### FR-ALIAS-001 — Observable proposals, never automatic aliases
When folder-derived or human-confirmed session reference banks have saved WD evidence,
the coordinator shall emit `alias-candidates.json` with ranked reference-name/WD-tag pairs.

- Include every reference bank, including banks with no observations. Join actual
  reference images by full content digest, not path-name resemblance. Count each
  image once per tag (maximum crop score); expose total bank images, tagged images,
  co-occurrence counts, top-1 counts, score min/p25/median/p75/max and rank.
- Where saved WD evidence does not cover reference images, expose a SEPARATE weak
  visual cohort: unique strongest non-self reference >.35, deduplicated by full
  image digest. Never describe these retrieved images as actual reference images.
  Ties, exclusions, missing tags and missing banks must not manufacture observations.
- Rank by direct-image count, then cohort-image count, then median score, then tag.
  Relatively strong support requires >=3 direct images, >=80% of tagged direct
  images, and median >=.85. Everything else is weak. These are descriptive review
  heuristics, not truth or calibrated confidence; compact WD censoring is disclosed.
- Bind proposals to corpus/profile and input digests. No proposals alter memory,
  labels, gates, model weights or originals. Explicit session names are supported
  through existing human-confirmed reference events, not inferred from query paths.
- AC-FR-ALIAS-001-01: Method: pytest actual producer plus analytic aggregation;
  fixture: ALIAS-SYN-v1; comparator: deduplicated exact counts, quantiles and stable
  ranks, empty banks, ties and lineage rejection. Artifact: `specs/evidence/alias-reconciliation.json`.

### FR-ALIAS-002 — Persist human decisions in memory
When a human confirms or rejects a proposed pair, the local application API shall
validate the complete bound decision batch before persisting character memory v2.

- `Character.alias_decisions` records raw WD tag, confirmed/rejected decision,
  actor and timestamp. Only confirmation adds the WD tag to the character's
  existing alias namespace; rejection must not add an alias. A pair is reversible
  only by another explicit decision. Ambiguous ownership fails closed.
- Read v1 memory; write v2. Existing curated v1 aliases remain human-curated.
  Rename preserves decisions and old names; merge unions compatible decisions and
  rejects contradictions; delete removes that character's curated decisions and
  aliases. Import/export round-trips decisions, refuses contradictory stale imports,
  and retains existing corpus/profile and face-ownership checks. Label synchronization
  must not discard decisions. Rejected pairs remain rejected on regeneration.
- Apply uses the existing exclusive stage lock; per-file atomicity is inherited.
  Multi-file crash recovery is not certified. Offline downloads are not filesystem
  writes to memory: the user must apply the exported envelope locally.
- AC-FR-ALIAS-002-01: Method: disk-backed pytest API tests; fixture: ALIAS-SYN-v1;
  comparator: exact confirmed/rejected aliases after reload, label sync, rename,
  merge, delete, import/export; invalid batches leave memory unchanged.
  Artifact: `specs/evidence/alias-reconciliation.json`.

### FR-ALIAS-003 — One namespace, conservative demotion
When comparing model, memory, reference or confirmed names, the suggestion producer
shall resolve curated aliases into the same canonical namespace before comparison.

- Unconfirmed proposals and rejected pairs cannot promote a suggestion. Preserve
  score >=.85 AND margin >=.20, exact-crop exclusion and contradiction demotion.
  A resolved compatible pair can become eligible, never human-confirmed or verified
  merely because an alias exists. Genuine other-character evidence still demotes.
- Unknown reference namespaces use `reference-namespace-unresolved`, not a verified
  identity-error claim. Known incompatible canonical names retain evidence disagreement.
- AC-FR-ALIAS-003-01: Method: actual suggestion-producer pytest; fixture: ALIAS-SYN-v1;
  comparator: demoted -> eligible only after explicit confirmation, false verified
  flag, unconfirmed/rejected/no-alias cases still demoted, other-character contradiction
  retained. Artifact: `specs/evidence/alias-reconciliation.json`.

### FR-ALIAS-004 — Offline human review surface
When opening alias review in the single-file studio, the user shall see proposed
pairs, ranked evidence, weakness disclosures and explicit confirm/reject controls.

- Use existing tokens, native controls, visible focus, Tab/Enter/Space, Escape and
  focus restoration; isolate gallery shortcuts while the dialog is open. Wrap CJK
  and raw tags at 1280/768/375 px. No external assets or network service.
- Persist local decisions under the stable corpus/profile binding, export a v1
  `alias-decisions.json` envelope, and distinguish browser-pending from applied
  memory decisions. Never silently rewrite the displayed pipeline suggestions.
- AC-FR-ALIAS-004-01: Method: real-browser keyboard, reload/export and layout tests;
  fixture: synthetic single-file gallery plus private snapshots; comparator: exact
  decision payload, zero console errors/external requests/horizontal dialog overflow
  at 1280/768/375 px. Artifact: `specs/evidence/alias-reconciliation-ui.json` and
  synthetic screenshots `docs/assets/alias-*` (private captures stay under `out/`).

### NFR-ALIAS-001 — Honest corpus receipt
When regenerating the three galleries, the operator shall report baseline and
after demoted/eligible face counts and alias-proposal counts separately.

- Baseline comparator: pilot 1013/0, review 2885/0, similarity 267/0 demoted/eligible.
  No real aliases are confirmed by this implementation run. Consequently proposals
  alone must preserve those demotions. The 143 review `2b_(nier:automata)` proposals
  remain an explicit confusable observation, not a labelled false-positive estimate.
- AC-NFR-ALIAS-001-01: Method: saved-evidence regeneration and gallery builds;
  fixture: the three private snapshots; comparator: exact baseline counts, unchanged
  image rows, zero fabricated confirmations. Artifact: `specs/evidence/alias-reconciliation.json`,
  private `alias-reconciliation-report.json`, and `docs/alias-reconciliation.md`.
