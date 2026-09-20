# 排障手册（Windows 本地运行）

> 中文摘要
> 本文件记录三条在 Windows 11 上运行本项目时反复踩到的坑与已验证的解法。
> 全部为实测结论：症状、根因、修复、验证方式。
> 目的是让后续维护者不再把环境问题误判为代码或模型问题。

## 1. Windows Defender 会终止"隐藏子进程"模式（`Trojan:Win32/PowhidSubExec.B`）

**症状**：后台任务莫名消失；进程创建报 `spawn EPERM`；长任务被报告为"超时/无活动"；
被启动的进程日志写到一半即停止。

**根因**：用 `Start-Process ... -WindowStyle Hidden` 启动长任务时，"隐藏窗口 + 子进程 +
长命令行"命中 Defender 的行为检测 `PowhidSubExec`（PowerShell Hidden Subprocess Execution），
Defender 会**终止该进程树**。

**证据**：Windows Defender 保护历史（`Microsoft-Windows-Windows Defender/Operational`
事件 1116/1117）会记录被命中的 `CmdLine:`，与我们的启动命令逐字对应。

**修复（已验证）**：
- 不要使用 `-WindowStyle Hidden`；
- 长时间任务在**前台**以 ≤4 分钟的、有界的命令分步执行；
- 需要并行的长任务改用**非隐藏**窗口启动，并配合短命令轮询；
- 如需长期顺畅（需管理员，且**会降低防护**，自行权衡）：
  `Add-MpPreference -ExclusionPath '<项目目录>'`。

**判定口诀**：凡是"任务无故消失"，先查 Defender 保护历史，再看代码。

## 2. pytest 必须从项目根目录运行

**症状**：`INTERNALERROR> ... SystemExit: 1`，或出现与项目无关的收集错误
（例如 `ComfyUI-Installs\...\custom_nodes\...\tests\...`）。

**根因**：从父目录运行 `pytest` 会递归收集整个目录树下的所有测试，包括 ComfyUI 自定义节点
自带的测试。这不是本项目的测试失败。

**修复**：始终在项目根目录运行：

```powershell
# 正确：工作目录 = 项目根
.\.venv\Scripts\python.exe -m pytest -q
```

## 3. 国内下载 Hugging Face 大权重：禁用 hf-xet + 使用镜像

**症状**：大文件（数 GB 的 `model.safetensors`）下载在某个百分比**静默僵住**：
`.incomplete` 文件时间戳不再更新，进程仍在列表里但 CPU 几乎为零，可达数十分钟无进展。

**根因**：`hf-xet` 分块传输在部分链路上会挂起；普通 HTTP 断点续传不受影响。

**修复（已验证：5.4GB 在 2 分 18 秒内完成）**：

```powershell
$env:HF_ENDPOINT = 'https://hf-mirror.com'
$env:HF_HUB_DISABLE_XET = '1'
$env:HF_HUB_DOWNLOAD_TIMEOUT = '180'
```

**注意**：切换是否启用 xet 会改变本地断点文件格式，已下载的 `.incomplete` 可能无法续用，
需要重新开始——因此**下载前就设定好**，不要在卡住后才切换。

## 4. 长任务与证据纪律

- 任何超过 4 分钟的推理/下载都应当**可断点、可轮询**，并把进度写入检查点文件
  （本项目沿用 `*-checkpoint.json` + 部分矩阵的模式）。
- **声明必须有工件**：截图、收据、日志三者缺一不可；没有工件的"已完成"一律视为未完成。
- 裁决类字段（如采纳/不采纳）必须由**门禁数值计算**得出，禁止硬编码结论。
