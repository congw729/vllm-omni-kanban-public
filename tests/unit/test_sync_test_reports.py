from __future__ import annotations

from pathlib import Path

import pytest

from scripts.sync_test_reports import _copy_if_changed, sync_test_reports


def test_sync_test_reports_copies_and_manifest(tmp_path: Path) -> None:
    nightly_dir = tmp_path / "data" / "nightly_test_report"
    release_dir = tmp_path / "data" / "release_test_report"
    nightly_dir.mkdir(parents=True)
    release_dir.mkdir(parents=True)

    nightly_html = "<html><body>nightly</body></html>"
    release_html = "<html><body>release</body></html>"
    (nightly_dir / "nightly-report-buildkite-latest-2026-06-20.html").write_text(
        nightly_html,
        encoding="utf-8",
    )
    (nightly_dir / "nightly-report-buildkite-latest-2026-06-19.html").write_text(
        nightly_html,
        encoding="utf-8",
    )
    (release_dir / "vllm-omni-release-test-report-2026-06-03.html").write_text(
        release_html,
        encoding="utf-8",
    )
    (nightly_dir / "ignored.html").write_text("skip", encoding="utf-8")

    payload = sync_test_reports(tmp_path)

    assert payload["nightly"] == ["2026-06-20", "2026-06-19"]
    assert payload["release"] == ["2026-06-03"]

    assets = tmp_path / "docs" / "assets" / "test_reports"
    assert (assets / "nightly" / "2026-06-20.html").read_text(encoding="utf-8") == nightly_html
    assert (assets / "release" / "2026-06-03.html").read_text(encoding="utf-8") == release_html
    assert (assets / "manifest.json").exists()


def test_sync_test_reports_removes_stale_copies(tmp_path: Path) -> None:
    assets = tmp_path / "docs" / "assets" / "test_reports" / "nightly"
    assets.mkdir(parents=True)
    stale = assets / "2026-01-01.html"
    stale.write_text("old", encoding="utf-8")

    sync_test_reports(tmp_path)

    assert not stale.exists()


def test_sync_test_reports_empty_sources(tmp_path: Path) -> None:
    payload = sync_test_reports(tmp_path)
    assert payload == {"nightly": [], "release": []}


def test_copy_if_changed_skips_identical_files(tmp_path: Path) -> None:
    src = tmp_path / "src.html"
    dest = tmp_path / "dest.html"
    payload = b"<html>report</html>"
    src.write_bytes(payload)
    dest.write_bytes(payload)

    assert _copy_if_changed(src, dest) is False


def test_copy_if_changed_copies_when_size_differs(tmp_path: Path) -> None:
    src = tmp_path / "src.html"
    dest = tmp_path / "dest.html"
    src.write_bytes(b"updated-report")
    dest.write_bytes(b"old")

    assert _copy_if_changed(src, dest) is True
    assert dest.read_bytes() == b"updated-report"
