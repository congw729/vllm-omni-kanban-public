---
name: sync-local-perf-result
description: >-
  Sync remote vLLM-Omni performance JSON results over SSH Config Host aliases,
  store under data/local_nightly_raw/manual_YYYYMMDD, and commit locally on main.
  Use when the user asks to sync/pull/upload local perf results, nightly raw data,
  benchmark logs, or provides an SSH connection name and remote log path.
disable-model-invocation: true
---

# 同步本地性能结果

## Purpose

从远程 GPU 机器拉取 vLLM-Omni 性能测试 JSON，存入 `vllm-omni-kanban` 仓库，并在本地 commit（不自动 push）。

目标仓库：**`vllm-omni-kanban`**。fork 目录如 `vllm-omni-kanban-public` 可接受，Skill 逻辑统一按主仓名编写。

## Safety Rules

1. 执行前列出 connection、远程路径、本地路径、文件 glob，征得同意后再运行。
2. 拉取远程文件**之前**必须将 `main` 与 `origin/main` fast-forward 同步。
3. **禁止自动 push**；commit 后提示用户确认是否 push。
4. 禁止 add `.env`、私钥、含 token 的文件；`git diff` 确认仅含预期 perf 文件。
5. 工作区有未提交改动时暂停，征得同意后再 stash / commit / 放弃。
6. `git pull --ff-only` 失败时停止，不自动 merge 或 rebase。

## Inputs

| 参数 | 必填 | 默认 |
|------|------|------|
| `connection` | 是 | — SSH Config Host 名（= `machine_type`） |
| `remote_path` | 否 | 自动选 `/rebase/vllm-omni/logs/` 下含 JSON 的最新子目录 |
| `local_path` | 否 | `data/local_nightly_raw/manual_{YYYYMMDD}/` |
| `files` | 否 | `*.json` |
| `date` | 否 | 当天 `YYYYMMDD` |

## Commit Message

严格模板（Host 名与模型名**前后均带空格**）：

```text
Sync {machine_type} {model_name} Local Perf Result {DATE}
```

示例：`Sync SP_H200_3 Qwen2.5-7B Local Perf Result 2026-05-30`

- `{machine_type}` = SSH Host 名
- `{model_name}` = 远程目录 basename 或 JSON 字段推断
- `{DATE}` = `YYYY-MM-DD`

## Workflow

从仓库根目录执行。Windows 用 PowerShell + OpenSSH；Linux/macOS 用 bash。

### Step 0 — 确认计划

向用户展示：

- `connection`、`machine_type`
- `remote_path`（自动或指定）
- `local_path`、`files`、`date`

征得同意后继续。

### Step 1 — 同步 main

```powershell
git status --short --branch
git remote -v
git fetch origin main
git checkout main
git pull --ff-only origin main
```

- 核对 origin 指向 `vllm-omni-kanban`（fork 目录名可不同）
- 记录 pull 前后 `HEAD` commit hash

### Step 2 — SSH 连通与远程目录

**连通检查：**

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=10 {connection} "echo ok"
```

**默认最新含 JSON 目录**（远程执行）：

```bash
base=/rebase/vllm-omni/logs
find "$base" -mindepth 1 -maxdepth 2 -type f -name '*.json' -printf '%T@ %h\n' 2>/dev/null \
  | sort -rn | head -1 | awk '{print $2}'
```

`find -printf` 不可用时 fallback：

```bash
for d in $(ls -td "$base"/*/ 2>/dev/null); do
  ls "$d"*.json >/dev/null 2>&1 && echo "${d%/}" && break
done
```

用户指定 `remote_path` 时跳过自动选择，但仍校验目录存在且含目标文件。

### Step 3 — 推断 model_name

优先级：

1. 远程结果目录 basename（如 `Qwen2.5-7B-instruct`）
2. JSON 字段：`model`, `model_name`, `model_id`（读第一个匹配文件）
3. 仍无法确定 → 询问用户（阻塞 commit）

### Step 4 — 同步到本地

```powershell
New-Item -ItemType Directory -Force -Path {local_path}
scp {connection}:{remote_path}/{files} {local_path}/
```

同步后列出本地文件清单。

### Step 5 — Git commit（不 push）

```powershell
git status
git diff --stat
git add {local_path}
git commit -m "Sync {machine_type} {model_name} Local Perf Result {DATE}"
```

完成后提示：「已本地 commit，如需 push 到 main 请确认」。

### Step 6 — 汇报

输出：

- main 同步状态（pull 前后 commit hash）
- SSH Host / machine_type
- 远程路径（是否自动选取）
- model_name 来源
- 本地路径与文件数
- commit hash 与 message
- 是否 push

## Additional Resources

- SSH 配置、故障排查、用户描述解析：见 [reference.md](reference.md)

## Verification Checklist

```
- [ ] main 已与 origin/main fast-forward 一致
- [ ] SSH 连通成功
- [ ] 远程目录含目标 JSON
- [ ] 本地目录与文件数正确
- [ ] commit message 含 Host / 模型名前后空格
- [ ] 未自动 push
```
