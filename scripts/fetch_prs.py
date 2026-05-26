"""Fetch merged PRs from a local clone of vllm-omni via `git log` / `git show`.

Bucketing logic (per-page dedup):
- `direct`   = PR's changed-file paths match any glob in mapping['models'][<model>]
- `inferred` = no direct match, but title's bracketed prefix matches a tag in mapping['title_tags'][<model>]
- `platform` = no direct or inferred, but at least one changed file matches platform_paths
- None       = otherwise (PR not shown on this model's page)

Direct supersedes inferred globally and platform on the same page.

Source repo location:
- CLI: `python -m scripts.fetch_prs <path-to-local-clone>`
- Env: `CODE_REPO_PATH=/path/to/vllm-omni python -m scripts.fetch_prs`
- Default: `.cache/vllm-omni/` (where `dashboard-sync.yml` clones it in CI;
  for local dev, set CODE_REPO_PATH or pass the path as the first CLI arg).
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

PR_SUFFIX_RE = re.compile(r"\(#(\d+)\)\s*$")
TAG_PREFIX_RE = re.compile(r"\[([^\]]+)\]")
RETENTION_DAYS = 90
GIT_LOG_SEP = "\x1f"  # ASCII unit separator — safe for git pretty format
GIT_RECORD_SEP = "\x1e"  # ASCII record separator


def extract_pr_number(subject: str) -> int | None:
    """Return the trailing `(#NNNN)` PR number from a commit subject line, else None."""
    first = subject.splitlines()[0] if subject else ""
    m = PR_SUFFIX_RE.search(first)
    return int(m.group(1)) if m else None


def _match_any(path: str, globs: list[str]) -> bool:
    """Return True if `path` matches any of the `globs` (supports trailing `/**`)."""
    for g in globs:
        if "/**" in g:
            base = g.split("/**")[0]
            if path == base or path.startswith(base + "/"):
                return True
        elif fnmatch.fnmatch(path, g):
            return True
    return False


def _title_tag_match(title: str, tags: list[str]) -> bool:
    """Return True if any bracketed prefix in `title` matches a tag (case-insensitive)."""
    prefixes = [m.lower() for m in TAG_PREFIX_RE.findall(title)]
    return any(t.lower() in prefixes for t in tags)


def bucket_pr_for_model(
    pr: dict[str, Any], kanban_model_name: str, mapping: dict[str, Any]
) -> str | None:
    """Return 'direct', 'inferred', 'platform', or None for this (PR, model) pair.

    Priority (highest to lowest):
      1. direct   — any changed file matches model globs
      2. inferred — title bracketed prefix matches a title_tag alias
      3. platform — any changed file matches platform_paths globs
      4. None     — no signal found
    """
    model_globs: list[str] = mapping.get("models", {}).get(kanban_model_name, [])
    platform_globs: list[str] = mapping.get("platform_paths", [])
    tags: list[str] = mapping.get("title_tags", {}).get(kanban_model_name, [])
    title: str = pr.get("title", "")
    files: list[str] = pr.get("files", [])

    if model_globs and any(_match_any(f, model_globs) for f in files):
        return "direct"
    if tags and _title_tag_match(title, tags):
        return "inferred"
    if platform_globs and any(_match_any(f, platform_globs) for f in files):
        return "platform"
    return None


def _git(repo_path: Path, *args: str) -> str:
    """Run `git -C <repo_path> <args>` and return stdout. Raises on non-zero exit."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def fetch_prs_via_git(
    repo_path: Path,
    since_days: int = RETENTION_DAYS,
    *,
    pr_url_base: str | None = None,
) -> list[dict[str, Any]]:
    """Walk the local clone's commit log and produce one PR dict per squash-merge commit.

    Schema per PR: {number, title, author, merged_at (ISO), url, files (list)}.
    If `pr_url_base` is given, all PR URLs are built as `<pr_url_base>/<number>`.
    Otherwise, derived from the repo's `origin` remote.
    """
    if not (repo_path / ".git").exists():
        raise FileNotFoundError(f"Not a git repo: {repo_path}")

    if pr_url_base is None:
        try:
            origin = _git(repo_path, "config", "--get", "remote.origin.url").strip()
        except subprocess.CalledProcessError:
            origin = "https://github.com/hsliuustc0106/vllm-omni.git"
        url_base = _origin_to_pr_url_base(origin)
    else:
        url_base = pr_url_base.rstrip("/")

    # Single git invocation: log + per-commit changed files in one stream.
    # `--name-only` after `--pretty=format:...` interleaves filenames between
    # commit headers, separated by blank lines. Roughly 100x faster than the
    # N+1 `git show` per commit (Gemini reviewer flagged the original).
    pretty = f"--pretty=format:{GIT_RECORD_SEP}%H{GIT_LOG_SEP}%an{GIT_LOG_SEP}%aI{GIT_LOG_SEP}%s"
    log_out = _git(
        repo_path,
        "log",
        f"--since={since_days}.days.ago",
        "--name-only",
        pretty,
    )

    prs: list[dict[str, Any]] = []
    for chunk in log_out.split(GIT_RECORD_SEP):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        # First line is the metadata; remaining non-empty lines are filenames.
        lines = chunk.split("\n")
        header_parts = lines[0].split(GIT_LOG_SEP)
        if len(header_parts) != 4:
            continue
        _sha, author, date_iso, subject = header_parts
        pr_num = extract_pr_number(subject)
        if pr_num is None:
            continue
        files = [ln for ln in lines[1:] if ln.strip()]
        prs.append(
            {
                "number": pr_num,
                "title": subject,
                "author": author,
                "merged_at": date_iso,
                "url": f"{url_base}/{pr_num}",
                "files": files,
            }
        )
    return prs


def _origin_to_pr_url_base(origin: str) -> str:
    """Convert any git remote URL form to `https://github.com/<owner>/<repo>/pull`."""
    # Strip trailing .git
    s = origin.removesuffix(".git")
    # ssh form: git@github.com:owner/repo
    if s.startswith("git@"):
        host_path = s.split("@", 1)[1]
        host, _, path = host_path.partition(":")
        return f"https://{host}/{path}/pull"
    # https form: https://github.com/owner/repo
    return f"{s}/pull"


def _build_per_model_payloads(
    prs: list[dict[str, Any]], identity: dict[str, Any], mapping: dict[str, Any]
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Build per-model bucketed PR lists from a flat list of PR dicts."""
    out: dict[str, dict[str, list[dict[str, Any]]]] = {
        m["id"]: {"direct": [], "inferred": [], "platform": []} for m in identity["models"]
    }
    for pr in prs:
        for model in identity["models"]:
            bucket = bucket_pr_for_model(pr, model["kanban_name"], mapping)
            if bucket is None:
                continue
            row: dict[str, Any] = {
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["author"],
                "merged_at": pr["merged_at"],
                "url": pr["url"],
            }
            if bucket == "direct":
                matched_globs = mapping["models"][model["kanban_name"]]
                row["files_matched"] = [f for f in pr["files"] if _match_any(f, matched_globs)]
            elif bucket == "platform":
                row["platform_paths"] = [
                    f for f in pr["files"] if _match_any(f, mapping["platform_paths"])
                ]
            elif bucket == "inferred":
                row["tag_matched"] = model["kanban_name"]
            out[model["id"]][bucket].append(row)
    for buckets in out.values():
        for b in buckets.values():
            b.sort(key=lambda r: str(r["merged_at"]), reverse=True)
    return out


def _resolve_repo_path() -> Path:
    """Resolve the local vllm-omni clone path from CLI arg, env var, or CI default.

    Resolution order:
      1. First CLI arg (e.g. `python -m scripts.fetch_prs /path/to/clone`)
      2. `CODE_REPO_PATH` env var
      3. `.cache/vllm-omni/` relative to the current working directory
         (this is where `dashboard-sync.yml` clones it)
    """
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        return Path(sys.argv[1]).expanduser().resolve()
    if env := os.environ.get("CODE_REPO_PATH"):
        return Path(env).expanduser().resolve()
    default = Path(".cache/vllm-omni")
    if (default / ".git").exists():
        return default
    raise FileNotFoundError(
        "No local vllm-omni clone found. Pass a path as the first arg, "
        "set CODE_REPO_PATH, or clone it to .cache/vllm-omni."
    )


def main(repo_root: Path | None = None) -> int:
    """Entry point: read PR data via local git, bucket per model, write per-model JSON feeds."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
    root = repo_root or Path(__file__).resolve().parent.parent

    identity = json.loads((root / "dashboard/src/data/identity.json").read_text(encoding="utf-8"))
    mapping = yaml.safe_load((root / "scripts/pr_mapping.yml").read_text(encoding="utf-8"))
    pr_url_base = mapping.get("sources", {}).get("pr_url_base")

    code_repo_path = _resolve_repo_path()
    log.info(
        "reading PRs from %s (last %d days) — linking to %s",
        code_repo_path,
        RETENTION_DAYS,
        pr_url_base or "<repo origin>",
    )

    prs = fetch_prs_via_git(
        code_repo_path,
        since_days=RETENTION_DAYS,
        pr_url_base=pr_url_base,
    )
    log.info("collected %d PRs from git log", len(prs))

    per_model = _build_per_model_payloads(prs, identity, mapping)
    out_dir = root / "dashboard/src/data/prs/per_model"
    out_dir.mkdir(parents=True, exist_ok=True)
    for model in identity["models"]:
        payload = {"model_id": model["id"], **per_model[model["id"]]}
        (out_dir / f"{model['id']}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    coverage_direct = sum(len(b["direct"]) for b in per_model.values())
    coverage_inferred = sum(len(b["inferred"]) for b in per_model.values())
    coverage_platform = sum(len(b["platform"]) for b in per_model.values())
    stats = {
        "last_updated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_prs_indexed_90d": len(prs),
        "attribution_coverage": {
            "direct": coverage_direct,
            "inferred_only": coverage_inferred,
            "platform": coverage_platform,
        },
        "truncated": False,
    }
    (root / "dashboard/src/data/prs/stats.json").write_text(
        json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    log.info(
        "wrote PR feeds for %d models; %d total PRs (direct=%d inferred=%d platform=%d)",
        len(identity["models"]),
        len(prs),
        coverage_direct,
        coverage_inferred,
        coverage_platform,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
