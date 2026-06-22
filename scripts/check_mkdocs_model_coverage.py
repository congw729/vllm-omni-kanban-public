from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
IGNORED_HISTORY_PAGES = {
    # Kept in generated chart data for historical access, but intentionally absent
    # from the MkDocs model directory.
    "qwen_image_edit_2509_history",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _model_nav_paths(mkdocs_config: dict[str, Any]) -> set[str]:
    for entry in mkdocs_config.get("nav", []):
        if not isinstance(entry, dict) or "Models" not in entry:
            continue
        models = entry["Models"]
        if not isinstance(models, list):
            return set()
        paths: set[str] = set()
        for item in models:
            if isinstance(item, dict):
                paths.update(str(value) for value in item.values())
            elif isinstance(item, str):
                paths.add(item)
        return paths
    return set()


def _slug_from_history_key(key: str) -> str:
    return key.removesuffix("_history").replace("_", "-")


def _history_pages(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pages = config.get("kanban_pages", {})
    if not isinstance(pages, dict):
        return {}
    return {
        key: value
        for key, value in pages.items()
        if key.endswith("_history") and key not in IGNORED_HISTORY_PAGES and isinstance(value, dict)
    }


def collect_warnings(root: Path) -> list[str]:
    config = _load_json(root / "data" / "config.json")
    mkdocs_config = _load_yaml(root / "mkdocs.yml")
    index_text = (root / "docs" / "index.md").read_text(encoding="utf-8")
    generate_charts_text = (root / "scripts" / "generate_charts.py").read_text(encoding="utf-8")
    mkdocs_hooks_text = (root / "scripts" / "mkdocs_hooks.py").read_text(encoding="utf-8")
    nav_paths = _model_nav_paths(mkdocs_config)

    warnings: list[str] = []
    for history_key, page_config in sorted(_history_pages(config).items()):
        slug = _slug_from_history_key(history_key)
        page_path = root / "docs" / "models" / f"{slug}.md"
        nav_path = f"models/{slug}.md"
        index_href = f'models/{slug}/'
        chart_file = f"{history_key}.json"
        source_dir = str(page_config.get("source_dir", ""))

        if not page_path.exists():
            warnings.append(f"{history_key}: missing docs/models/{slug}.md")
            continue

        page_text = page_path.read_text(encoding="utf-8")
        if nav_path not in nav_paths:
            warnings.append(f"{history_key}: missing MkDocs nav entry for {nav_path}")
        if index_href not in index_text:
            warnings.append(f"{history_key}: missing docs/index.md card link {index_href}")
        if chart_file not in page_text:
            warnings.append(f"{history_key}: model page does not reference {chart_file}")
        if chart_file not in generate_charts_text:
            warnings.append(f"{history_key}: scripts/generate_charts.py does not write {chart_file}")
        if source_dir and f'"{source_dir}"' not in mkdocs_hooks_text and f"'{source_dir}'" not in mkdocs_hooks_text:
            warnings.append(f"{history_key}: scripts/mkdocs_hooks.py does not sync source_dir {source_dir}")

    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check MkDocs model page coverage without blocking daily service by default.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when coverage warnings are found.")
    args = parser.parse_args()

    warnings = collect_warnings(ROOT)
    if not warnings:
        print("MkDocs model coverage check passed.")
        return 0

    print("MkDocs model coverage warnings:")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
