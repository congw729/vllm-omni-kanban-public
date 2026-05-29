# 同步本地性能结果 — 参考

## 目标仓库

| 名称 | 说明 |
|------|------|
| `vllm-omni-kanban` | 主仓（Skill 与 commit 逻辑统一使用此名） |
| `vllm-omni-kanban-public` | fork 开发目录，可接受 |

校验：`git remote -v` 中 origin URL 或本地目录名包含 `vllm-omni-kanban`。

## SSH Config 示例

`~/.ssh/config`：

```sshconfig
Host SP_H200_3
    HostName 10.0.0.3
    User ubuntu
    IdentityFile ~/.ssh/id_ed25519
```

- `Host` 别名 = `machine_type`，直接用于 commit message
- `BatchMode=yes` 要求已配置密钥，否则会失败

## 远程默认路径

```text
/rebase/vllm-omni/logs/
```

自动选择：该目录下（含子目录）**修改时间最新**且含 `*.json` 的目录。

列出候选目录：

```bash
ssh {connection} "ls -lt /rebase/vllm-omni/logs/"
```

## 用户描述解析

| 用户说法 | 处理 |
|----------|------|
| `/rebase/vllm-omni/logs/20260528/` | 当作 `remote_path` |
| 「最新」「recent」「上次跑的结果」 | 自动最新含 JSON 目录 |
| 「Qwen 那次」「5月28日」 | 列出远程子目录，用户确认后再同步 |

## model_name 推断

### 1. 目录 basename

`/rebase/vllm-omni/logs/qwen3-omni/run1/` → 取 `run1` 或上层 `qwen3-omni`，优先**直接含 JSON 的目录** basename。

### 2. JSON 字段

按顺序读取第一个 `*.json`：

```json
{ "model": "..." }
{ "model_name": "..." }
{ "model_id": "..." }
```

PowerShell 快速探测：

```powershell
Get-Content (Get-ChildItem {local_path}\*.json | Select-Object -First 1) -Raw | ConvertFrom-Json | Select-Object model, model_name, model_id
```

### 3. 仍无法确定

询问用户，阻塞 commit。

## Commit Message 空格规则

模板：

```text
Sync {machine_type} {model_name} Local Perf Result {DATE}
```

| 位置 | 要求 |
|------|------|
| `Sync` 后 | 一个空格 |
| Host 名后 | 一个空格 |
| 模型名后 | 一个空格（`Local` 前） |

正确：`Sync SP_H200_3 Qwen3-Omni Local Perf Result 2026-05-30`  
错误：`Sync SP_H200_3Qwen3-OmniLocal Perf Result 2026-05-30`

## main 预同步

### 脏工作区

`git status --short` 有输出时：

1. 若仅 `data/local_nightly_raw/` 下改动 → 可继续（先完成本次同步）
2. 若有其他未提交文件 → 暂停，提示 stash / commit / 放弃

### fast-forward 失败

```text
fatal: Not possible to fast-forward
```

可能原因：本地 main 有独有 commit 或与远程分叉。停止并报告，由用户决定 rebase / merge。

## 常见错误

| 现象 | 处理 |
|------|------|
| `Could not resolve hostname` | 检查 `~/.ssh/config` 中 Host 名 |
| `Permission denied (publickey)` | 配置密钥或 `ssh-agent` |
| 远程目录无 json | 列出 `logs/` 子目录，请用户指定 `remote_path` |
| `scp: No such file or directory` | 检查 `remote_path` 与 `files` glob |
| commit 含意外文件 | `git reset HEAD` 后重新 `git add` 仅目标路径 |

## Windows 前置条件

- OpenSSH 客户端（Windows 10+ 可选功能）
- `ssh`、`scp` 在 PATH 中
- Git for Windows

## 本地目录结构

默认：

```text
data/local_nightly_raw/manual_20260530/
├── result_test_qwen3_omni_....json
└── ...
```

用户可指定其他 `local_path`，Skill 会 `mkdir -p` 创建。
