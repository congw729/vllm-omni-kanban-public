"""Fetch vllm-omni nightly performance data from raw Buildkite JSON results.

Reads data/buildkite_nightly_raw/<build_id>/tests/dfx/perf/results/*.json
directly from the local filesystem (we are now inside the kanban repo, so
the raw data lives at repo_root/data/buildkite_nightly_raw/).
"""

from __future__ import annotations

import fnmatch
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

log = logging.getLogger(__name__)

# Raw-entry keys that are bookkeeping/config, not metrics. Everything else
# numeric gets pulled through as a metric (so new fields auto-appear).
_NON_METRIC_KEYS: frozenset[str] = frozenset(
    {
        # request counts (used to compute pass_rate, not emitted directly)
        "completed",
        "failed",
        "completed_requests",
        "failed_requests",
        # benchmark config
        "num_prompts",
        "max_concurrency",
        "max_concurrent_requests",
        "request_rate",
        "burstiness",
        "duration",
        "num-prompts",
        "max-concurrency",
        "num-inference-steps",
        "num-input-images",
        "width",
        "height",
        "random_input_len",
        "random_output_len",
        "input_len",
        "output_len",
        "in_len",
        "out_len",
        # job/labeling metadata
        "date",
        "endpoint_type",
        "backend",
        "label",
        "model_id",
        "tokenizer_id",
        "test_name",
        "timestamp",
        "endpoint",
        "log_file",
        # diffusion top-level header (these are strings/empty anyway)
        "Model",
        "Framework",
        "API Endpoint",
        "Hardware",
        "Deployment",
        "Task",
        "Dataset",
        "resolution",
        "Parallelism",
        "Cache",
        "Quantization",
        "offload",
        "compile",
        "Attn_backend",
    }
)


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------


def parse_result_entry(
    entry: dict[str, Any],
    model_type: str,
    *,
    date: str,
    variant_id: str,
) -> dict[str, Any] | None:
    """Extract normalised metrics from one raw result entry.

    Args:
        entry: A single result entry dict (flat for LLM, from ``result`` sub-key
            for diffusion).
        model_type: ``"diffusion"`` or ``"llm"``.
        date: YYYY-MM-DD date string for this build.
        variant_id: The variant identifier for this row.

    Returns:
        A snapshot row dict with ``date``, ``variant_id``, ``values``, ``alerts``,
        or ``None`` if the entry should be skipped (e.g. no valid requests).
    """
    # Schema-free extraction: collect every numeric field from the raw entry.
    # Future upstream metric additions flow through automatically.
    if model_type == "diffusion":
        # diffusion: numeric metrics live under entry.result; latency_* fields
        # are in seconds and get a uniform "*_ms" rename + x1000 conversion.
        source = entry.get("result", {})
        completed = source.get("completed_requests")
        failed = source.get("failed_requests")
        seconds_to_ms_prefixes: tuple[str, ...] = ("latency_",)
    else:
        # LLM/TTS: flat dict, fields already named with their unit suffix.
        source = entry
        completed = source.get("completed")
        failed = source.get("failed")
        seconds_to_ms_prefixes = ()

    if not completed:
        return None

    values: dict[str, float] = {}

    # Derived metric: pass rate
    if completed is not None and failed is not None and completed > 0:
        values["pass_rate"] = 1.0 - (failed / completed)

    # Generic numeric pass: every scalar number that isn't a request-counter or
    # known-noise field. This catches new TTS metrics (rtfx, audio_throughput,
    # mean_audio_rtf, …) and any future fields without code changes.
    for key, raw in source.items():
        if key in _NON_METRIC_KEYS:
            continue
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue
        out_key = key
        out_val = float(raw)
        if any(key.startswith(p) for p in seconds_to_ms_prefixes):
            # diffusion latency in seconds → emit as *_ms for unit consistency
            out_key = f"{key}_ms"
            out_val *= 1000.0
        values[out_key] = out_val

    if not values:
        return None

    return {
        "date": date,
        "variant_id": variant_id,
        "values": values,
        "alerts": [],
    }


def extract_date_from_filename(filename: str) -> str | None:
    """Parse YYYYMMDD from a filename timestamp suffix like ``_20260523-181140.json``.

    Returns ``YYYY-MM-DD`` string, or ``None`` if not found.
    """
    import re

    m = re.search(r"_(\d{8})-\d{6}\.json$", filename)
    if not m:
        return None
    raw = m.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def find_canonical_file(file_paths: list[Path], file_glob: str) -> Path | None:
    """Find the first path in ``file_paths`` whose name matches ``file_glob``.

    Returns the matching Path or ``None``.
    """
    for p in file_paths:
        if fnmatch.fnmatch(p.name, file_glob):
            return p
    return None


def pick_canonical_entry(
    data: Any, test_name: str | None, model_type: str
) -> dict[str, Any] | None:
    """Pick the canonical entry from parsed file data.

    For ``diffusion`` type: ``data`` is a list; we pick the first entry whose
    ``test_name`` matches. For ``llm`` type: ``data`` is a flat dict, returned as-is.
    """
    if model_type == "diffusion":
        if not isinstance(data, list):
            log.warning("Expected list for diffusion result, got %s", type(data).__name__)
            return None
        for entry in data:
            if test_name is None or entry.get("test_name") == test_name:
                return cast("dict[str, Any]", entry)
        return None
    else:
        if not isinstance(data, dict):
            log.warning("Expected dict for llm result, got %s", type(data).__name__)
            return None
        return cast("dict[str, Any]", data)


# ---------------------------------------------------------------------------
# Snapshot building
# ---------------------------------------------------------------------------


def build_snapshots_from_results(
    results_by_build: dict[str, dict[str, list[dict[str, Any]]]],
    identity: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Aggregate per-build parsed results into per-model snapshot row lists.

    Args:
        results_by_build: ``{build_id: {kanban_name: [row, ...]}}`` where each
            row already carries a ``variant_id``.
        identity: The site identity dict (``models`` array).

    Returns:
        ``{model_id: [row, ...]}`` with rows sorted by date ascending.
    """
    kanban_to_id: dict[str, str] = {m["kanban_name"]: m["id"] for m in identity["models"]}
    out: dict[str, list[dict[str, Any]]] = {}

    for _build_id, model_results in results_by_build.items():
        for kanban_name, rows in model_results.items():
            model_id = kanban_to_id.get(kanban_name)
            if model_id is None:
                continue
            for row in rows:
                if row is not None:
                    out.setdefault(model_id, []).append(row)

    # Sort each model's series by date ascending
    for model_id in out:
        out[model_id].sort(key=lambda r: (r["date"], r["variant_id"]))

    return out


def merge_into_snapshot_file(
    existing: dict[str, Any] | None,
    *,
    model_id: str,
    model_meta: dict[str, Any],
    variants_meta: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    retention_days: int = 90,
) -> dict[str, Any]:
    """Merge new rows into an existing snapshot file, deduping by (date, variant_id).

    New rows for an existing (date, variant_id) OVERWRITE the old row.
    Rows older than ``retention_days`` from today (UTC) are pruned.
    """
    cutoff: str = (datetime.now(UTC) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    series: list[dict[str, Any]] = list(existing.get("series", [])) if existing else []
    keyed: dict[tuple[str, str], dict[str, Any]] = {(r["date"], r["variant_id"]): r for r in series}
    for r in new_rows:
        keyed[(r["date"], r["variant_id"])] = r
    pruned: list[dict[str, Any]] = [r for r in keyed.values() if r["date"] >= cutoff]
    pruned.sort(key=lambda r: (r["date"], r["variant_id"]))

    # Derive the metric list from the union of all keys actually present in the
    # series — the snapshot file declares exactly what it carries, no more.
    # Stable order: pass_rate first (universal), then alphabetical.
    present: set[str] = {k for r in pruned for k in r.get("values", {})}
    sorted_metrics = sorted(present - {"pass_rate"})
    required_metrics = (["pass_rate"] if "pass_rate" in present else []) + sorted_metrics

    return {
        "model_id": model_id,
        "display_name": model_meta["display_name"],
        "category": model_meta.get("category", "unknown"),
        "variants": variants_meta,
        "required_metrics": required_metrics,
        "optional_metrics": [],
        # Units intentionally not declared here — the page infers them from the
        # metric key name (e.g. `*_ms` → milliseconds) so any future field
        # flows through with the correct label without a fetcher code change.
        "alert_thresholds": {},
        "series": pruned,
    }


# ---------------------------------------------------------------------------
# Variant color assignment
# ---------------------------------------------------------------------------


def assign_variant_colors(
    variants: list[dict[str, Any]], palette: list[str]
) -> list[dict[str, Any]]:
    """Assign colors from the palette (cycled) to each variant in order."""
    result: list[dict[str, Any]] = []
    for i, v in enumerate(variants):
        color = palette[i % len(palette)]
        result.append(
            {
                "id": v["id"],
                "display_name": v["display_name"],
                "color": color,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(repo_root: Path | None = None) -> int:
    """Entry point invoked by dashboard-sync.yml.

    Reads raw Buildkite JSON results from the local filesystem
    (data/buildkite_nightly_raw/ relative to repo root), picks the canonical
    variant per model per build, and merges into snapshot files.
    Returns exit code.
    """
    import yaml

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
    root: Path = repo_root or Path(__file__).resolve().parent.parent

    identity: dict[str, Any] = json.loads(
        (root / "dashboard/src/data/identity.json").read_text(encoding="utf-8")
    )
    variants_cfg: dict[str, Any] = yaml.safe_load(
        (root / "scripts/test_variants.yml").read_text(encoding="utf-8")
    )
    variant_models: dict[str, Any] = variants_cfg["models"]
    palette: list[str] = variants_cfg.get("variant_colors", ["#76b900"])

    raw_data_root: Path = root / "data/buildkite_nightly_raw"
    if not raw_data_root.is_dir():
        log.error("Raw data directory not found: %s", raw_data_root)
        return 1

    cutoff_date: str = (datetime.now(UTC) - timedelta(days=90)).strftime("%Y-%m-%d")
    today_str: str = datetime.now(UTC).strftime("%Y-%m-%d")

    # List all build IDs from local filesystem
    build_ids: list[int] = sorted(
        [int(p.name) for p in raw_data_root.iterdir() if p.is_dir() and p.name.isdigit()],
        reverse=True,
    )
    log.info("Found %d build directories", len(build_ids))

    # {build_id: {kanban_name: [row, ...]}}
    results_by_build: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for build_id in build_ids:
        build_str = str(build_id)
        results_path = raw_data_root / build_str / "tests/dfx/perf/results"

        if not results_path.is_dir():
            log.warning("Build %s: results dir missing; skipping", build_str)
            continue

        # Collect all JSON files in the results directory
        file_paths: list[Path] = sorted(results_path.glob("*.json"))
        if not file_paths:
            log.warning("Build %s: no JSON files found in results dir; skipping", build_str)
            continue

        # Determine build date from first file timestamp we can parse
        build_date: str | None = None
        for fp in file_paths:
            build_date = extract_date_from_filename(fp.name)
            if build_date:
                break

        if build_date is None:
            log.warning("Build %s: cannot determine date from filenames; skipping", build_str)
            continue

        if build_date < cutoff_date:
            log.debug(
                "Build %s (date %s) is outside 90-day window; skipping", build_str, build_date
            )
            continue

        if build_date > today_str:
            log.debug("Build %s (date %s) is in the future; skipping", build_str, build_date)
            continue

        log.info("Processing build %s (date %s)", build_str, build_date)
        build_results: dict[str, list[dict[str, Any]]] = {}

        for kanban_name, model_cfg in variant_models.items():
            model_type: str = model_cfg.get("type", "llm")
            variants: list[dict[str, Any]] = model_cfg.get("variants", [])
            rows_for_model: list[dict[str, Any]] = []

            for variant in variants:
                variant_id: str = variant["id"]
                file_glob: str = variant["file_glob"]
                inner_test_name: str | None = variant.get("inner_test_name")

                file_path = find_canonical_file(file_paths, file_glob)
                if file_path is None:
                    log.debug(
                        "Build %s: no file matching %r for %s/%s",
                        build_str,
                        file_glob,
                        kanban_name,
                        variant_id,
                    )
                    continue

                try:
                    data = json.loads(file_path.read_bytes())
                except (json.JSONDecodeError, OSError) as exc:
                    log.warning(
                        "Build %s: failed to read/parse %s (%s); skipping variant %s",
                        build_str,
                        file_path.name,
                        exc,
                        variant_id,
                    )
                    continue

                entry = pick_canonical_entry(data, inner_test_name, model_type)
                if entry is None:
                    log.debug(
                        "Build %s: entry %r not found in %s (variant %s)",
                        build_str,
                        inner_test_name,
                        file_path.name,
                        variant_id,
                    )
                    continue

                row = parse_result_entry(entry, model_type, date=build_date, variant_id=variant_id)
                if row is not None:
                    rows_for_model.append(row)

            build_results[kanban_name] = rows_for_model

        results_by_build[build_str] = build_results

    # Aggregate into per-model snapshot rows
    all_new = build_snapshots_from_results(results_by_build, identity)

    snapshots_dir: Path = root / "dashboard/src/data/snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for model in identity["models"]:
        mid = model["id"]
        kanban_name = model["kanban_name"]
        path = snapshots_dir / f"{mid}.json"
        existing: dict[str, Any] | None = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        )

        # Build variant metadata (id, display_name, color) for this model
        model_variant_defs: list[dict[str, Any]] = variant_models.get(kanban_name, {}).get(
            "variants", []
        )
        variants_meta = assign_variant_colors(model_variant_defs, palette)

        merged: dict[str, Any] = merge_into_snapshot_file(
            existing,
            model_id=mid,
            model_meta=model,
            variants_meta=variants_meta,
            new_rows=all_new.get(mid, []),
        )
        path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(mid)

    now_iso: str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_dates: list[str] = sorted(
        {
            r["date"]
            for mid in written
            for r in json.loads((snapshots_dir / f"{mid}.json").read_text(encoding="utf-8"))[
                "series"
            ]
        }
    )
    manifest: dict[str, Any] = {
        "last_updated": now_iso,
        "models": [m["id"] for m in identity["models"]],
        "date_range": {
            "start": all_dates[0] if all_dates else None,
            "end": all_dates[-1] if all_dates else None,
        },
    }
    (root / "dashboard/src/data/manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    log.info("wrote %d snapshot files; date range %s", len(written), manifest["date_range"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
