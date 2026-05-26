"""Tests for scripts.verify_data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_data import VerificationError, verify_repo_data, verify_snapshot


def _valid_snapshot() -> dict:
    return {
        "model_id": "qwen3-omni",
        "display_name": "Qwen3 Omni",
        "category": "multimodal",
        "required_metrics": ["pass_rate"],
        "optional_metrics": [],
        "alert_thresholds": {},
        "variants": [{"id": "random-c1", "display_name": "random · c=1", "color": "#76b900"}],
        "series": [
            {
                "date": "2026-05-23",
                "variant_id": "random-c1",
                "values": {"pass_rate": 0.98},
                "alerts": [],
            },
            {
                "date": "2026-05-22",
                "variant_id": "random-c1",
                "values": {"pass_rate": 0.97},
                "alerts": [],
            },
        ],
    }


def test_verify_snapshot_valid_ok() -> None:
    verify_snapshot(_valid_snapshot())


def test_verify_snapshot_missing_field() -> None:
    s = _valid_snapshot()
    del s["series"]
    with pytest.raises(VerificationError, match="series"):
        verify_snapshot(s)


def test_verify_snapshot_non_numeric_value() -> None:
    s = _valid_snapshot()
    s["series"][0]["values"]["pass_rate"] = "not-a-number"  # type: ignore[assignment]
    with pytest.raises(VerificationError, match="non-numeric"):
        verify_snapshot(s)


def test_verify_snapshot_missing_variant_id() -> None:
    s = _valid_snapshot()
    del s["series"][0]["variant_id"]
    with pytest.raises(VerificationError, match="variant_id"):
        verify_snapshot(s)


def test_verify_snapshot_60_percent_drift_warns(caplog: pytest.LogCaptureFixture) -> None:
    """Drift gate is a soft warning, not a hard error (upstream data may use placeholder values)."""
    import logging

    s = _valid_snapshot()
    s["series"] = [
        {"date": "2026-05-23", "variant_id": "v", "values": {"pass_rate": 0.30}, "alerts": []},
        {"date": "2026-05-22", "variant_id": "v", "values": {"pass_rate": 0.90}, "alerts": []},
        {"date": "2026-05-21", "variant_id": "v", "values": {"pass_rate": 0.91}, "alerts": []},
        {"date": "2026-05-20", "variant_id": "v", "values": {"pass_rate": 0.92}, "alerts": []},
        {"date": "2026-05-19", "variant_id": "v", "values": {"pass_rate": 0.93}, "alerts": []},
        {"date": "2026-05-18", "variant_id": "v", "values": {"pass_rate": 0.94}, "alerts": []},
        {"date": "2026-05-17", "variant_id": "v", "values": {"pass_rate": 0.95}, "alerts": []},
        {"date": "2026-05-16", "variant_id": "v", "values": {"pass_rate": 0.95}, "alerts": []},
    ]
    with caplog.at_level(logging.WARNING):
        verify_snapshot(s)  # should NOT raise
    assert any("drift" in r.message for r in caplog.records), "expected drift warning in log"


def test_verify_repo_data_missing_snapshot(tmp_path: Path) -> None:
    (tmp_path / "dashboard/src/data/snapshots").mkdir(parents=True)
    (tmp_path / "dashboard/src/data").joinpath("identity.json").write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "x",
                        "kanban_name": "X",
                        "display_name": "X",
                        "slug": "x",
                        "category": "c",
                    }
                ],
            }
        )
    )
    (tmp_path / "dashboard/src/data/manifest.json").write_text(json.dumps({"models": ["x"]}))
    with pytest.raises(VerificationError, match="snapshot file missing"):
        verify_repo_data(tmp_path)
