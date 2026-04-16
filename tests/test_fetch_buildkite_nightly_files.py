"""Tests for nightly sync artifact basename filter (no network)."""

from pathlib import PurePosixPath

import pytest

from scripts.fetch_buildkite_nightly_files import (
    _append_matching_builds_until_cap,
    append_resolved_build_github_output,
    build_matches_latest_nightly_criteria,
    first_matching_build_number,
    is_nightly_sync_artifact_basename,
)


@pytest.mark.parametrize(
    "name,expect",
    [
        ("result_test_qwen3_omni_random_1_10_20260308-182108.json", True),
        ("tests/dfx/perf/results/result_test_foo.json", True),
        ("result_test_qwen3_omni_random_1_10_20260308-182108.html", True),
        ("diffusion_result_test_qwen_image_vllm_omni_20260311-053632.json", True),
        ("diffusion_result_test_stem_20260311.html", True),
        ("diffusion_result_test_qwen_image_20260311-053632.json", True),
        ("benchmark_results_test_qwen_image_vllm_omni_20260311-053632.json", True),
        ("buildkite_testcase_statistics.html", False),
        ("summary_gebench.json", False),
        ("result_test_foo.txt", False),
        ("prefix_diffusion_result_x.json", False),
        ("random_report.html", False),
        ("result_test_x.htm", False),
    ],
)
def test_is_nightly_sync_artifact_basename(name: str, expect: bool) -> None:
    assert is_nightly_sync_artifact_basename(PurePosixPath(name).name) is expect


def test_build_matches_latest_nightly_criteria() -> None:
    b = {"state": "passed", "message": "Scheduled nightly build  #5575"}
    assert build_matches_latest_nightly_criteria(b, message_contains="Scheduled nightly build", require_state="passed")
    assert not build_matches_latest_nightly_criteria(b, message_contains="Scheduled nightly build", require_state="failed")
    assert not build_matches_latest_nightly_criteria(
        {"state": "passed", "message": "manual"}, message_contains="Scheduled nightly build", require_state="passed"
    )
    assert build_matches_latest_nightly_criteria(
        {"state": "failed", "message": "Scheduled nightly build"}, message_contains="Scheduled nightly build", require_state=None
    )


def test_first_matching_build_number_order() -> None:
    builds = [
        {"number": 1, "state": "passed", "message": "other"},
        {"number": 5575, "state": "passed", "message": "Scheduled nightly build  #5575"},
        {"number": 5574, "state": "passed", "message": "Scheduled nightly build  #5574"},
    ]
    found = first_matching_build_number(
        builds, message_contains="Scheduled nightly build", require_state="passed"
    )
    assert found == "5575"


def test_append_resolved_build_github_output(tmp_path, monkeypatch) -> None:
    gh_out = tmp_path / "github_output.txt"
    gh_out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    append_resolved_build_github_output(build_no="5575", commit="deadbeef", web_url="https://buildkite.com/build/5575")
    text = gh_out.read_text(encoding="utf-8")
    assert "resolved_build_number=5575\n" in text
    assert "resolved_commit=deadbeef\n" in text
    assert "resolved_build_url=https://buildkite.com/build/5575\n" in text


def test_append_resolved_build_github_output_skips_without_env(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    append_resolved_build_github_output(build_no="1", commit="", web_url="")


def test_append_matching_builds_until_cap_respects_order_and_cap() -> None:
    out: list = []
    page = [
        {"number": 10, "state": "passed", "message": "Scheduled nightly build  #10"},
        {"number": 9, "state": "passed", "message": "manual"},
        {"number": 8, "state": "passed", "message": "Scheduled nightly build  #8"},
    ]
    _append_matching_builds_until_cap(
        out,
        page,
        message_contains="Scheduled nightly build",
        require_state="passed",
        cap=5,
    )
    assert [b["number"] for b in out] == [10, 8]
    out2: list = []
    _append_matching_builds_until_cap(
        out2,
        page + [{"number": 7, "state": "passed", "message": "Scheduled nightly build  #7"}],
        message_contains="Scheduled nightly build",
        require_state="passed",
        cap=2,
    )
    assert [b["number"] for b in out2] == [10, 8]
