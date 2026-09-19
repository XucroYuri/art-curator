> 中文摘要
> 历史决策以独立环境隔离评分器依赖冲突。
> 升级 Transformers 曾改变美学分数，恢复旧版后相等。
> 子进程隔离已实现，但版本握手与长期工作进程尚未认证。

# ADR-0001 — Isolated scorer environments

Status: accepted, retrospective; date of evidence 2026-09-19. Requirement trace: FR-ARCH-001, FR-WORKER-001, NFR-DATA-001. No independent normative requirements are added here.

## Context and decision

`score.py` dispatches Q-ReAlign and HPSv3 through Windows `.venv-qrealign/Scripts/python.exe` and `.venv-hpsv3/Scripts/python.exe`. Main environment retains Transformers 4.57.6/pyiqa 0.1.15.post2; Q-ReAlign requires 5.17.0/0.1.16; HPS uses 4.45.2 and hpsv3 1.0.0. Keep dependencies isolated rather than upgrading the main environment or substituting scorers.

Evidence: `out/review/summary.md` deviation_qrealign_dependency; `docs/pipeline/hpsv3.md`; `tools/check_aesthetic_upgrade.py`; `environment-versions.json`. Eight-image aesthetic upgrade comparison changed scores by up to 0.0625 (>0.001); restoration gave exact equality on that slice. This is limited regression evidence, not universal equivalence.

## Alternatives and consequences

Rejected shared upgrade because measured scores drifted; rejected model substitution because semantics change. Costs: multiple environments, Windows paths, process startup and dependency inventories without a full lock. Workers currently write coordinator SQLite directly and have only exit-code success; isolation is not a sandbox or version handshake.

Future acceptance: AC-FR-WORKER-001-01 validates protocol/environment identity; AC-NFR-DATA-001-01 validates long-lived batched workers; AC-NFR-GATE-003-01 validates any changed execution profile. Artifacts at the AC paths are mandatory before those capabilities are claimed.
