from __future__ import annotations

from pathlib import Path

import pytest

from scripts.sync_buildkite_raw_model_results import (
    dest_subdir_for_source,
    iter_source_files,
    main,
    sync_files,
    validate_model_name,
)


def test_validate_model_name_rejects_path_traversal() -> None:
    with pytest.raises(argparse_type_error_type()):
        validate_model_name("../evil")


def test_validate_model_name_accepts_qwen3omni() -> None:
    assert validate_model_name("qwen3omni") == "qwen3omni"


def argparse_type_error_type() -> type[Exception]:
    import argparse

    return argparse.ArgumentTypeError


def test_iter_source_files_filters_by_keywords(tmp_path: Path) -> None:
    raw = tmp_path / "buildkite_nightly_raw"
    (raw / "1000" / "tests" / "results").mkdir(parents=True)
    match = raw / "1000" / "tests" / "results" / "result_test_qwen3_omni_random_1_10_20260101-120000.json"
    match.write_text("{}", encoding="utf-8")
    other = raw / "1000" / "tests" / "results" / "result_test_other_1_10_20260101-120000.json"
    other.write_text("{}", encoding="utf-8")
    found = iter_source_files(raw, "qwen3_omni")
    assert found == [match]


def test_iter_source_files_includes_diffusion_result_json(tmp_path: Path) -> None:
    raw = tmp_path / "buildkite_nightly_raw"
    (raw / "1" / "perf").mkdir(parents=True)
    match = raw / "1" / "perf" / "diffusion_result_test_qwen_image_20260101-120000.json"
    match.write_text("[]", encoding="utf-8")
    found = iter_source_files(raw, "qwen_image")
    assert found == [match]


def test_iter_source_files_matches_basename_when_path_lacks_keyword(tmp_path: Path) -> None:
    raw = tmp_path / "buildkite_nightly_raw"
    (raw / "1000" / "tests" / "qwen3_omni" / "perf").mkdir(parents=True)
    match = raw / "1000" / "tests" / "qwen3_omni" / "perf" / "result_test_qwen3_tts_random_1_10_20260101-120000.json"
    match.write_text("{}", encoding="utf-8")
    noise = raw / "1000" / "tests" / "qwen3_omni" / "perf" / "result_test_qwen3_omni_random_1_10_20260101-120000.json"
    noise.write_text("{}", encoding="utf-8")
    found = iter_source_files(raw, "qwen3_tts")
    assert found == [match]


def test_dest_subdir_for_source_build_id_and_nogroup(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    p1 = raw / "42" / "result_test_qwen3_omni_random_1_10_20260101-120000.json"
    assert dest_subdir_for_source(p1, raw) == "42"
    p2 = raw / "main" / "result_test_qwen3_omni_random_1_10_20260101-120000.json"
    assert dest_subdir_for_source(p2, raw) == "_nogroup"


def test_sync_preserves_same_basename_across_build_dirs(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    low = raw / "1" / "result_test_qwen3_omni_random_1_10_20260101-120000.json"
    high = raw / "2" / "result_test_qwen3_omni_random_1_10_20260101-120000.json"
    low.parent.mkdir(parents=True)
    high.parent.mkdir(parents=True)
    low.write_text('{"a":1}', encoding="utf-8")
    high.write_text('{"a":2}', encoding="utf-8")
    dest = tmp_path / "out"
    n = sync_files(
        raw_root=raw,
        dest_dir=dest,
        model_keywords="qwen3_omni",
        dry_run=False,
        move=False,
        verbose=False,
    )
    assert n == 2
    assert (dest / "1" / low.name).read_text(encoding="utf-8") == '{"a":1}'
    assert (dest / "2" / high.name).read_text(encoding="utf-8") == '{"a":2}'


def test_main_dry_run_zero_when_raw_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "--model-name",
            "qwen3omni",
            "--model-keywords",
            "qwen3_omni",
            "--dry-run",
            "--raw-root",
            str(tmp_path / "missing"),
        ],
    )
    assert code == 0
