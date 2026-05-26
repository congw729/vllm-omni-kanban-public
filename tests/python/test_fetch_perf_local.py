"""Tests for scripts.fetch_perf_local (local-filesystem variant of fetch_kanban)."""

from __future__ import annotations

from pathlib import Path

from scripts.fetch_perf_local import (
    assign_variant_colors,
    build_snapshots_from_results,
    extract_date_from_filename,
    find_canonical_file,
    merge_into_snapshot_file,
    parse_result_entry,
    pick_canonical_entry,
)

# ---------------------------------------------------------------------------
# Inline fixtures — one entry per model type
# ---------------------------------------------------------------------------

DIFFUSION_ENTRY = {
    "test_name": "test_qwen_image_edit_2509_single_device",
    "timestamp": "20260523-181412",
    "server_params": {"model": "Qwen/Qwen-Image-Edit-2509"},
    "benchmark_params": {"name": "512x512_steps20_i2i_2img"},
    "result": {
        "throughput_qps": 0.067,
        "latency_mean": 14.9,
        "latency_median": 14.9,
        "latency_p99": 14.97,
        "latency_p95": 14.97,
        "latency_p50": 14.91,
        "peak_memory_mb_max": 57612.0,
        "peak_memory_mb_mean": 57612.0,
        "completed_requests": 10,
        "failed_requests": 0,
        "duration": 149.16,
    },
    "Hardware": "",
    "Framework": "vllm-omni",
    "Model": "Qwen/Qwen-Image-Edit-2509",
}

# A second variant that should be ignored (different test_name)
DIFFUSION_ENTRY_OTHER_VARIANT = {
    "test_name": "test_qwen_image_edit_2509_ulysses2_cfg2_vae_patch4",
    "result": {
        "throughput_qps": 0.12,
        "latency_p99": 10.0,
        "completed_requests": 10,
        "failed_requests": 1,
    },
}

LLM_ENTRY = {
    "date": "20260523-182413",
    "model_id": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
    "completed": 4,
    "failed": 0,
    "output_throughput": 22.58,
    "p99_e2el_ms": 35111.55,
    "mean_ttft_ms": 125.39,
    "random_input_len": 2500,
    "random_output_len": 900,
}

TTS_ENTRY = {
    "date": "20260523-182251",
    "model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "completed": 20,
    "failed": 0,
    "audio_throughput": 6.36,
    "p99_e2el_ms": 1029.39,
    "mean_audio_ttfp_ms": 138.75,
}


# ---------------------------------------------------------------------------
# parse_result_entry
# ---------------------------------------------------------------------------


def test_parse_result_entry_diffusion_metrics() -> None:
    row = parse_result_entry(
        DIFFUSION_ENTRY, "diffusion", date="2026-05-23", variant_id="single_device"
    )
    assert row is not None
    assert row["date"] == "2026-05-23"
    assert row["variant_id"] == "single_device"
    assert row["values"]["pass_rate"] == 1.0
    # latency_p99 in result is 14.97 seconds → converted to ms
    assert abs(row["values"]["latency_p99_ms"] - 14970.0) < 1.0
    assert abs(row["values"]["throughput_qps"] - 0.067) < 1e-6
    assert row["values"]["peak_memory_mb_max"] == 57612.0


def test_parse_result_entry_llm_metrics() -> None:
    # Generic extractor: emits the raw field name verbatim, not a renamed one.
    row = parse_result_entry(LLM_ENTRY, "llm", date="2026-05-23", variant_id="random-c1")
    assert row is not None
    assert row["variant_id"] == "random-c1"
    assert row["values"]["pass_rate"] == 1.0
    assert abs(row["values"]["p99_e2el_ms"] - 35111.55) < 0.01
    assert abs(row["values"]["mean_ttft_ms"] - 125.39) < 0.01
    assert abs(row["values"]["output_throughput"] - 22.58) < 0.01
    # Config keys (random_input_len, random_output_len) must NOT be in values.
    assert "random_input_len" not in row["values"]
    assert "random_output_len" not in row["values"]


def test_parse_result_entry_tts_metrics() -> None:
    row = parse_result_entry(TTS_ENTRY, "llm", date="2026-05-23", variant_id="base-seedtts-c1")
    assert row is not None
    assert row["values"]["pass_rate"] == 1.0
    # TTS-specific fields flow through with their raw names; future fields
    # added upstream (e.g. new audio metric) appear without code changes.
    assert abs(row["values"]["mean_audio_ttfp_ms"] - 138.75) < 0.01
    assert abs(row["values"]["audio_throughput"] - 6.36) < 0.01
    assert abs(row["values"]["p99_e2el_ms"] - 1029.39) < 0.01


def test_parse_result_entry_pass_rate_with_failures() -> None:
    entry = dict(DIFFUSION_ENTRY)
    entry["result"] = dict(DIFFUSION_ENTRY["result"])
    entry["result"]["completed_requests"] = 10
    entry["result"]["failed_requests"] = 2
    row = parse_result_entry(entry, "diffusion", date="2026-05-23", variant_id="single_device")
    assert row is not None
    assert abs(row["values"]["pass_rate"] - 0.8) < 1e-9


def test_parse_result_entry_zero_completed_returns_none() -> None:
    entry = dict(DIFFUSION_ENTRY)
    entry["result"] = dict(DIFFUSION_ENTRY["result"])
    entry["result"]["completed_requests"] = 0
    row = parse_result_entry(entry, "diffusion", date="2026-05-23", variant_id="single_device")
    assert row is None


# ---------------------------------------------------------------------------
# pick_canonical_entry
# ---------------------------------------------------------------------------


def test_pick_canonical_entry_diffusion_matches_test_name() -> None:
    data = [DIFFUSION_ENTRY_OTHER_VARIANT, DIFFUSION_ENTRY]
    entry = pick_canonical_entry(data, "test_qwen_image_edit_2509_single_device", "diffusion")
    assert entry is not None
    assert entry["test_name"] == "test_qwen_image_edit_2509_single_device"


def test_pick_canonical_entry_diffusion_no_match_returns_none() -> None:
    data = [DIFFUSION_ENTRY_OTHER_VARIANT]
    entry = pick_canonical_entry(data, "test_qwen_image_edit_2509_single_device", "diffusion")
    assert entry is None


def test_pick_canonical_entry_llm_returns_dict() -> None:
    entry = pick_canonical_entry(LLM_ENTRY, None, "llm")
    assert entry is LLM_ENTRY


def test_pick_canonical_entry_llm_wrong_type_returns_none() -> None:
    entry = pick_canonical_entry([LLM_ENTRY], None, "llm")
    assert entry is None


# ---------------------------------------------------------------------------
# extract_date_from_filename
# ---------------------------------------------------------------------------


def test_extract_date_from_filename_diffusion() -> None:
    name = "diffusion_result_test_qwen_image_edit_2509_vllm_omni_20260523-181140.json"
    assert extract_date_from_filename(name) == "2026-05-23"


def test_extract_date_from_filename_llm() -> None:
    name = "result_test_qwen3_omni_random_1_4_in2500_out900_20260517-182030.json"
    assert extract_date_from_filename(name) == "2026-05-17"


def test_extract_date_from_filename_no_match() -> None:
    assert extract_date_from_filename("some_random_file.json") is None


# ---------------------------------------------------------------------------
# find_canonical_file (now takes list[Path] instead of list[dict])
# ---------------------------------------------------------------------------


def test_find_canonical_file_matches_glob(tmp_path: Path) -> None:
    f1 = tmp_path / "diffusion_result_test_qwen_image_edit_2509_vllm_omni_20260523-181140.json"
    f2 = tmp_path / "diffusion_result_test_qwen_image_vllm_omni_20260523-181537.json"
    f1.write_text("{}")
    f2.write_text("{}")
    result = find_canonical_file(
        [f1, f2], "diffusion_result_test_qwen_image_edit_2509_vllm_omni_*.json"
    )
    assert result is not None
    assert "edit_2509" in result.name


def test_find_canonical_file_no_match_returns_none(tmp_path: Path) -> None:
    f = tmp_path / "some_other_file.json"
    f.write_text("{}")
    result = find_canonical_file([f], "diffusion_result_test_wan22_*_vllm_omni_*.json")
    assert result is None


# ---------------------------------------------------------------------------
# build_snapshots_from_results (new variant-aware API)
# ---------------------------------------------------------------------------


def _make_identity() -> dict:
    return {
        "models": [
            {
                "id": "qwen-image-edit-2509",
                "kanban_name": "Qwen-Image-edit-2509",
                "display_name": "Qwen Image Edit 2509",
                "slug": "qwen-image-edit-2509",
                "category": "image_editing",
            },
            {
                "id": "qwen3-omni",
                "kanban_name": "Qwen3-Omni",
                "display_name": "Qwen3 Omni",
                "slug": "qwen3-omni",
                "category": "multimodal",
            },
            {
                "id": "qwen3-tts",
                "kanban_name": "Qwen3-TTS",
                "display_name": "Qwen3 TTS",
                "slug": "qwen3-tts",
                "category": "audio_synthesis",
            },
        ],
    }


def test_variant_rows_get_correct_variant_id() -> None:
    """variant rows must carry variant_id matching the variant declaration."""
    identity = _make_identity()
    row_v1 = {
        "date": "2026-05-23",
        "variant_id": "single_device",
        "values": {"pass_rate": 1.0},
        "alerts": [],
    }
    row_v2 = {
        "date": "2026-05-23",
        "variant_id": "ulysses2",
        "values": {"pass_rate": 0.9},
        "alerts": [],
    }
    results_by_build = {
        "10254": {
            "Qwen-Image-edit-2509": [row_v1, row_v2],
        }
    }
    out = build_snapshots_from_results(results_by_build, identity)
    assert "qwen-image-edit-2509" in out
    vids = [r["variant_id"] for r in out["qwen-image-edit-2509"]]
    assert "single_device" in vids
    assert "ulysses2" in vids


def test_merge_deduplicates_by_date_and_variant_id() -> None:
    """merge_into_snapshot_file must dedup on (date, variant_id), not hardware_id."""
    existing = {
        "series": [
            {
                "date": "2026-05-01",
                "variant_id": "random-c1",
                "values": {"pass_rate": 0.9},
                "alerts": [],
            },
        ]
    }
    new_rows = [
        {
            "date": "2026-05-01",
            "variant_id": "random-c1",
            "values": {"pass_rate": 0.95},
            "alerts": [],
        },
        {
            "date": "2026-05-02",
            "variant_id": "random-c1",
            "values": {"pass_rate": 0.97},
            "alerts": [],
        },
        {
            "date": "2026-05-01",
            "variant_id": "random-mm-qps0.1",
            "values": {"pass_rate": 0.88},
            "alerts": [],
        },
    ]
    meta = {"id": "qwen3-omni", "display_name": "Qwen3 Omni", "category": "multimodal"}
    variants_meta = [{"id": "random-c1", "display_name": "random · c=1", "color": "#76b900"}]
    merged = merge_into_snapshot_file(
        existing,
        model_id="qwen3-omni",
        model_meta=meta,
        variants_meta=variants_meta,
        new_rows=new_rows,
    )
    # (2026-05-01, random-c1) should be deduped → only one entry
    same_date_v1 = [
        r for r in merged["series"] if r["date"] == "2026-05-01" and r["variant_id"] == "random-c1"
    ]
    assert len(same_date_v1) == 1
    assert same_date_v1[0]["values"]["pass_rate"] == 0.95  # new value wins
    # (2026-05-02, random-c1) should be present
    assert any(
        r["date"] == "2026-05-02" and r["variant_id"] == "random-c1" for r in merged["series"]
    )
    # (2026-05-01, random-mm-qps0.1) should be a separate entry
    assert any(
        r["date"] == "2026-05-01" and r["variant_id"] == "random-mm-qps0.1"
        for r in merged["series"]
    )


def test_multiple_variants_produce_multiple_rows_per_date() -> None:
    """A model with N variants should produce N rows for the same date."""
    identity = _make_identity()
    rows = [
        {
            "date": "2026-05-23",
            "variant_id": "base-seedtts-c1",
            "values": {"pass_rate": 1.0},
            "alerts": [],
        },
        {
            "date": "2026-05-23",
            "variant_id": "customvoice-design-c1",
            "values": {"pass_rate": 0.95},
            "alerts": [],
        },
        {
            "date": "2026-05-23",
            "variant_id": "customvoice-text-c1",
            "values": {"pass_rate": 0.98},
            "alerts": [],
        },
    ]
    results_by_build = {"10254": {"Qwen3-TTS": rows}}
    out = build_snapshots_from_results(results_by_build, identity)
    assert "qwen3-tts" in out
    date_rows = [r for r in out["qwen3-tts"] if r["date"] == "2026-05-23"]
    assert len(date_rows) == 3
    vids = {r["variant_id"] for r in date_rows}
    assert vids == {"base-seedtts-c1", "customvoice-design-c1", "customvoice-text-c1"}


def test_build_snapshots_skips_empty_variant_lists() -> None:
    identity = _make_identity()
    # Empty list means no rows for this model
    results_by_build = {"9845": {"Qwen3-TTS": []}}
    out = build_snapshots_from_results(results_by_build, identity)
    assert "qwen3-tts" not in out


# ---------------------------------------------------------------------------
# assign_variant_colors
# ---------------------------------------------------------------------------


def test_assign_variant_colors_cycles_palette() -> None:
    variants = [
        {"id": "v1", "display_name": "V1"},
        {"id": "v2", "display_name": "V2"},
        {"id": "v3", "display_name": "V3"},
    ]
    palette = ["#aaa", "#bbb"]
    result = assign_variant_colors(variants, palette)
    assert result[0]["color"] == "#aaa"
    assert result[1]["color"] == "#bbb"
    assert result[2]["color"] == "#aaa"  # cycles
    assert all("id" in r and "display_name" in r and "color" in r for r in result)


# ---------------------------------------------------------------------------
# merge_into_snapshot_file — snapshot shape
# ---------------------------------------------------------------------------


def test_merge_snapshot_includes_variants_field() -> None:
    meta = {"id": "qwen3-tts", "display_name": "Qwen3 TTS", "category": "audio_synthesis"}
    variants_meta = [
        {"id": "base-seedtts-c1", "display_name": "base · seed-tts · c=1", "color": "#76b900"}
    ]
    merged = merge_into_snapshot_file(
        None,
        model_id="qwen3-tts",
        model_meta=meta,
        variants_meta=variants_meta,
        new_rows=[],
    )
    assert "variants" in merged
    assert merged["variants"] == variants_meta
    assert "hardware" not in merged
