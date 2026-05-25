---
name: update-main-docs
description: Update the main branch, activate the uv-managed Python environment, and start a local MkDocs preview server. Use when the user asks to refresh main, run mkdocs serve, preview the documentation site, or start the local docs server for this project.
---

# Update Main Docs

## Purpose

Use this skill to update the repository's `main` branch safely, activate the project's Python environment, and start the MkDocs development server for the documentation site.

## Environment

This project uses `uv` to manage the default Python environment.
Before running project commands, activate the default environment:

```bash
source .venv/bin/activate
```

If the user specifies another environment name or path, use that activation command instead of `.venv`.

## Safety Rules

1. Ask for explicit approval before running commands.
2. Check the current branch and working tree before changing branches or pulling.
3. If `git status --short` reports any changes, stop and ask how to proceed. Do not stash, reset, overwrite, merge, or rebase automatically.
4. Activate the selected Python environment before running project commands.
5. Use fast-forward-only updates for `main`.
6. Check for an existing `mkdocs serve` process or active terminal before starting a new server.
7. If a command fails, report the exact failing step and stop unless the next action is clearly safe and approved.

## Workflow

Run commands from the repository root.

```bash
git status --short --branch
source .venv/bin/activate
git fetch origin main
git switch main
git pull --ff-only origin main
```

If `git status --short` reports changes, stop before switching branches or pulling.
If `git pull --ff-only` fails, stop. Do not merge or rebase automatically.

Before starting the server, check whether `mkdocs serve` is already running. If no server is running, start it in the active environment:

```bash
mkdocs serve
```

The local preview is usually available at:

```text
http://127.0.0.1:8000/
```

## Dependency Handling

This project stores MkDocs dependencies in `requirements.txt`. If `mkdocs` is missing or the server fails because dependencies are unavailable, ask for approval before installing into the active environment:

```bash
python -m pip install -r requirements.txt
```

Then retry `mkdocs serve`.

## Port Conflicts

If port `8000` is already in use, report the conflict and ask whether to reuse the existing server, stop it, or start MkDocs on another port:

```bash
mkdocs serve -a 127.0.0.1:8001
```

