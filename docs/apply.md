# 可撤销分流：独立 apply / undo

这两个入口不调用评分 CLI、不加载模型、不访问网络，也不修改评分结果。
默认仅生成计划；先在临时合成数据上验证，**不要直接试运行真实语料移动**。
共享实现位于 `_moves.py`，负责磁盘契约、路径边界及校验复制。

## 命令（项目目录中执行，PowerShell）

```powershell
$env:PYTHONUTF8='1'
# 使用项目已有虚拟环境；若已激活，可将解释器替换为 python。
.venv\Scripts\python.exe -m artcurator.apply --out out\library --plan
# 省略 --plan 完全等价：
.venv\Scripts\python.exe -m artcurator.apply --out out\library
```

只有人工检查 `moves_plan.json` 并做好备份后才使用下面的显式移动命令：

```powershell
# TOKEN 必须是计划输出的 APPLY- 加 digest 的前 8 位。
.venv\Scripts\python.exe -m artcurator.apply --out out\library --execute --confirm <TOKEN>
.venv\Scripts\python.exe -m artcurator.undo --out out\library --log disposition_log.jsonl
```

`--execute`、已存在且完整的计划、未改变的 CSV SHA256、正确的确认令牌缺一不可。
计划的 `scores_sha256` 是 CSV 原始字节摘要；`digest` 是除自身以外所有计划字段的
规范化 UTF-8 JSON SHA256，包含映射、角色白名单、所有源/目标及源文件完整 SHA256。
执行不重新生成计划，也不会默默接受修改后的源文件。

`--limit N` 必须为正数：计划阶段取 CSV 前 N 行；执行阶段取计划前 N 个非 review
条目（包括已在目标位置及重复项）；撤销阶段取逆序日志前 N 个 done 条目。
请在独立沙盒输出目录使用小批量测试。一次输出目录只允许一个执行批次；已有日志后
禁止重新执行或重写计划，避免覆盖撤销依据。继续分批请使用新输出目录和更新的评分路径。
撤销不要求 CSV 仍保持原样，但必须保留原计划及其有效摘要。

## 默认映射与可选配置

| proposed_tier | 相对角色目录的目标 | 行为 |
|---|---|---|
| queue | queue | 已在该目录则 duplicate，不移除源文件 |
| route_nsfw | safety-review | 校验后移动 |
| route_identity | 身份待核 | 独立人工身份审查目录 |
| archive_candidate | 归档候选 | 新目录 |
| review | 无 | 保持原位 |

要求路径布局为 `characters_root/角色/来源文件夹/文件`。角色目录从每行
`abs_path.parent.parent` 推导；它必须是配置 `characters_root` 的直接子目录。
目标是该角色目录下的单层文件夹。源目录可能就是 queue，此时 queue 行是原位保留。
不递归猜测其他目录布局。

可给独立 apply 命令传 `--config path\to\apply-config.yaml`：

```yaml
characters_root: /path/to/image-library  # 占位路径，请替换
apply:
  queue: queue
  route_nsfw: safety-review
  route_identity: 身份待核
  archive_candidate: 归档候选
```

所有 `apply:` 键均可省略；未知 apply 键被拒绝；review 不可改为移动。
目标必须是普通单层名称，不接受绝对路径、路径分隔符、`..` 或 Windows 特殊字符。
独立入口只读取主配置中的 characters_root 和 apply，其余评分配置不会影响移动。
`scores.csv` 必须含 `sha16`、`abs_path`、`filesize`、`proposed_tier`；允许冻结的 22 列
（无 `qrealign`）以及后续增加列的超集。多余列忽略。计划阶段会读取源文件字节以绑定
完整 SHA256，但不创建目标目录、不改写语料。
**评分配置加载器拒绝新增 apply 键**；请使用独立且不提交的 `apply-config.yaml`，
并在 apply 命令中传入它，不要给评分配置增加此键。

## 安全模型与恢复

1. 计划阶段只读取 CSV、配置及源文件（完整 SHA256 和字节数）；写入仅发生在项目输出
   目录的计划临时文件、计划及运行锁。不会创建目标目录或触碰语料元数据写入操作。
2. CLI 输出目录必须在项目内；API 也禁止输出位于角色根目录内。源、目标、每级祖先
   都拒绝符号链接和 Windows junction。所有计划及撤销条目必须落在计划列出的角色内。
3. 执行前预检所选源文件。目标存在且内容相同：记录 `duplicate`，原文件保留。
   内容不同：尝试 `原文件名__sha16.扩展名`；后缀目标仍冲突则拒绝，不覆盖任何现有文件。
4. 每次移动用独占 `xb` 创建目标，流式复制，flush/fsync，复制可移植 stat 元数据，
   计算目标和源 SHA256。仅校验相等后才允许 unlink 源文件；不使用 rename 代替跨盘复制。
5. unlink 前先将 `done` **完成意图**写入 UTF-8 JSONL 并 fsync，再次校验两端。
   日志字段为 `{ts, sha16, src, dst, bytes, sha256_before, sha256_after, status}`。
   因此崩溃可能留下 done 且两端均存在，而不会留下已移除源却无日志的正常提交窗口。
6. 复制/校验失败立即停止，源保留，已完成的本批次项按逆序通过相同校验规则恢复；
   记录 `failed` 和成功回滚的 `rolled_back`。**失败或部分复制副本保留供人工检查，不删除**。
7. undo 按逆序处理每条 done，验证它确实对应原计划的目标（含允许的冲突后缀），
   复制回原位置并校验，再 unlink 逆向源。若两端均存在且均匹配，保留原位置、移除逆向源。
   已经恢复则报告 `already_undone`。冲突或哈希变化报告 `undo_failed`，保留文件继续处理其他项。
   duplicate 不撤销，不会删除执行前就存在的目标。空目标目录不会被删除。

可逆性依赖：至少一份经过验证的内容、原计划及日志仍可读取，存储可写，原路径没有被
其他内容占用。正常执行及中断后的已记账移动均可重复调用 undo 恢复字节和路径；
不能承诺在外部修改、磁盘损坏、断电丢失硬件缓存或日志被人为删除后“无条件恢复”。
建议保留独立备份。复制的 stat 不等于完整文件系统备份：ACL、所有权、创建时间、
NTFS alternate data streams、稀疏布局及所有扩展属性不保证跨文件系统完整保留。

## 操作约束 / 故障处理

- `.disposition.lock` 阻止同一输出目录并发操作。硬中断可能留下锁；先确认没有活动进程，
  再手动移除输出目录中的锁并运行 undo。不同输出目录的锁不协调同一角色，请勿并发运行。
- 使用期间停止其他会写入语料的程序。路径检查并非防恶意并发替换目录的 OS 沙盒，
  哈希摘要也不是签名；能同时编辑计划、摘要和令牌的人仍属于受信操作员。
- 复制完成但写入 done 之前崩溃：原文件仍在，额外副本保留；人工核对后再处理。
  JSONL 截断/损坏时 fail closed，不自动跳过或修补；保存副本后人工恢复有效日志。
- 回滚也可能因空间不足、权限或外部文件变更失败；明确报告，保留可用副本，修复环境后 undo。
- SHA256 检查保证的是文件内容，不证明图像质量、身份或安全分类。
- 计划读取完整源文件，耗时取决于磁盘吞吐；本次不使用云服务。

## 测试

```powershell
.venv\Scripts\python.exe -m pytest tests\test_apply.py -q
```

所有移动测试的数据都在 pytest `tmp_path`，不访问真实语料。覆盖默认计划、所有映射、
摘要与令牌门禁、中文/日文路径、正确复制移除、复制损坏后的批次回滚、碰撞、原位 queue、
重复撤销、done 后 unlink 前的中断状态、变更目标拒绝撤销、配置越界、链接检测、limit
以及独立 CLI 入口。跨卷采用同一复制机制；测试未声称实际挂载两个卷进行故障注入。
