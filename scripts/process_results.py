from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.common import flatten_metrics, load_json, parse_timestamp, save_json

DATA_DIR = ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"
INDEX_PATH = DATA_DIR / "index.json"
CONFIG_PATH = DATA_DIR / "config.json"

def ensure_number(name: str, value: Any) -> None:
    if not isinstance(value, (int, float)):
        raise ValueError(f"metric '{name}' must be numeric")


def validate_result(result: dict[str, Any], config: dict[str, Any]) -> None:
    for key in ("timestamp", "commit", "hardware", "model", "metrics"):
        if key not in result:
            raise ValueError(f"missing required field: {key}")

    if not isinstance(result["commit"], str) or not result["commit"]:
        raise ValueError("commit must be a non-empty string")

    parse_timestamp(result["timestamp"])

    if result["hardware"] not in config["hardware"]:
        raise ValueError(f"unknown hardware: {result['hardware']}")
    if result["model"] not in config["models"]:
        raise ValueError(f"unknown model: {result['model']}")
    if not isinstance(result["metrics"], dict):
        raise ValueError("metrics must be an object")

    flat_metrics = flatten_metrics(result["metrics"])
    required_metrics = config["models"][result["model"]]["metrics"]["required"]
    missing = [metric for metric in required_metrics if metric not in flat_metrics]
    if missing:
        raise ValueError(f"missing required metrics for {result['model']}: {', '.join(missing)}")

    for metric in required_metrics:
        ensure_number(metric, flat_metrics[metric])


def normalize_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("unsupported payload format")


def load_input(args: argparse.Namespace) -> Any:
    if args.input:
        return load_json(Path(args.input), None)
    env_payload = os.getenv("GITHUB_EVENT_CLIENT_PAYLOAD")
    if env_payload:
        import json

        return json.loads(env_payload)
    raise ValueError("no input payload provided")


def result_key(result: dict[str, Any]) -> tuple[str, str, str]:
    return (parse_timestamp(result["timestamp"]).date().isoformat(), result["hardware"], result["model"])


def compare_results(existing: dict[str, Any], incoming: dict[str, Any]) -> int:
    existing_ts = parse_timestamp(existing["timestamp"])
    incoming_ts = parse_timestamp(incoming["timestamp"])
    return 1 if incoming_ts > existing_ts or incoming["commit"] != existing["commit"] else -1 if incoming_ts < existing_ts else 0


def upsert_result(result: dict[str, Any], source: str) -> tuple[str, bool]:
    result_date, hardware, model = result_key(result)
    day_path = RESULTS_DIR / f"{result_date}.json"
    day_payload = load_json(day_path, {"date": result_date, "results": []})
    results = day_payload["results"]

    existing_index = None
    for idx, item in enumerate(results):
        item_key = (
            parse_timestamp(item["timestamp"]).date().isoformat(),
            item["hardware"],
            item["model"],
        )
        if item_key == (result_date, hardware, model):
            existing_index = idx
            break

    if existing_index is None:
        results.append(result)
        save_json(day_path, day_payload)
        return result_date, True

    existing = results[existing_index]
    if existing == result:
        return result_date, False

    comparison = compare_results(existing, result)
    if source == "schedule" or comparison >= 0:
        results[existing_index] = result
        save_json(day_path, day_payload)
        return result_date, True
    return result_date, False


def prune_old_data(index: dict[str, Any], retention_days: int, reference_date: date) -> None:
    if not index["dates"]:
        return
    keep_after = reference_date - timedelta(days=retention_days - 1)
    kept_dates = []
    for date_str in index["dates"]:
        if datetime.fromisoformat(date_str).date() >= keep_after:
            kept_dates.append(date_str)
        else:
            path = RESULTS_DIR / f"{date_str}.json"
            if path.exists():
                path.unlink()
    index["dates"] = kept_dates


def update_index(touched_dates: set[str], config: dict[str, Any], last_updated: str) -> dict[str, Any]:
    index = load_json(INDEX_PATH, {"last_updated": None, "retention_days": config["retention_days"], "dates": []})
    index["retention_days"] = config["retention_days"]
    index["last_updated"] = last_updated
    index["dates"] = sorted(set(index["dates"]).union(touched_dates), reverse=True)
    prune_old_data(index, config["retention_days"], parse_timestamp(last_updated).date())
    save_json(INDEX_PATH, index)
    return index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process daily vLLM-omni results.")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--input", help="Input file path")
    parser.add_argument("--source", choices=("dispatch", "schedule"), default="dispatch")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_json(CONFIG_PATH, {})
    payload = load_input(args)
    results = normalize_results(payload)
    for result in results:
        validate_result(result, config)

    if args.validate_only:
        print(f"validated {len(results)} results")
        return 0

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    touched_dates: set[str] = set()
    for result in results:
        date_str, changed = upsert_result(result, args.source)
        if changed:
            touched_dates.add(date_str)
    if not touched_dates and results:
        touched_dates.add(result_key(results[0])[0])

    latest_timestamp = max(result["timestamp"] for result in results)
    index = update_index(touched_dates, config, latest_timestamp)

    print(f"processed {len(results)} results across {len(index['dates'])} dates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
