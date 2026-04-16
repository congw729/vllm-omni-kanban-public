"""MkDocs hooks: sync Buildkite raw JSON into data/results, then regenerate charts.

Uses on_startup (not on_pre_build) so writes under docs/assets/charts/ do not
re-trigger livereload in an endless loop; generate_charts updates generated_at every run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# (model_name subdirectory under data/results/, keyword matching path or basename under buildkite_nightly_raw)
_BUILDKITE_RAW_SYNCS: tuple[tuple[str, str], ...] = (
    ("qwen3omni", "qwen3_omni"),
    ("qwen3tts", "qwen3_tts"),
    ("qwen_image", "qwen_image"),
)


def on_startup(command: str, dirty: bool, **kwargs) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    sync_script = repo_root / "scripts" / "sync_buildkite_raw_model_results.py"
    for model_name, model_keywords in _BUILDKITE_RAW_SYNCS:
        proc = subprocess.run(
            [
                sys.executable,
                str(sync_script),
                "--model-name",
                model_name,
                "--model-keywords",
                model_keywords,
            ],
            cwd=str(repo_root),
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"sync_buildkite_raw_model_results.py ({model_name}) exited with status {proc.returncode}",
            )

    gen_script = repo_root / "scripts" / "generate_charts.py"
    proc = subprocess.run(
        [sys.executable, str(gen_script)],
        cwd=str(repo_root),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"generate_charts.py exited with status {proc.returncode}")
