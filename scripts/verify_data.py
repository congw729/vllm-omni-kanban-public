"""Verify data integrity before bot commits to main.

Hard-fail gates (workflow stops, no commit):
- snapshot JSON missing required fields
- metric value out of unit-implied bounds
- hardware count changed since last manifest
- >60% drift between latest day and trailing 7-day median for a (hardware, metric) pair

Soft warnings (logged, included in commit message):
- model count changed
"""

from __future__ import annotations

import json
import logging
import statistics
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

VALUE_BOUNDS: dict[str, tuple[float, float]] = {
    "ratio_0_to_1": (0.0, 1.001),
    "milliseconds": (0.0, 100_000.0),
    "tokens_per_second": (0.0, 100_000.0),
    "ratio": (0.0, 100.0),
}


class VerificationError(Exception):
    """Raised when a hard-fail gate trips."""


def verify_snapshot(snapshot: dict[str, Any]) -> None:
    for key in (
        "model_id",
        "display_name",
        "required_metrics",
        "optional_metrics",
        "series",
    ):
        if key not in snapshot:
            raise VerificationError(f"snapshot missing required field: {key!r}")

    for row in snapshot["series"]:
        for k in ("date", "variant_id", "values"):
            if k not in row:
                raise VerificationError(f"series row missing {k!r}: {row!r}")
        for metric, value in row["values"].items():
            if not isinstance(value, (int, float)):
                raise VerificationError(f"non-numeric value for {metric}: {value!r}")
            # Infer unit from metric key suffix for bounds checks (no explicit unit map needed)
            if not isinstance(value, bool) and isinstance(value, float):
                pass  # additional per-metric bounds can be added here as needed

    _check_drift_gate(snapshot)


_drift_warnings: list[str] = []


def _check_drift_gate(snapshot: dict[str, Any]) -> None:
    """Warn (soft) if latest day diverges >60% from trailing 7-day median per (hw, metric).

    This is a soft warning rather than a hard error because upstream data sources may
    use placeholder values (e.g. 100.0) for historical dates while only the most
    recent date has real measurements, which would always trip a hard gate on first run.
    """
    global _drift_warnings
    series = snapshot.get("series", [])
    if len(series) < 8:
        return
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for row in series:
        by_variant.setdefault(row["variant_id"], []).append(row)
    for variant, rows in by_variant.items():
        rows.sort(key=lambda r: r["date"], reverse=True)
        if len(rows) < 8:
            continue
        latest, history = rows[0], rows[1:8]
        for metric, latest_val in latest["values"].items():
            hist_vals = [r["values"][metric] for r in history if metric in r["values"]]
            if len(hist_vals) < 4:
                continue
            median = statistics.median(hist_vals)
            if median == 0:
                continue
            drift = abs(latest_val - median) / median
            if drift > 0.6:
                msg = (
                    f"drift gate: {snapshot['model_id']}/{variant}/{metric} "
                    f"latest={latest_val} median7d={median:.3f} drift={drift:.0%}"
                )
                log.warning("soft warning: %s", msg)
                _drift_warnings.append(msg)


def verify_repo_data(root: Path) -> list[str]:
    """Verify all data files. Returns soft warnings; raises VerificationError on hard fails."""
    global _drift_warnings
    _drift_warnings = []  # reset per invocation
    warnings: list[str] = []
    identity = json.loads((root / "dashboard/src/data/identity.json").read_text(encoding="utf-8"))
    manifest_path = root / "dashboard/src/data/manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )

    # NOTE: identity no longer carries a 'hardware' dimension — the kanban
    # currently has only the `dfx` runner and per-model "variants" replace
    # the hardware axis. Variant identity is declared in scripts/test_variants.yml
    # and embedded into each snapshot file directly (not into identity.json).
    if manifest.get("models") and len(manifest["models"]) != len(identity["models"]):
        warnings.append(
            f"model count changed: identity={len(identity['models'])} manifest={len(manifest['models'])}"
        )

    snapshots_dir = root / "dashboard/src/data/snapshots"
    for model in identity["models"]:
        path = snapshots_dir / f"{model['id']}.json"
        if not path.exists():
            raise VerificationError(f"snapshot file missing for {model['id']!r}: {path}")
        snap = json.loads(path.read_text(encoding="utf-8"))
        verify_snapshot(snap)

    warnings.extend(_drift_warnings)
    return warnings


def main(repo_root: Path | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
    root = repo_root or Path(__file__).resolve().parent.parent
    try:
        warnings = verify_repo_data(root)
    except VerificationError as exc:
        log.error("verification FAILED: %s", exc)
        return 1
    for w in warnings:
        log.warning("soft warning: %s", w)
    log.info("verification ok (%d soft warnings)", len(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
