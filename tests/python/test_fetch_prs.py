"""Tests for scripts.fetch_prs (git-subprocess based)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.fetch_prs import (
    _build_per_model_payloads,
    _origin_to_pr_url_base,
    bucket_pr_for_model,
    extract_pr_number,
    fetch_prs_via_git,
)


def test_extract_pr_number_squash_suffix() -> None:
    assert extract_pr_number("[Qwen3-Omni] fix audio chunk EOS (#3814)") == 3814
    assert extract_pr_number("Refactor (#1)") == 1
    assert extract_pr_number("no pr number here") is None
    assert extract_pr_number("multi-line\n(#999)") is None  # only first line considered


def test_origin_to_pr_url_base_https() -> None:
    assert (
        _origin_to_pr_url_base("https://github.com/hsliuustc0106/vllm-omni.git")
        == "https://github.com/hsliuustc0106/vllm-omni/pull"
    )
    assert (
        _origin_to_pr_url_base("https://github.com/hsliuustc0106/vllm-omni")
        == "https://github.com/hsliuustc0106/vllm-omni/pull"
    )


def test_origin_to_pr_url_base_ssh() -> None:
    assert (
        _origin_to_pr_url_base("git@github.com:hsliuustc0106/vllm-omni.git")
        == "https://github.com/hsliuustc0106/vllm-omni/pull"
    )


def _mapping() -> dict[str, Any]:
    return yaml.safe_load("""
models:
  Qwen3-Omni:
    - "vllm_omni/model_executor/models/qwen3_omni/**"
platform_paths:
  - "vllm_omni/scheduler/**"
title_tags:
  Qwen3-Omni: ["qwen3-omni", "qwen3omni"]
sources: {kanban_repo: x, code_repo: y}
""")


def test_bucket_direct_match() -> None:
    pr = {
        "title": "[Qwen3-Omni] fix",
        "files": ["vllm_omni/model_executor/models/qwen3_omni/output.py"],
    }
    assert bucket_pr_for_model(pr, "Qwen3-Omni", _mapping()) == "direct"


def test_bucket_platform_when_no_direct() -> None:
    pr = {"title": "[Scheduler] swap", "files": ["vllm_omni/scheduler/policy.py"]}
    assert bucket_pr_for_model(pr, "Qwen3-Omni", _mapping()) == "platform"


def test_bucket_inferred_when_only_title_tag() -> None:
    pr = {"title": "[Qwen3-Omni] doc-only", "files": ["docs/models/qwen3_omni.md"]}
    assert bucket_pr_for_model(pr, "Qwen3-Omni", _mapping()) == "inferred"


def test_bucket_none_when_no_signal() -> None:
    pr = {"title": "random change", "files": ["README.md"]}
    assert bucket_pr_for_model(pr, "Qwen3-Omni", _mapping()) is None


def test_per_page_dedup_direct_suppresses_platform() -> None:
    # On Qwen3-Omni's page, a PR touching BOTH qwen3_omni AND scheduler must be `direct`, not `platform`.
    pr = {
        "title": "[Qwen3-Omni][Scheduler] joint fix",
        "files": [
            "vllm_omni/model_executor/models/qwen3_omni/output.py",
            "vllm_omni/scheduler/policy.py",
        ],
    }
    assert bucket_pr_for_model(pr, "Qwen3-Omni", _mapping()) == "direct"


def test_build_per_model_payloads_groups_correctly() -> None:
    identity = {
        "models": [
            {
                "id": "qwen3-omni",
                "kanban_name": "Qwen3-Omni",
                "display_name": "Qwen3 Omni",
                "slug": "qwen3-omni",
                "category": "multimodal",
            }
        ],
        "hardware": [],
    }
    mapping = _mapping()
    prs = [
        {
            "number": 1,
            "title": "[Qwen3-Omni] direct hit",
            "author": "alice",
            "merged_at": "2026-05-20T00:00:00Z",
            "url": "u/1",
            "files": ["vllm_omni/model_executor/models/qwen3_omni/x.py"],
        },
        {
            "number": 2,
            "title": "[Scheduler] platform",
            "author": "bob",
            "merged_at": "2026-05-21T00:00:00Z",
            "url": "u/2",
            "files": ["vllm_omni/scheduler/p.py"],
        },
        {
            "number": 3,
            "title": "unrelated",
            "author": "eve",
            "merged_at": "2026-05-22T00:00:00Z",
            "url": "u/3",
            "files": ["README.md"],
        },
    ]
    out = _build_per_model_payloads(prs, identity, mapping)
    assert len(out["qwen3-omni"]["direct"]) == 1
    assert out["qwen3-omni"]["direct"][0]["number"] == 1
    assert out["qwen3-omni"]["direct"][0]["files_matched"] == [
        "vllm_omni/model_executor/models/qwen3_omni/x.py"
    ]
    assert len(out["qwen3-omni"]["platform"]) == 1
    assert out["qwen3-omni"]["platform"][0]["number"] == 2
    assert out["qwen3-omni"]["inferred"] == []
    # PR #3 has no signal → not present anywhere
    all_numbers = {r["number"] for bucket in out["qwen3-omni"].values() for r in bucket}
    assert 3 not in all_numbers


def test_fetch_prs_via_git_against_tiny_repo(tmp_path: Path) -> None:
    """Stand up a 2-commit git repo and verify the parser extracts PR metadata correctly."""
    repo = tmp_path / "tiny"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
        cwd=repo,
        check=True,
    )
    (repo / "a.py").write_text("x\n")
    subprocess.run(["git", "add", "a.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "[Feat] first thing (#100)"], cwd=repo, check=True)
    (repo / "b.py").write_text("y\n")
    subprocess.run(["git", "add", "b.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "second thing without PR number"],
        cwd=repo,
        check=True,
    )

    prs = fetch_prs_via_git(repo, since_days=1)
    assert len(prs) == 1
    assert prs[0]["number"] == 100
    assert prs[0]["title"] == "[Feat] first thing (#100)"
    assert prs[0]["author"] == "Tester"
    assert prs[0]["url"] == "https://github.com/test/repo/pull/100"
    assert prs[0]["files"] == ["a.py"]
    assert prs[0]["merged_at"].startswith("20")  # any ISO date


def test_fetch_prs_via_git_raises_on_non_repo(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Not a git repo"):
        fetch_prs_via_git(tmp_path, since_days=1)
