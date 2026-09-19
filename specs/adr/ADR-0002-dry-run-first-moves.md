> 中文摘要
> 移动采用先计划、再显式确认的独立入口。
> 完整哈希、校验复制与写前日志保护源文件。
> 后续用户修改和损坏日志需要明确冲突恢复，不能强行覆盖。

# ADR-0002 — Dry-run-first verified moves

Status: accepted, retrospective. Trace: INV-3, FR-STABLE-001, FR-PERSIST-001, FR-PROTOCOL-002; no new normative requirement.

## Context and decision

Curation proposals are not authorization to delete. `artcurator.apply` defaults to writing `moves_plan.json`; execute requires stored plan, unchanged scores digest and `APPLY-<digest[:8]>`. `_moves.py` implements exclusive-create copy, fsync and full-content verification; `apply.py` appends durable done intent before unlink and rechecks both hashes. `undo.py` restores in reverse and refuses unrelated edits. `review` has no move destination.

Sources: `docs/apply.md`, `_moves.py`, `apply.py`, `undo.py`, `tests/test_apply.py`. Historical tests include CJK names, hash mismatch rollback, collisions, modified destinations and both-present interruption recovery. No physical power-loss or mounted cross-volume certification is inferred.

## Alternatives and consequences

Rejected direct rename/delete from UI and recomputing a plan at execution: neither preserves an inspectable frozen decision. Copy-verify costs extra I/O and disk space; speculative failed-wave copies remain for inspection. Token is operator intent, not authentication. Per-output locks cannot coordinate two outputs on the same corpus. Current truncated JSONL recovery is manual and fails closed.

Future acceptance: AC-INV-3-01 and AC-FR-PERSIST-001-02 cover crash cutpoints, ordered-prefix recovery, reconciliation and concurrency; AC-FR-PROTOCOL-002-01 prevents imports bypassing plan authority. Qualification awaits those artifacts.
