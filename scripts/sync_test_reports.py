"""Sync HTML CI test reports from data/ into docs/assets/test_reports/ for MkDocs."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

_NIGHTLY_NAME_RE = re.compile(
    r"^nightly-report-buildkite-latest-(?P<date>\d{4}-\d{2}-\d{2})\.html$",
)
_RELEASE_NAME_RE = re.compile(
    r"^vllm-omni-release-test-report-(?P<date>\d{4}-\d{2}-\d{2})\.html$",
)


def _collect_report_dates(source_dir: Path, pattern: re.Pattern[str]) -> dict[str, Path]:
    """Map YYYY-MM-DD -> source HTML path (newest file wins if duplicates)."""
    out: dict[str, Path] = {}
    if not source_dir.is_dir():
        return out
    for path in sorted(source_dir.glob("*.html")):
        match = pattern.match(path.name)
        if not match:
            continue
        out[match.group("date")] = path
    return out


def _copy_if_changed(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if dest.stat().st_size == src.stat().st_size and dest.read_bytes() == src.read_bytes():
            return False
    shutil.copy2(src, dest)
    return True


def sync_test_reports(repo_root: Path) -> dict[str, list[str]]:
    """Copy nightly/release HTML reports and write manifest.json.

    Returns manifest payload (without generated_at) for testing.
    """
    nightly_src = repo_root / "data" / "nightly_test_report"
    release_src = repo_root / "data" / "release_test_report"
    assets_root = repo_root / "docs" / "assets" / "test_reports"

    nightly_dates = _collect_report_dates(nightly_src, _NIGHTLY_NAME_RE)
    release_dates = _collect_report_dates(release_src, _RELEASE_NAME_RE)

    for kind, mapping in (("nightly", nightly_dates), ("release", release_dates)):
        kind_dir = assets_root / kind
        kind_dir.mkdir(parents=True, exist_ok=True)
        expected = {f"{date}.html" for date in mapping}
        for stale in kind_dir.glob("*.html"):
            if stale.name not in expected:
                stale.unlink()
        for date, src in mapping.items():
            _copy_if_changed(src, kind_dir / f"{date}.html")

    payload = {
        "nightly": sorted(nightly_dates.keys(), reverse=True),
        "release": sorted(release_dates.keys(), reverse=True),
    }
    manifest = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        **payload,
    }
    assets_root.mkdir(parents=True, exist_ok=True)
    manifest_path = assets_root / "manifest.json"
    content = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    if not manifest_path.exists() or manifest_path.read_text(encoding="utf-8") != content:
        manifest_path.write_text(content, encoding="utf-8")
    return payload
