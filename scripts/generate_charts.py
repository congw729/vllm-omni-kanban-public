from __future__ import annotations

import json
import math
import os
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import flatten_metrics, load_json, parse_log_metric_tables, save_json

DATA_DIR = ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"
INDEX_PATH = DATA_DIR / "index.json"
CONFIG_PATH = DATA_DIR / "config.json"
FRAMEWORK_COMPARISON_INPUT_DIR = DATA_DIR / "framework_comparison"
SGLANG_DIFFUSION_RESULTS_DIR = DATA_DIR / "sglang_diffusion_results"
SGLANG_DIFFUSION_RESULTS_ENV = "SGLANG_DIFFUSION_RESULTS_DIR"
SGLANG_LOG_DIR = Path(os.environ.get("SGLANG_LOG_DIR", str(DATA_DIR / "sglang-log")))
CHARTS_DIR = ROOT / "docs" / "assets" / "charts"
QWEN3_OMNI_HISTORY_PATH = CHARTS_DIR / "qwen3_omni_history.json"
QWEN3_TTS_HISTORY_PATH = CHARTS_DIR / "qwen3_tts_history.json"
QWEN_IMAGE_HISTORY_PATH = CHARTS_DIR / "qwen_image_history.json"
QWEN_IMAGE_LAYERED_HISTORY_PATH = CHARTS_DIR / "qwen_image_layered_history.json"
QWEN_IMAGE_EDIT_HISTORY_PATH = CHARTS_DIR / "qwen_image_edit_history.json"
QWEN_IMAGE_EDIT_2509_HISTORY_PATH = CHARTS_DIR / "qwen_image_edit_2509_history.json"
QWEN_IMAGE_EDIT_2511_HISTORY_PATH = CHARTS_DIR / "qwen_image_edit_2511_history.json"
WAN22_HISTORY_PATH = CHARTS_DIR / "wan22_history.json"
HUNYUAN_IMAGE3_HISTORY_PATH = CHARTS_DIR / "hunyuan_image3_history.json"
HUNYUAN_IMAGE3_ACCURACY_PATH = CHARTS_DIR / "hunyuan_image3_accuracy.json"
LOCAL_RAW_DIR = DATA_DIR / "local_nightly_raw"
BAGEL_HISTORY_PATH = CHARTS_DIR / "bagel_history.json"
VOXCPM2_HISTORY_PATH = CHARTS_DIR / "voxcpm2_history.json"
FRAMEWORK_COMPARISON_PATH = CHARTS_DIR / "framework_comparison.json"
HIGGS_AUDIO_V3_HISTORY_PATH = CHARTS_DIR / "higgs_audio_v3_history.json"
DEFAULT_RESULT_DATASETS = frozenset({"random", "random-mm"})
QWEN3_OMNI_DATASETS = set(DEFAULT_RESULT_DATASETS)  # backward compat
QWEN3_OMNI_GROUP_FIELDS = (
    "endpoint_type",
    "backend",
    "model_id",
    "tokenizer_id",
    "test_name",
    "dataset_name",
    "random_input_len",
    "random_output_len",
    "max_concurrency",
    "num_prompts",
    # Same CI scenario can emit two rows differing only by whether audio RTF/TTFP/duration metrics exist.
    # Without this dimension, frontend line charts merge them and latest-per-day hides the other path.
    "omni_metrics_profile",
)
QWEN3_TTS_GROUP_FIELDS = (
    "endpoint_type",
    "backend",
    "model_id",
    "tokenizer_id",
    "test_name",
    "dataset_name",
    "max_concurrency",
    "num_prompts",
)
QWEN_IMAGE_GROUP_FIELDS = (
    "test_name",
    "backend",
    "hardware",
    "model_id",
    "benchmark_name",
    "dataset_name",
    "max_concurrency",
    "num_prompts",
)
HUNYUAN_ACCURACY_GROUP_FIELDS = (
    "test_file",
    "test_name",
)
FRAMEWORK_COMPARISON_DIMENSIONS = (
    "model_family",
    "model_id",
    "workload_profile",
    "task",
    "dataset_name",
    "endpoint",
    "hardware",
    "width",
    "height",
    "num_inference_steps",
    "num_input_images",
    "max_concurrency",
    "num_prompts",
    "random_input_len",
    "random_output_len",
    "omni_metrics_profile",
)
FRAMEWORK_COMPARISON_TABLE_COLUMNS = [
    "date",
    "model_family",
    "model_id",
    "framework",
    "backend",
    "endpoint",
    "hardware",
    "test_name",
    "task",
    "dataset_name",
    "benchmark_name",
    "width",
    "height",
    "num_inference_steps",
    "num_input_images",
    "max_concurrency",
    "num_prompts",
    "random_input_len",
    "random_output_len",
    "latency_mean_s",
    "latency_p50_s",
    "latency_p99_s",
    "throughput_qps",
    "peak_memory_mb_max",
    "source_format",
    "source_file",
    "source_run_id",
    "mean_ttft_ms",
    "mean_tpot_ms",
    "mean_e2el_ms",
    "mean_audio_rtf",
    "mean_audio_ttfp_ms",
    "output_throughput",
    "total_token_throughput",
    "e2e_latency_ms",
    "peak_memory_gb",
]
FRAMEWORK_COMPARISON_METRIC_GROUPS = [
    {"id": "latency", "title": "Latency", "metrics": ["latency_mean_s", "latency_p50_s", "latency_p99_s"]},
    {"id": "throughput", "title": "Throughput", "metrics": ["throughput_qps", "output_throughput", "total_token_throughput"]},
    {"id": "memory", "title": "Peak Memory", "metrics": ["peak_memory_mb_max", "peak_memory_gb"]},
    {"id": "ttft", "title": "TTFT", "metrics": ["mean_ttft_ms"]},
    {"id": "tpot", "title": "TPOT", "metrics": ["mean_tpot_ms"]},
    {"id": "e2e", "title": "E2E Latency", "metrics": ["mean_e2el_ms", "e2e_latency_ms"]},
    {"id": "audio_rtf", "title": "Audio RTF", "metrics": ["mean_audio_rtf"]},
    {"id": "audio_ttfp", "title": "Audio TTFP", "metrics": ["mean_audio_ttfp_ms"]},
]
SGLANG_LOG_MODEL_MAP = {
    "qwen-image-sglang-test.log": ("Qwen Image", "Qwen/Qwen-Image"),
    "qwen-image-edit-sglang-test.log": ("Qwen Image Edit", "Qwen/Qwen-Image-Edit"),
    "qwen-image-edit-2511-sglang-test.log": ("Qwen Image Edit 2511", "Qwen/Qwen-Image-Edit-2511"),
}
SGLANG_DIFFUSION_MODEL_FAMILY_MAP = {
    "Qwen/Qwen-Image": "Qwen Image",
    "Qwen/Qwen-Image-Edit": "Qwen Image Edit",
    "Qwen/Qwen-Image-Edit-2511": "Qwen Image Edit 2511",
}
MODEL_COMPARE_PAGE_TARGETS = [
    ("Qwen Image", "models/qwen-image/"),
    ("Qwen Image Edit", "models/qwen-image-edit/"),
    ("Qwen Image Edit 2511", "models/qwen-image-edit-2511/"),
]
WORKLOAD_KEY_FIELDS = (
    "model_family",
    "model_id",
    "workload_profile",
    "task",
    "dataset_name",
    "endpoint",
    "hardware",
    "width",
    "height",
    "num_inference_steps",
    "num_input_images",
    "max_concurrency",
    "num_prompts",
)
MODEL_METRICS = {
    "Qwen3-Omni": [
        ("ttft_ms", None, None),
        ("tpot_ms", None, None),
        ("ttfp_ms", None, None),
        ("real_time_factor", None, None),
        ("throughput_tokens_per_sec", None, None),
    ],
    "Qwen3-TTS": [
        ("ttft_ms", None, None),
        ("tpot_ms", None, None),
        ("ttfp_ms", None, None),
        ("real_time_factor", None, None),
        ("throughput_tokens_per_sec", None, None),
    ],
    "Qwen-image": [
        ("e2e_latency_ms", None, None),
        ("peak_memory_gb", None, None),
    ],
    "Qwen-Image-edit": [
        ("e2e_latency_ms", None, None),
        ("peak_memory_gb", None, None),
    ],
    "Qwen-Image-edit-2509": [
        ("e2e_latency_ms", None, None),
        ("peak_memory_gb", None, None),
    ],
    "Qwen-Image-edit-2511": [
        ("e2e_latency_ms", None, None),
        ("peak_memory_gb", None, None),
    ],
    "WAN2.2": [
        ("e2e_latency_ms", None, None),
        ("peak_memory_gb", None, None),
    ],
    "Hunyuan-Image3": [
        ("e2e_latency_ms", None, None),
        ("peak_memory_gb", None, None),
    ],
    "BAGEL": [
        ("e2e_latency_ms", None, None),
        ("peak_memory_gb", None, None),
    ],
    "VoxCPM2": [
        ("ttfp_ms", None, None),
        ("real_time_factor", None, None),
        ("throughput_tokens_per_sec", None, None),
    ],
    "Higgs-Audio-V3": [
        ("ttfp_ms", None, None),
        ("real_time_factor", None, None),
        ("throughput_tokens_per_sec", None, None),
    ],
}
RANGE_WINDOWS = {"1d": 1, "7d": 7, "30d": 30}


def save_chart(name: str, option: dict[str, Any]) -> None:
    save_json(CHARTS_DIR / f"{name}.json", option)


def average_metric(results: list[dict[str, Any]], metric: str) -> float | None:
    values = [value for result in results if isinstance((value := flatten_metrics(result["metrics"]).get(metric)), (int, float))]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def chart_slug(value: str) -> str:
    return value.lower().replace(".", "").replace(" ", "_").replace("-", "_")


def _strip_io_length_suffix_before_timestamp(name: str) -> str:
    """Strip _in*_out*_ before the trailing _YYYYMMDD-HHMMSS segment.

    Matches numeric IO lengths (_in100_out100) and TTS-style placeholders (_inna_outna).
    """
    return re.sub(r"_in[^_]+_out[^_]+(?=_\d{8}-\d{6}$)", "", name)


def parse_result_test_filename(
    path: Path,
    dataset_allowlist: frozenset[str] | set[str] | None = None,
) -> dict[str, Any] | None:
    allow = frozenset(dataset_allowlist) if dataset_allowlist is not None else DEFAULT_RESULT_DATASETS
    stem = path.stem
    prefix = "result_test_"
    if not stem.startswith(prefix):
        return None
    middle = _strip_io_length_suffix_before_timestamp(stem[len(prefix) :])
    parts = middle.split("_")
    if len(parts) < 5:
        return None
    timestamp = parts[-1]
    try:
        parsed_ts = datetime.strptime(timestamp, "%Y%m%d-%H%M%S")
        num_prompts = int(parts[-2])
    except ValueError:
        return None

    mc_token = parts[-3]
    try:
        max_concurrency = int(mc_token)
    except ValueError:
        try:
            float(mc_token)
        except ValueError:
            return None
        max_concurrency = None

    dataset_name = parts[-4]
    test_name = "_".join(parts[:-4])
    if not test_name:
        return None
    if dataset_name not in allow:
        dataset_name = ""

    return {
        "test_name": test_name,
        "dataset_name": dataset_name,
        "max_concurrency": max_concurrency,
        "num_prompts": num_prompts,
        "timestamp_key": timestamp,
        "sort_timestamp": parsed_ts.isoformat(),
        "date": parsed_ts.strftime("%Y-%m-%d %H:%M:%S"),
    }


def parse_qwen3_omni_filename(path: Path) -> dict[str, Any] | None:
    return parse_result_test_filename(path, DEFAULT_RESULT_DATASETS)


def infer_omni_metrics_profile(payload: dict[str, Any]) -> str:
    """Label for chart grouping: audio-series present vs text-oriented aggregate only.

    Nightly payloads may include two measurements for an otherwise identical workload
    (endpoint, concurrency, prompts, lengths) where only one fills ``mean_audio_rtf`` /
    TTFP / audio duration columns. Previously they shared one series key and
    ``pickLatestPerCalendarDay`` kept only the latest timestamp.
    """

    probe_keys = (
        "mean_audio_rtf",
        "median_audio_rtf",
        "p99_audio_rtf",
        "mean_audio_ttfp_ms",
        "median_audio_ttfp_ms",
        "p99_audio_ttfp_ms",
        "mean_audio_duration_s",
        "median_audio_duration_s",
        "p99_audio_duration_s",
    )
    for key in probe_keys:
        raw = payload.get(key)
        if isinstance(raw, (int, float)) and math.isfinite(float(raw)):
            return "audio_metrics"
        if isinstance(raw, str) and raw.strip():
            try:
                val = float(raw)
            except ValueError:
                continue
            if math.isfinite(val):
                return "audio_metrics"
    return "text_only_metrics"


def load_result_test_history(
    source_dir: Path,
    dataset_allowlist: frozenset[str] | set[str] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(source_dir.rglob("result_test_*.json")):
        parsed = parse_result_test_filename(path, dataset_allowlist)
        if parsed is None:
            continue
        payload = load_json(path, {})
        if not isinstance(payload, dict):
            continue
        merged = {**payload, **parsed}
        record: dict[str, Any] = {
            "source_file": path.name,
            **payload,
            **parsed,
        }
        record["test_name"] = parsed["test_name"]
        record["dataset_name"] = parsed["dataset_name"]
        record["max_concurrency"] = parsed["max_concurrency"]
        record["num_prompts"] = parsed["num_prompts"]
        record["date"] = parsed["date"]
        record["sort_timestamp"] = parsed["sort_timestamp"]
        cr = merged.get("completed_requests")
        if cr is None:
            cr = merged.get("completed")
        fr = merged.get("failed_requests")
        if fr is None:
            fr = merged.get("failed")
        record["completed_requests"] = cr
        record["failed_requests"] = fr
        baseline_obj = merged.get("baseline")
        if isinstance(baseline_obj, dict):
            for bk, bv in baseline_obj.items():
                if isinstance(bk, str) and bk and isinstance(bv, (int, float)):
                    record[f"baseline_{bk}"] = float(bv)
        record["omni_metrics_profile"] = infer_omni_metrics_profile(record)
        record["config_key"] = " | ".join("" if record.get(field) is None else str(record.get(field)) for field in QWEN3_OMNI_GROUP_FIELDS)
        records.append(record)

    def _group_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return tuple("" if item.get(field) is None else str(item.get(field)) for field in QWEN3_OMNI_GROUP_FIELDS)

    records.sort(
        key=lambda item: (
            _group_sort_key(item),
            item["sort_timestamp"],
        ),
        reverse=False,
    )
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        key = _group_sort_key(record)
        grouped.setdefault(key, []).append(record)

    ordered_records: list[dict[str, Any]] = []
    for key in sorted(grouped):
        items = sorted(grouped[key], key=lambda item: item["sort_timestamp"], reverse=True)
        ordered_records.extend(items)
    return ordered_records


def load_qwen3_omni_history(source_dir: Path) -> list[dict[str, Any]]:
    return load_result_test_history(source_dir, DEFAULT_RESULT_DATASETS)


def _slug_stage_name(stage: str) -> str:
    return stage.replace(".", "_")


def _slug_serve_arg_key(key: str) -> str:
    return key.replace("-", "_").replace(".", "_")


def _serialize_serve_arg_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False)


def _normalize_hardware(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    hardware = value.strip()
    if not hardware:
        return None
    return hardware.upper()


def _load_diffusion_benchmark_records(sorted_paths: list[Path]) -> list[dict[str, Any]]:
    """Parse diffusion/benchmark perf JSON arrays (shared by Qwen Image and WAN 2.2 pages)."""
    raw_rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    stage_keys: set[str] = set()
    serve_arg_keys: set[str] = set()
    for path in sorted_paths:
        data = load_json(path, [])
        if not isinstance(data, list):
            continue
        for raw in data:
            if not isinstance(raw, dict):
                continue
            res = raw.get("result")
            if not isinstance(res, dict):
                continue
            ts = raw.get("timestamp") or ""
            try:
                parsed_ts = datetime.strptime(ts, "%Y%m%d-%H%M%S")
            except ValueError:
                continue
            bp = raw.get("benchmark_params") if isinstance(raw.get("benchmark_params"), dict) else {}
            sp = raw.get("server_params") if isinstance(raw.get("server_params"), dict) else {}
            sort_timestamp = parsed_ts.isoformat()
            date = parsed_ts.strftime("%Y-%m-%d %H:%M:%S")
            lm = res.get("latency_mean")
            e2e_ms = float(lm) * 1000.0 if isinstance(lm, (int, float)) else None
            med = res.get("latency_median")
            e2e_med_ms = float(med) * 1000.0 if isinstance(med, (int, float)) else None
            p99v = res.get("latency_p99")
            e2e_p99_ms = float(p99v) * 1000.0 if isinstance(p99v, (int, float)) else None
            pmem = res.get("peak_memory_mb_mean")
            peak_gb = float(pmem) / 1024.0 if isinstance(pmem, (int, float)) else None
            for dkey in ("stage_durations_mean", "stage_durations_p50", "stage_durations_p99"):
                block = res.get(dkey)
                if isinstance(block, dict):
                    stage_keys.update(block.keys())
            sa = sp.get("serve_args")
            if isinstance(sa, dict):
                serve_arg_keys.update(sa.keys())
            record = {
                "test_name": raw.get("test_name"),
                "backend": raw.get("backend"),
                "hardware": _normalize_hardware(raw.get("hardware") or raw.get("Hardware")),
                "model_id": sp.get("model"),
                "benchmark_name": str(bp.get("name") or ""),
                "dataset_name": str(bp.get("dataset") or ""),
                "max_concurrency": bp.get("max-concurrency"),
                "num_prompts": bp.get("num-prompts"),
                "task": bp.get("task"),
                "width": bp.get("width"),
                "height": bp.get("height"),
                "completed_requests": res.get("completed_requests"),
                "failed_requests": res.get("failed_requests"),
                "e2e_latency_ms": e2e_ms,
                "e2e_latency_median_ms": e2e_med_ms,
                "e2e_latency_p99_ms": e2e_p99_ms,
                "throughput_qps": res.get("throughput_qps"),
                "peak_memory_gb": peak_gb,
                "peak_memory_mb_mean": res.get("peak_memory_mb_mean"),
                "peak_memory_mb_median": res.get("peak_memory_mb_median"),
                "peak_memory_mb_max": res.get("peak_memory_mb_max"),
                "timestamp_key": ts,
                "sort_timestamp": sort_timestamp,
                "date": date,
                "source_file": path.name,
            }
            bench_bl = bp.get("baseline") if isinstance(bp.get("baseline"), dict) else {}
            bl_lm = bench_bl.get("latency_mean")
            if isinstance(bl_lm, (int, float)):
                record["baseline_e2e_latency_ms"] = float(bl_lm) * 1000.0
            bl_tpq = bench_bl.get("throughput_qps")
            if isinstance(bl_tpq, (int, float)):
                record["baseline_throughput_qps"] = float(bl_tpq)
            bl_pmem = bench_bl.get("peak_memory_mb_mean")
            if isinstance(bl_pmem, (int, float)):
                record["baseline_peak_memory_gb"] = float(bl_pmem) / 1024.0
            raw_rows.append((record, res, sp))

    ordered_serve = sorted(serve_arg_keys)
    ordered_stages = sorted(stage_keys)
    records: list[dict[str, Any]] = []
    for record, res, sp in raw_rows:
        sa = sp.get("serve_args") if isinstance(sp.get("serve_args"), dict) else {}
        for name in ordered_serve:
            slug = _slug_serve_arg_key(name)
            val = sa.get(name) if isinstance(sa, dict) else None
            record[f"serve_args_{slug}"] = _serialize_serve_arg_value(val)
        mean = res.get("stage_durations_mean") if isinstance(res.get("stage_durations_mean"), dict) else {}
        p50 = res.get("stage_durations_p50") if isinstance(res.get("stage_durations_p50"), dict) else {}
        p99d = res.get("stage_durations_p99") if isinstance(res.get("stage_durations_p99"), dict) else {}
        for name in ordered_stages:
            slug = _slug_stage_name(name)
            record[f"stage_mean_{slug}"] = mean.get(name) if isinstance(mean, dict) else None
            record[f"stage_p50_{slug}"] = p50.get(name) if isinstance(p50, dict) else None
            record[f"stage_p99_{slug}"] = p99d.get(name) if isinstance(p99d, dict) else None
        record["config_key"] = " | ".join(str(record.get(field, "")) for field in QWEN_IMAGE_GROUP_FIELDS)
        records.append(record)

    def _group_field_sort_value(value: Any) -> tuple[int, int, Any]:
        if value is None:
            return (1, 0, 0)
        if isinstance(value, bool):
            return (0, 1, int(value))
        if isinstance(value, (int, float)):
            return (0, 1, value)
        return (0, 2, str(value))

    def _group_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(_group_field_sort_value(item.get(field)) for field in QWEN_IMAGE_GROUP_FIELDS)

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        key = _group_sort_key(record)
        grouped.setdefault(key, []).append(record)
    ordered: list[dict[str, Any]] = []
    for key in sorted(grouped):
        items = sorted(grouped[key], key=lambda item: item["sort_timestamp"], reverse=True)
        ordered.extend(items)
    return ordered


def load_qwen_image_benchmark_history(source_dir: Path) -> list[dict[str, Any]]:
    """Load CI perf arrays from diffusion_* / benchmark_results_*.json (Qwen Image diffusion bench)."""
    bench_paths: set[Path] = set()
    for pattern in ("diffusion_result_*.json", "benchmark_results_*.json"):
        bench_paths.update(source_dir.rglob(pattern))
    return _load_diffusion_benchmark_records(sorted(bench_paths, key=lambda p: str(p)))


def load_wan22_benchmark_history(source_dir: Path) -> list[dict[str, Any]]:
    """Load CI perf arrays from diffusion_result*.json basenames that contain wan22."""
    bench_paths: list[Path] = []
    for path in source_dir.rglob("diffusion_result*.json"):
        if not path.is_file():
            continue
        if "wan22" not in path.name.casefold():
            continue
        bench_paths.append(path)
    return _load_diffusion_benchmark_records(sorted(bench_paths, key=lambda p: str(p)))


def _history_payload_from_records(
    config: dict[str, Any],
    source_dir: Path,
    page_key: str,
    display_name: str,
    group_fields: tuple[str, ...],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    def _normalize_filter_fields(item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        if normalized.get("qps") in (None, ""):
            normalized["qps"] = normalized.get("request_rate")
        if normalized.get("input_len") in (None, ""):
            normalized["input_len"] = normalized.get("random_input_len")
        if normalized.get("output_len") in (None, ""):
            normalized["output_len"] = normalized.get("random_output_len")
        return normalized

    records = [_normalize_filter_fields(record) for record in records]
    page_config = config.get("kanban_pages", {}).get(page_key, {})
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        key = tuple(record.get(field) for field in group_fields)
        groups.setdefault(key, []).append(record)

    grouped_payload = []
    for key in sorted(groups, key=lambda k: tuple("" if v is None else str(v) for v in k)):
        items = sorted(groups[key], key=lambda item: item["sort_timestamp"], reverse=True)
        grouped_payload.append(
            {
                "key": dict(zip(group_fields, key)),
                "config_key": items[0]["config_key"],
                "record_count": len(items),
                "records": items,
            }
        )

    filter_fields = page_config.get("filters", [])
    filter_options = {
        field: sorted(
            {item.get(field) for item in records if item.get(field) not in (None, "")},
            key=lambda value: str(value),
        )
        for field in filter_fields
    }
    metric_groups = ensure_baseline_metric_groups(page_config.get("metric_groups", []), records)

    try:
        source_dir_display = str(source_dir.relative_to(ROOT))
    except ValueError:
        source_dir_display = str(source_dir)

    return {
        "title": display_name,
        "source_dir": source_dir_display,
        "generated_at": datetime.now().isoformat(),
        "filters": filter_fields,
        "filter_options": filter_options,
        "table_columns": page_config.get("table_columns", []),
        "metric_groups": metric_groups,
        "group_fields": list(group_fields),
        "chart_point_per_day": bool(page_config.get("chart_point_per_day", True)),
        "default_visible_series": page_config.get("default_visible_series"),
        "record_count": len(records),
        "group_count": len(grouped_payload),
        "records": records,
        "groups": grouped_payload,
    }


def ensure_baseline_metric_groups(metric_groups: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chart_metrics = {
        metric
        for group in metric_groups
        for metric in group.get("metrics", [])
        if isinstance(metric, str)
    }
    baseline_metrics = {
        key[len("baseline_") :]
        for record in records
        for key in record
        if isinstance(key, str) and key.startswith("baseline_")
    }
    missing_metrics = sorted(baseline_metrics - chart_metrics)
    if not missing_metrics:
        return metric_groups
    generated_groups = [
        {
            "id": f"baseline_metric_{metric}",
            "title": metric.replace("_", " ").title(),
            "metrics": [metric],
            "collapsed": True,
        }
        for metric in missing_metrics
    ]
    return [*metric_groups, *generated_groups]


def build_result_test_history_payload(
    config: dict[str, Any],
    source_dir: Path,
    page_key: str,
    display_name: str,
) -> dict[str, Any]:
    page_config = config.get("kanban_pages", {}).get(page_key, {})
    ds_names = page_config.get("dataset_names", ["random", "random-mm"])
    dataset_allowlist = frozenset(ds_names)
    records = load_result_test_history(source_dir, dataset_allowlist) if source_dir.is_dir() else []
    return _history_payload_from_records(config, source_dir, page_key, display_name, QWEN3_OMNI_GROUP_FIELDS, records)


def build_qwen3_omni_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    display = config.get("models", {}).get("Qwen3-Omni", {}).get("display_name", "Qwen3 Omni")
    return build_result_test_history_payload(config, source_dir, "qwen3_omni_history", display)


def build_qwen3_tts_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    display = config.get("models", {}).get("Qwen3-TTS", {}).get("display_name", "Qwen3 TTS")
    page_config = config.get("kanban_pages", {}).get("qwen3_tts_history", {})
    ds_names = page_config.get("dataset_names", ["random", "random-mm"])
    dataset_allowlist = frozenset(ds_names)
    records = load_result_test_history(source_dir, dataset_allowlist) if source_dir.is_dir() else []
    return _history_payload_from_records(config, source_dir, "qwen3_tts_history", display, QWEN3_TTS_GROUP_FIELDS, records)


def build_qwen_image_family_history_payload(
    config: dict[str, Any],
    source_dir: Path,
    *,
    page_key: str,
    model_key: str,
    fallback_display: str,
    test_name_filter: Callable[[str], bool] | None = None,
    records_loader: Callable[[Path], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    display = config.get("models", {}).get(model_key, {}).get("display_name", fallback_display)
    loader = records_loader or load_qwen_image_benchmark_history
    records = loader(source_dir) if source_dir.is_dir() else []
    if test_name_filter is not None:
        records = [r for r in records if test_name_filter(str(r.get("test_name") or ""))]
    payload = _history_payload_from_records(config, source_dir, page_key, display, QWEN_IMAGE_GROUP_FIELDS, records)
    page_config = config.get("kanban_pages", {}).get(page_key, {})
    legacy_stage_json = frozenset({"stage_durations_mean", "stage_durations_p50", "stage_durations_p99"})
    base = [c for c in page_config.get("table_columns", []) if c not in legacy_stage_json]
    serve_cols = sorted({k for r in records for k in r if k.startswith("serve_args_")})
    if "model_id" in base and serve_cols:
        idx_m = base.index("model_id") + 1
        base = base[:idx_m] + serve_cols + base[idx_m:]
    dynamic: list[str] = []
    if page_config.get("include_stage_columns", True):
        stage_slug_set: set[str] = set()
        for rec in records:
            for k in rec:
                if k.startswith("stage_mean_"):
                    stage_slug_set.add(k[len("stage_mean_") :])
        slugs: list[str] = sorted(stage_slug_set)
        # qwen-image-edit page: keep one pipeline family to avoid duplicate display labels after prefix trimming.
        if page_key == "qwen_image_history":
            slugs = [s for s in slugs if "QwenImagePipeline_" in s]
        elif page_key == "qwen_image_layered_history":
            slugs = [s for s in slugs if "QwenImageLayeredPipeline_" in s]
        elif page_key == "qwen_image_edit_history":
            slugs = [s for s in slugs if "QwenImageEditPipeline_" in s]
        elif page_key in {"qwen_image_edit_2509_history", "qwen_image_edit_2511_history"}:
            slugs = [s for s in slugs if "QwenImageEditPlusPipeline_" in s]
        if page_config.get("p99_stage_columns_last", False):
            for slug in slugs:
                dynamic.extend([f"stage_mean_{slug}", f"stage_p50_{slug}"])
            for slug in slugs:
                dynamic.append(f"stage_p99_{slug}")
        else:
            for slug in slugs:
                dynamic.extend([f"stage_mean_{slug}", f"stage_p50_{slug}", f"stage_p99_{slug}"])
    anchor = "peak_memory_mb_max"
    if anchor in base:
        idx = base.index(anchor) + 1
        payload["table_columns"] = base[:idx] + dynamic + base[idx:]
    else:
        payload["table_columns"] = base + dynamic
    return payload


def build_qwen_image_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    return build_qwen_image_family_history_payload(
        config,
        source_dir,
        page_key="qwen_image_history",
        model_key="Qwen-image",
        fallback_display="Qwen Image",
        test_name_filter=lambda name: (
            "qwen_image_edit" not in name
            and "qwen_image_layered" not in name
            and "qwen_image" in name
        ),
    )


def build_qwen_image_layered_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    return build_qwen_image_family_history_payload(
        config,
        source_dir,
        page_key="qwen_image_layered_history",
        model_key="Qwen-image-layered",
        fallback_display="Qwen Image Layered",
        test_name_filter=lambda name: "qwen_image_layered" in name,
    )


def build_qwen_image_edit_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    return build_qwen_image_family_history_payload(
        config,
        source_dir,
        page_key="qwen_image_edit_history",
        model_key="Qwen-Image-edit",
        fallback_display="Qwen Image Edit",
        test_name_filter=lambda name: (
            "qwen_image_edit_2509" not in name
            and "qwen_image_edit_2511" not in name
            and "qwen_image_edit" in name
        ),
    )


def build_qwen_image_edit_2509_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    return build_qwen_image_family_history_payload(
        config,
        source_dir,
        page_key="qwen_image_edit_2509_history",
        model_key="Qwen-Image-edit-2509",
        fallback_display="Qwen Image Edit 2509",
        test_name_filter=lambda name: "qwen_image_edit_2509" in name,
    )


def build_qwen_image_edit_2511_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    return build_qwen_image_family_history_payload(
        config,
        source_dir,
        page_key="qwen_image_edit_2511_history",
        model_key="Qwen-Image-edit-2511",
        fallback_display="Qwen Image Edit 2511",
        test_name_filter=lambda name: "qwen_image_edit_2511" in name,
    )


def build_wan22_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    return build_qwen_image_family_history_payload(
        config,
        source_dir,
        page_key="wan22_history",
        model_key="WAN2.2",
        fallback_display="WAN 2.2",
        records_loader=load_wan22_benchmark_history,
    )


def build_hunyuan_image3_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    return build_qwen_image_family_history_payload(
        config,
        source_dir,
        page_key="hunyuan_image3_history",
        model_key="Hunyuan-Image3",
        fallback_display="Hunyuan Image 3",
        test_name_filter=lambda name: "hunyuan_image" in name,
    )


def _metric_field_name(label: str) -> str:
    """Map a table metric label to a record field key, e.g. "PSNR (dB)" -> "psnr_db"."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", label.lower())).strip("_")


def load_hunyuan_local_accuracy_records(raw_root: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Load accuracy metric tables from local manual pytest logs.

    Scans every ``manual_YYYYMMDD/*.log`` under ``raw_root`` (filenames vary, so no
    name-based filtering) and keeps rows attributed to hunyuan test files. The table
    reference column (L20x Reference) is stored as ``baseline_<metric>`` so the chart
    renderer draws it as the baseline line.

    Returns ``(records, metric_labels)`` where ``metric_labels`` maps the sanitized
    field key back to the original table label for chart titles.
    """
    records: list[dict[str, Any]] = []
    metric_labels: dict[str, str] = {}
    if not raw_root.is_dir():
        return records, metric_labels

    for log_path in sorted(raw_root.glob("manual_*/*.log")):
        date_match = re.fullmatch(r"manual_(\d{8})", log_path.parent.name)
        if not date_match:
            continue
        raw_date = date_match.group(1)
        date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        try:
            text = log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        by_case: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in parse_log_metric_tables(text):
            test_file = str(row.get("test_file") or "")
            if "hunyuan" not in test_file:
                continue
            by_case.setdefault((test_file, str(row.get("test_name") or "")), []).append(row)

        for (test_file, test_name), case_rows in sorted(by_case.items()):
            record: dict[str, Any] = {
                "date": date,
                "sort_timestamp": f"{date}T00:00:00",
                "test_file": test_file,
                "test_name": test_name,
                "source_file": log_path.name,
                "config_key": f"{test_file}::{test_name}",
            }
            for row in case_rows:
                field = _metric_field_name(row["metric"])
                metric_labels[field] = row["metric"]
                record[field] = row["value"]
                if row["reference"] is not None:
                    record[f"baseline_{field}"] = row["reference"]
            records.append(record)

    return records, metric_labels


def build_hunyuan_image3_accuracy_payload(config: dict[str, Any], raw_root: Path) -> dict[str, Any]:
    records, metric_labels = load_hunyuan_local_accuracy_records(raw_root)
    payload = _history_payload_from_records(
        config,
        raw_root,
        "hunyuan_image3_accuracy",
        "Hunyuan Image 3 - Local Accuracy",
        HUNYUAN_ACCURACY_GROUP_FIELDS,
        records,
    )
    metric_fields = sorted(metric_labels)
    payload["metric_groups"] = [
        {"id": field, "title": metric_labels[field], "metrics": [field]} for field in metric_fields
    ]
    payload["table_columns"] = ["date", "test_file", "test_name", *metric_fields, "source_file"]
    return payload


def build_bagel_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    return build_qwen_image_family_history_payload(
        config,
        source_dir,
        page_key="bagel_history",
        model_key="BAGEL",
        fallback_display="BAGEL",
        test_name_filter=lambda name: "bagel" in name,
    )


def build_voxcpm2_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    display = config.get("models", {}).get("VoxCPM2", {}).get("display_name", "VoxCPM2")
    page_config = config.get("kanban_pages", {}).get("voxcpm2_history", {})
    ds_names = page_config.get("dataset_names", ["seed-tts", "seed-tts-text"])
    records = load_result_test_history(source_dir, frozenset(ds_names)) if source_dir.is_dir() else []
    return _history_payload_from_records(config, source_dir, "voxcpm2_history", display, QWEN3_TTS_GROUP_FIELDS, records)


def framework_label(record: dict[str, Any]) -> str:
    for field in ("framework", "backend", "endpoint_type"):
        value = record.get(field)
        if value not in (None, ""):
            return str(value)
    return "unknown"


def finite_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = float(value)
        except ValueError:
            return None
        if math.isfinite(parsed):
            return parsed
    return None


def set_if_number(record: dict[str, Any], field: str, value: Any) -> None:
    parsed = finite_number(value)
    if parsed is not None:
        record[field] = round(parsed, 4)


def comparison_key(record: dict[str, Any]) -> str:
    return "||".join(key_part(record.get(field)) for field in FRAMEWORK_COMPARISON_DIMENSIONS)


def key_part(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def record_day(record: dict[str, Any]) -> str:
    for field in ("sort_timestamp", "date"):
        value = record.get(field)
        if isinstance(value, str) and len(value) >= 10:
            return value[:10]
    return ""


def parse_compact_timestamp(value: Any) -> tuple[str | None, str | None]:
    text = str(value or "").strip()
    match = re.match(r"(?P<date>\d{8})-(?P<time>\d{6})$", text)
    if not match:
        return None, None
    date_text = match.group("date")
    time_text = match.group("time")
    date = f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:]}"
    sort_timestamp = f"{date}T{time_text[:2]}:{time_text[2:4]}:{time_text[4:]}"
    return date, sort_timestamp


def parse_benchmark_profile(record: dict[str, Any]) -> None:
    match = re.search(r"(?P<width>\d+)x(?P<height>\d+)_steps(?P<steps>\d+)", str(record.get("benchmark_name") or ""))
    if not match:
        return
    record.setdefault("width", int(match.group("width")))
    record.setdefault("height", int(match.group("height")))
    record.setdefault("num_inference_steps", int(match.group("steps")))


def infer_endpoint(record: dict[str, Any]) -> str | None:
    endpoint = record.get("endpoint") or record.get("endpoint_type")
    if endpoint not in (None, ""):
        return str(endpoint)
    task = str(record.get("task") or "").lower()
    if task == "t2i":
        return "/v1/images/generations"
    if task in {"i2i", "ti2i"}:
        return "/v1/images/edits"
    return None


def infer_num_input_images(record: dict[str, Any]) -> int | None:
    parsed = finite_number(record.get("num_input_images"))
    if parsed is not None:
        return int(parsed)
    task = str(record.get("task") or "").lower()
    model_family = str(record.get("model_family") or "")
    if task == "t2i":
        return 0
    if task in {"i2i", "ti2i"}:
        return 2 if "2511" in model_family else 1
    return None


def normalized_test_profile(record: dict[str, Any]) -> str:
    name = str(record.get("test_name") or "").strip()
    if not name:
        return ""
    name = re.sub(r"_v1_images_(?:generations|edits)_\d{8}-\d{6}$", "", name)
    name = name.replace("test_sglang_", "test_", 1)
    if name == "test_qwen_image_single_device_step_execution":
        return "test_qwen_image_single_device"
    return name


def workload_key(record: dict[str, Any]) -> str:
    return "||".join(key_part(record.get(field)) for field in WORKLOAD_KEY_FIELDS)


def workload_label(record: dict[str, Any]) -> str:
    parts = [
        record.get("model_family"),
        record.get("workload_profile"),
        record.get("task"),
        f"{record.get('width')}x{record.get('height')}" if record.get("width") and record.get("height") else "",
        f"{record.get('num_inference_steps')} steps" if record.get("num_inference_steps") else "",
        f"{record.get('num_input_images')} images" if record.get("num_input_images") is not None else "",
        f"c{record.get('max_concurrency')}" if record.get("max_concurrency") not in (None, "") else "",
        f"p{record.get('num_prompts')}" if record.get("num_prompts") not in (None, "") else "",
    ]
    return " · ".join(str(part) for part in parts if part not in (None, ""))


def normalize_framework_comparison_record(record: dict[str, Any], metric_fields: set[str]) -> dict[str, Any]:
    parse_benchmark_profile(record)
    model_family = str(record.get("model_family") or record.get("title") or "Unknown Model")
    framework = framework_label(record)
    source_format = record.get("source_format", "vllm_history_payload")
    if framework == "unknown" and source_format == "vllm_history_payload":
        framework = "vllm-omni"
    record["model_family"] = model_family
    record["endpoint"] = infer_endpoint(record)
    record["num_input_images"] = infer_num_input_images(record)
    record["workload_profile"] = normalized_test_profile(record)
    comparison_record: dict[str, Any] = {
        "date": record.get("date"),
        "sort_timestamp": record.get("sort_timestamp") or record.get("date"),
        "model_family": model_family,
        "model_id": record.get("model_id") or model_family,
        "framework": framework,
        "backend": record.get("backend") or record.get("endpoint_type") or framework,
        "endpoint": record.get("endpoint"),
        "endpoint_type": record.get("endpoint_type"),
        "hardware": record.get("hardware") or "Not specified",
        "test_name": record.get("test_name"),
        "workload_profile": record.get("workload_profile"),
        "task": record.get("task"),
        "dataset_name": record.get("dataset_name"),
        "benchmark_name": record.get("benchmark_name"),
        "width": record.get("width"),
        "height": record.get("height"),
        "num_inference_steps": record.get("num_inference_steps"),
        "num_input_images": record.get("num_input_images"),
        "max_concurrency": record.get("max_concurrency"),
        "num_prompts": record.get("num_prompts"),
        "random_input_len": record.get("random_input_len"),
        "random_output_len": record.get("random_output_len"),
        "omni_metrics_profile": record.get("omni_metrics_profile"),
        "parallelism": record.get("parallelism") or record.get("Parallelism"),
        "peak_memory_status": record.get("peak_memory_status"),
        "commit_sha": record.get("commit_sha"),
        "source_format": source_format,
        "source_file": record.get("source_file"),
        "source_run_id": record.get("source_run_id") or record.get("config_key"),
    }
    if not comparison_record.get("task") and comparison_record.get("benchmark_name"):
        benchmark = str(comparison_record["benchmark_name"]).lower()
        if "t2i" in benchmark:
            comparison_record["task"] = "t2i"
        elif "i2i" in benchmark:
            comparison_record["task"] = "i2i"
    if comparison_record.get("endpoint") is None:
        comparison_record["endpoint"] = infer_endpoint(comparison_record)
    if comparison_record.get("num_input_images") is None:
        comparison_record["num_input_images"] = infer_num_input_images(comparison_record)
    comparison_record["workload_key"] = workload_key(comparison_record)
    comparison_record["comparison_key"] = comparison_key(comparison_record)
    comparison_record["workload_label"] = workload_label(comparison_record)
    for metric in metric_fields:
        value = record.get(metric)
        parsed = finite_number(value)
        if parsed is not None:
            comparison_record[metric] = round(parsed, 4)
    set_if_number(comparison_record, "latency_mean_s", record.get("latency_mean_s") or record.get("latency_mean"))
    set_if_number(comparison_record, "latency_p50_s", record.get("latency_p50_s") or record.get("latency_median"))
    set_if_number(comparison_record, "latency_p99_s", record.get("latency_p99_s") or record.get("latency_p99"))
    set_if_number(comparison_record, "throughput_qps", record.get("throughput_qps") or record.get("request_throughput"))
    set_if_number(comparison_record, "peak_memory_mb_max", record.get("peak_memory_mb_max"))
    e2e_latency_ms = finite_number(record.get("e2e_latency_ms") or record.get("mean_e2el_ms"))
    if e2e_latency_ms is not None and "latency_mean_s" not in comparison_record:
        comparison_record["latency_mean_s"] = round(e2e_latency_ms / 1000, 4)
    peak_memory_gb = finite_number(record.get("peak_memory_gb"))
    if peak_memory_gb is not None and "peak_memory_mb_max" not in comparison_record:
        comparison_record["peak_memory_mb_max"] = round(peak_memory_gb * 1024, 4)
    if comparison_record.get("peak_memory_mb_max") == 0:
        comparison_record["peak_memory_status"] = "missing_or_untrusted"
        comparison_record.pop("peak_memory_mb_max", None)
    if isinstance(record.get("stage_durations_mean"), dict):
        comparison_record["stage_durations_mean"] = record["stage_durations_mean"]
    for field, value in record.items():
        if field.startswith("stage_mean_"):
            set_if_number(comparison_record, field, value)
    return comparison_record


def build_framework_comparison_record(model_family: str, record: dict[str, Any], metric_fields: set[str]) -> dict[str, Any]:
    return normalize_framework_comparison_record({**record, "model_family": model_family}, metric_fields)


def parse_cli_args(command_text: str) -> dict[str, str | bool]:
    args: dict[str, str | bool] = {}
    try:
        tokens = shlex.split(command_text)
    except ValueError:
        tokens = command_text.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            key = token[2:].replace("-", "_")
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                args[key] = tokens[i + 1]
                i += 2
            else:
                args[key] = True
                i += 1
        else:
            i += 1
    return args


def parse_sglang_log_timestamp(log_text: str) -> tuple[str, str]:
    match = re.search(r"\[(\d{2})-(\d{2}) (\d{2}:\d{2}:\d{2})\]", log_text)
    if not match:
        date = datetime.now().strftime("%Y-%m-%d")
        return date, f"{date}T00:00:00"
    month, day, clock = match.groups()
    date = f"{datetime.now().year}-{month}-{day}"
    return date, f"{date}T{clock}"


def sglang_record_from_args(log_path: Path, model_family: str, model_id: str, args: dict[str, Any], date: str, sort_timestamp: str) -> dict[str, Any]:
    test_name = str(args.get("perf_dump_dir") or args.get("output_file") or log_path.stem).split("/")[-1]
    record: dict[str, Any] = {
        "date": date,
        "sort_timestamp": sort_timestamp,
        "model_family": model_family,
        "model_id": str(args.get("model") or model_id),
        "framework": "sglang",
        "backend": str(args.get("request_backend") or "sglang"),
        "endpoint": args.get("endpoint"),
        "hardware": "Not specified",
        "test_name": test_name,
        "task": args.get("task"),
        "dataset_name": args.get("dataset"),
        "width": args.get("width"),
        "height": args.get("height"),
        "num_inference_steps": args.get("num_inference_steps"),
        "num_input_images": args.get("num_input_images"),
        "max_concurrency": args.get("max_concurrency"),
        "num_prompts": args.get("num_prompts"),
        "source_format": "sglang_log",
        "source_file": str(log_path),
        "source_run_id": test_name,
    }
    return record


def parse_sglang_log_records(log_path: Path) -> list[dict[str, Any]]:
    model_family, model_id = SGLANG_LOG_MODEL_MAP.get(log_path.name, (log_path.stem, log_path.stem))
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    date, sort_timestamp = parse_sglang_log_timestamp(log_text)
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_stage_mean = False
    for raw_line in log_text.splitlines():
        line = re.sub(r"\x1b\[[0-9;]*m", "", raw_line).strip()
        if "Running benchmark (endpoint=" in line:
            command_text = line.split(":", 1)[1].strip() if ":" in line else line
            current = sglang_record_from_args(log_path, model_family, model_id, parse_cli_args(command_text), date, sort_timestamp)
            in_stage_mean = False
            continue
        if current is None:
            continue
        label_match = re.match(r"([A-Za-z][A-Za-z0-9 ()/]+):\s+([0-9.]+|inf)\b", line)
        if label_match:
            label, raw_value = label_match.groups()
            value = float(raw_value) if raw_value != "inf" else raw_value
            field_map = {
                "Request throughput (req/s)": "throughput_qps",
                "Latency Mean (s)": "latency_mean_s",
                "Latency Median (s)": "latency_p50_s",
                "Latency P99 (s)": "latency_p99_s",
                "Peak Memory Max (MB)": "peak_memory_mb_max",
                "Peak Memory Mean (MB)": "peak_memory_mb_mean",
                "Peak Memory Median (MB)": "peak_memory_mb_median",
            }
            field = field_map.get(label)
            if field:
                current[field] = value
                continue
        if line == "Stage Durations Mean (s):":
            current.setdefault("stage_durations_mean", {})
            in_stage_mean = True
            continue
        if in_stage_mean:
            stage_match = re.match(r"([A-Za-z][A-Za-z0-9_]+):\s+([0-9.]+)", line)
            if stage_match:
                stage, raw_value = stage_match.groups()
                current.setdefault("stage_durations_mean", {})[stage] = round(float(raw_value), 4)
                current[f"stage_mean_{stage}"] = round(float(raw_value), 4)
                continue
            if line.startswith("=") or not line:
                in_stage_mean = False
        if line.startswith("Results for ") and current:
            records.append(current)
            current = None
            in_stage_mean = False
    return records


def load_temporary_sglang_records(log_dir: Path = SGLANG_LOG_DIR) -> list[dict[str, Any]]:
    if not log_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for log_path in sorted(log_dir.glob("*.log")):
        records.extend(parse_sglang_log_records(log_path))
    return records


def records_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        records = payload.get("records", [])
        return records if isinstance(records, list) else []
    return []


def sglang_diffusion_input_dir(input_dir: Path = SGLANG_DIFFUSION_RESULTS_DIR) -> Path:
    env_dir = os.environ.get(SGLANG_DIFFUSION_RESULTS_ENV)
    if env_dir:
        return Path(env_dir)
    if input_dir.is_dir():
        return input_dir
    return input_dir


def sglang_diffusion_model_family(item: dict[str, Any]) -> str:
    server_params = item.get("server_params") if isinstance(item.get("server_params"), dict) else {}
    model_id = str(item.get("Model") or item.get("model") or server_params.get("model") or "").strip()
    if model_id in SGLANG_DIFFUSION_MODEL_FAMILY_MAP:
        return SGLANG_DIFFUSION_MODEL_FAMILY_MAP[model_id]
    if model_id:
        return model_id.split("/")[-1].replace("-", " ")
    return "Unknown Model"


def normalize_sglang_diffusion_json_record(path: Path, item: dict[str, Any]) -> dict[str, Any]:
    benchmark_params = item.get("benchmark_params") if isinstance(item.get("benchmark_params"), dict) else {}
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    server_params = item.get("server_params") if isinstance(item.get("server_params"), dict) else {}
    timestamp = item.get("timestamp")
    date, sort_timestamp = parse_compact_timestamp(timestamp)
    model_id = str(server_params.get("model") or result.get("model") or item.get("Model") or "").strip()
    record: dict[str, Any] = {
        "date": date,
        "sort_timestamp": sort_timestamp or date,
        "model_family": sglang_diffusion_model_family(item),
        "model_id": model_id,
        "framework": str(
            item.get("Framework") or result.get("request_backend") or item.get("request_backend") or "sglang",
        ).lower(),
        "backend": str(
            item.get("Request Backend") or result.get("request_backend") or item.get("request_backend") or "sglang",
        ),
        "endpoint": item.get("endpoint") or result.get("endpoint") or item.get("API Endpoint"),
        "hardware": item.get("Hardware") or "Not specified",
        "test_name": item.get("test_name"),
        "task": benchmark_params.get("task") or result.get("task") or item.get("Task"),
        "dataset_name": benchmark_params.get("dataset") or result.get("dataset") or item.get("Dataset"),
        "benchmark_name": benchmark_params.get("name"),
        "width": benchmark_params.get("width"),
        "height": benchmark_params.get("height"),
        "num_inference_steps": benchmark_params.get("num-inference-steps") or item.get("num_inference_steps"),
        "num_input_images": benchmark_params.get("num-input-images"),
        "max_concurrency": benchmark_params.get("max-concurrency") or item.get("max_concurrency"),
        "num_prompts": benchmark_params.get("num-prompts"),
        "parallelism": item.get("Parallelism"),
        "source_format": "sglang_diffusion_json",
        "source_file": str(path),
        "source_run_id": f"{item.get('test_name') or path.stem}:{timestamp or path.stem}",
        "commit_sha": item.get("commit_sha"),
    }
    metric_map = {
        "throughput_qps": "throughput_qps",
        "latency_mean": "latency_mean",
        "latency_median": "latency_median",
        "latency_p50": "latency_p50_s",
        "latency_p99": "latency_p99",
        "peak_memory_mb_max": "peak_memory_mb_max",
    }
    for source_field, target_field in metric_map.items():
        if source_field in result:
            record[target_field] = result[source_field]
    if isinstance(result.get("stage_durations_mean"), dict):
        record["stage_durations_mean"] = result["stage_durations_mean"]
        for stage, value in result["stage_durations_mean"].items():
            record[f"stage_mean_{stage}"] = value
    return record


def load_sglang_diffusion_json_records(input_dir: Path = SGLANG_DIFFUSION_RESULTS_DIR) -> list[dict[str, Any]]:
    source_dir = sglang_diffusion_input_dir(input_dir)
    if not source_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(source_dir.glob("*.json")):
        payload = load_json(path, [])
        for item in records_from_payload(payload):
            if isinstance(item, dict):
                records.append(normalize_sglang_diffusion_json_record(path, item))
    return records


def load_formal_framework_comparison_records(input_dir: Path = FRAMEWORK_COMPARISON_INPUT_DIR) -> list[dict[str, Any]]:
    """Read the future stable comparison input format without coupling UI code to it."""
    if not input_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted([*input_dir.glob("*.json"), *input_dir.glob("*.jsonl")]):
        try:
            if path.suffix == ".jsonl":
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        payload = json.loads(line)
                        if isinstance(payload, dict):
                            payload.setdefault("source_format", "formal_jsonl")
                            payload.setdefault("source_file", str(path))
                            records.append(payload)
            else:
                payload = load_json(path, {})
                for item in records_from_payload(payload):
                    if isinstance(item, dict):
                        item.setdefault("source_format", "formal_json")
                        item.setdefault("source_file", str(path))
                        records.append(item)
        except (OSError, json.JSONDecodeError):
            continue
    return records


def comparison_metric_fields() -> set[str]:
    return {metric for group in FRAMEWORK_COMPARISON_METRIC_GROUPS for metric in group["metrics"]}


def build_workload_options(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = str(record.get("workload_key") or "")
        if key:
            by_key.setdefault(key, []).append(record)
    options: list[dict[str, Any]] = []
    for key, items in by_key.items():
        sample = items[0]
        frameworks = sorted({str(item.get("framework")) for item in items if item.get("framework")})
        dates_by_framework = {
            framework: sorted({record_day(item) for item in items if item.get("framework") == framework and record_day(item)})
            for framework in frameworks
        }
        options.append(
            {
                "key": key,
                "label": sample.get("workload_label") or key,
                "model_family": sample.get("model_family"),
                "workload_profile": sample.get("workload_profile"),
                "frameworks": frameworks,
                "dates_by_framework": dates_by_framework,
                "comparable": any(framework in {"vllm-omni", "vllm"} for framework in frameworks) and "sglang" in frameworks,
            }
        )
    return sorted(options, key=lambda item: (str(item.get("model_family") or ""), str(item.get("label") or "")))


def build_metric_options(records: list[dict[str, Any]], metric_fields: set[str]) -> list[dict[str, str]]:
    available_metrics = sorted({metric for item in records for metric in metric_fields if metric in item})
    return [{"value": metric, "label": metric.replace("_", " ").title()} for metric in available_metrics]


def build_framework_date_options(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    frameworks = sorted({str(item.get("framework")) for item in records if item.get("framework")})
    return {
        framework: sorted({record_day(item) for item in records if item.get("framework") == framework and record_day(item)})
        for framework in frameworks
    }


def build_framework_comparison_payload(history_payloads: list[dict[str, Any]], adapter_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    metric_fields = {
        metric
        for group in FRAMEWORK_COMPARISON_METRIC_GROUPS
        for metric in group["metrics"]
    }
    records: list[dict[str, Any]] = []
    for payload in history_payloads:
        model_family = str(payload.get("title") or "Unknown Model")
        for record in payload.get("records", []):
            comparison_record = build_framework_comparison_record(model_family, record, metric_fields)
            if any(metric in comparison_record for metric in metric_fields):
                records.append(comparison_record)
    for record in adapter_records or []:
        comparison_record = normalize_framework_comparison_record(record, metric_fields)
        if any(metric in comparison_record for metric in metric_fields):
            records.append(comparison_record)

    records.sort(key=lambda item: str(item.get("sort_timestamp") or ""), reverse=True)
    filters = ["model_family", "model_id", "framework", "backend", "hardware", "task", "test_name", "dataset_name", "width", "height", "num_inference_steps", "num_input_images", "max_concurrency", "num_prompts"]
    filter_options = {
        field: sorted({str(value) for item in records if (value := item.get(field)) not in (None, "")})
        for field in filters
    }
    available_metrics = {metric for item in records for metric in metric_fields if metric in item}
    metric_groups = [
        {
            **group,
            "metrics": [metric for metric in group["metrics"] if metric in available_metrics],
        }
        for group in FRAMEWORK_COMPARISON_METRIC_GROUPS
    ]
    metric_groups = [group for group in metric_groups if group["metrics"]]
    table_columns = [
        column
        for column in FRAMEWORK_COMPARISON_TABLE_COLUMNS
        if column not in metric_fields or column in available_metrics
    ]
    comparable_groups = {
        key
        for key, frameworks in _frameworks_by_workload_key(records).items()
        if len(frameworks) > 1
    }
    workload_options = build_workload_options(records)

    return {
        "title": "Framework Comparison",
        "generated_at": datetime.now().isoformat(),
        "baseline_framework": "vllm",
        "baseline_candidates": ["vllm-omni", "vllm"],
        "filters": filters,
        "filter_options": filter_options,
        "table_columns": table_columns,
        "metric_groups": metric_groups,
        "metric_options": build_metric_options(records, metric_fields),
        "workload_options": workload_options,
        "framework_date_options": build_framework_date_options(records),
        "record_count": len(records),
        "comparable_group_count": len(comparable_groups),
        "comparison_dimensions": list(FRAMEWORK_COMPARISON_DIMENSIONS),
        "workload_key_fields": list(WORKLOAD_KEY_FIELDS),
        "model_page_targets": [{"model_family": model, "href": href} for model, href in MODEL_COMPARE_PAGE_TARGETS],
        "records": records,
    }


def _frameworks_by_workload_key(records: list[dict[str, Any]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for record in records:
        grouped.setdefault(str(record.get("workload_key") or ""), set()).add(str(record.get("framework") or "unknown"))
    return grouped


def build_higgs_audio_v3_history_payload(config: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    display = config.get("models", {}).get("Higgs-Audio-V3", {}).get("display_name", "Higgs Audio V3")
    page_config = config.get("kanban_pages", {}).get("higgs_audio_v3_history", {})
    ds_names = page_config.get("dataset_names", ["seed-tts-text"])
    records = load_result_test_history(source_dir, frozenset(ds_names)) if source_dir.is_dir() else []
    return _history_payload_from_records(config, source_dir, "higgs_audio_v3_history", display, QWEN3_TTS_GROUP_FIELDS, records)


def build_multi_series_chart(
    dates: list[str],
    hardware_items: list[tuple[str, str]],
    day_results: dict[str, list[dict[str, Any]]],
    model: str,
    metric: str,
    y_min: float | None = None,
    y_max: float | None = None,
) -> dict[str, Any]:
    series = []
    for hardware, hardware_label in hardware_items:
        values = []
        for date in dates:
            match = next(
                (item for item in day_results.get(date, []) if item["model"] == model and item["hardware"] == hardware),
                None,
            )
            flat = flatten_metrics(match["metrics"]) if match else {}
            values.append(flat.get(metric))
        if any(value is not None for value in values):
            series.append({"name": hardware_label, "type": "line", "data": values, "smooth": True})

    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"type": "scroll", "top": 0, "left": 0, "right": 0, "textStyle": {"fontSize": 12}},
        "grid": {"left": 56, "right": 24, "top": 54, "bottom": 42},
        "xAxis": {"type": "category", "data": dates, "axisLabel": {"color": "#5b6775"}},
        "yAxis": {"type": "value", "min": y_min, "max": y_max, "axisLabel": {"color": "#5b6775"}},
        "series": series,
    }


def build_hardware_status(config: dict[str, Any], latest_results: list[dict[str, Any]]) -> dict[str, Any]:
    hardware_status = []
    for hardware_key, hardware_config in config.get("hardware", {}).items():
        hw_results = [r for r in latest_results if r.get("hardware") == hardware_key]
        if not hw_results:
            continue
        pass_rate = average_metric(hw_results, "pass_rate")
        latency_p99 = average_metric(hw_results, "latency_p99_ms")
        if pass_rate is None:
            status = "unknown"
        elif pass_rate >= 0.9:
            status = "healthy"
        elif pass_rate >= 0.8:
            status = "warning"
        else:
            status = "critical"
        hardware_status.append({
            "hardware_key": hardware_key,
            "display_name": hardware_config["display_name"],
            "pass_rate": pass_rate,
            "latency_p99_ms": latency_p99,
            "status": status,
        })
    return {"hardware": hardware_status}


def main() -> int:
    config = load_json(CONFIG_PATH, {})
    index = load_json(INDEX_PATH, {"dates": []})
    dates = sorted(index.get("dates", []))
    day_results = {date: load_json(RESULTS_DIR / f"{date}.json", {"results": []}).get("results", []) for date in dates}

    hardware_items = [(key, value["display_name"]) for key, value in config.get("hardware", {}).items()]

    latest_results = day_results[dates[-1]] if dates else []
    save_chart("hardware_status", build_hardware_status(config, latest_results))
    qwen3_omni_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("qwen3_omni_history", {}).get("source_dir", "qwen3omni")
    qwen3_omni_payload = build_qwen3_omni_history_payload(config, qwen3_omni_source_dir)
    save_json(QWEN3_OMNI_HISTORY_PATH, qwen3_omni_payload)
    qwen3_tts_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("qwen3_tts_history", {}).get("source_dir", "qwen3tts")
    qwen3_tts_payload = build_qwen3_tts_history_payload(config, qwen3_tts_source_dir)
    save_json(QWEN3_TTS_HISTORY_PATH, qwen3_tts_payload)
    qwen_image_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("qwen_image_history", {}).get("source_dir", "qwen_image")
    qwen_image_payload = build_qwen_image_history_payload(config, qwen_image_source_dir)
    save_json(QWEN_IMAGE_HISTORY_PATH, qwen_image_payload)
    qwen_image_layered_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("qwen_image_layered_history", {}).get("source_dir", "qwen_image_layered")
    qwen_image_layered_payload = build_qwen_image_layered_history_payload(config, qwen_image_layered_source_dir)
    save_json(QWEN_IMAGE_LAYERED_HISTORY_PATH, qwen_image_layered_payload)
    qwen_image_edit_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("qwen_image_edit_history", {}).get("source_dir", "qwen_image_edit")
    qwen_image_edit_payload = build_qwen_image_edit_history_payload(config, qwen_image_edit_source_dir)
    save_json(QWEN_IMAGE_EDIT_HISTORY_PATH, qwen_image_edit_payload)
    qwen_image_edit_2509_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("qwen_image_edit_2509_history", {}).get("source_dir", "qwen_image_edit_2509")
    qwen_image_edit_2509_payload = build_qwen_image_edit_2509_history_payload(config, qwen_image_edit_2509_source_dir)
    save_json(QWEN_IMAGE_EDIT_2509_HISTORY_PATH, qwen_image_edit_2509_payload)
    qwen_image_edit_2511_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("qwen_image_edit_2511_history", {}).get("source_dir", "qwen_image_edit_2511")
    qwen_image_edit_2511_payload = build_qwen_image_edit_2511_history_payload(config, qwen_image_edit_2511_source_dir)
    save_json(QWEN_IMAGE_EDIT_2511_HISTORY_PATH, qwen_image_edit_2511_payload)
    wan22_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("wan22_history", {}).get("source_dir", "wan22")
    wan22_payload = build_wan22_history_payload(config, wan22_source_dir)
    save_json(WAN22_HISTORY_PATH, wan22_payload)
    hunyuan_image3_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("hunyuan_image3_history", {}).get("source_dir", "hunyuan_image3")
    hunyuan_image3_payload = build_hunyuan_image3_history_payload(config, hunyuan_image3_source_dir)
    save_json(HUNYUAN_IMAGE3_HISTORY_PATH, hunyuan_image3_payload)
    save_json(HUNYUAN_IMAGE3_ACCURACY_PATH, build_hunyuan_image3_accuracy_payload(config, LOCAL_RAW_DIR))
    bagel_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("bagel_history", {}).get("source_dir", "bagel")
    bagel_payload = build_bagel_history_payload(config, bagel_source_dir)
    save_json(BAGEL_HISTORY_PATH, bagel_payload)
    voxcpm2_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("voxcpm2_history", {}).get("source_dir", "voxcpm2")
    voxcpm2_payload = build_voxcpm2_history_payload(config, voxcpm2_source_dir)
    save_json(VOXCPM2_HISTORY_PATH, voxcpm2_payload)
    higgs_audio_v3_source_dir = RESULTS_DIR / config.get("kanban_pages", {}).get("higgs_audio_v3_history", {}).get("source_dir", "higgs_audio_v3")
    higgs_audio_v3_payload = build_higgs_audio_v3_history_payload(config, higgs_audio_v3_source_dir)
    save_json(HIGGS_AUDIO_V3_HISTORY_PATH, higgs_audio_v3_payload)
    sglang_diffusion_records = load_sglang_diffusion_json_records()
    comparison_adapter_records = [
        *load_formal_framework_comparison_records(),
        *sglang_diffusion_records,
        *(load_temporary_sglang_records() if not sglang_diffusion_records else []),
    ]
    save_json(
        FRAMEWORK_COMPARISON_PATH,
        build_framework_comparison_payload(
            [
                qwen3_omni_payload,
                qwen3_tts_payload,
                qwen_image_payload,
                qwen_image_layered_payload,
                qwen_image_edit_payload,
                qwen_image_edit_2509_payload,
                qwen_image_edit_2511_payload,
                wan22_payload,
                hunyuan_image3_payload,
                bagel_payload,
                voxcpm2_payload,
                higgs_audio_v3_payload,
            ],
            comparison_adapter_records,
        ),
    )
    for model, model_config in config.get("models", {}).items():
        available_metrics = set(model_config["metrics"]["required"]) | set(model_config["metrics"]["optional"])
        for metric, y_min, y_max in MODEL_METRICS.get(model, []):
            if metric not in available_metrics:
                continue
            for range_key, window in RANGE_WINDOWS.items():
                save_chart(
                    f"{chart_slug(model)}_{metric}_{range_key}",
                    build_multi_series_chart(
                        dates[-window:],
                        hardware_items,
                        day_results,
                        model,
                        metric,
                        y_min=y_min,
                        y_max=y_max,
                    ),
                )
    print(f"generated {len(list(CHARTS_DIR.glob('*.json')))} chart files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
