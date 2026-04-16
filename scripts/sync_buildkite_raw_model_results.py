"""Copy perf JSON artifacts from buildkite_nightly_raw into data/results/<model_name>.

Recursively scans data/buildkite_nightly_raw for result_test_*.json and diffusion/benchmark perf JSON where either the
file path (POSIX) or the basename contains the given --model-keywords substring (so
e.g. qwen3_tts matches .../result_test_qwen3_tts_* even when the parent path only
mentions qwen3_omni).

Each file is copied to data/results/<model_name>/<build_id>/<basename>, where <build_id> is the first
path segment under buildkite_nightly_raw (Buildkite build number). Files not under a numeric build folder
use subdirectory _nogroup. This preserves history when the same basename appears in multiple builds
(previous versions deduplicated by basename and only kept the highest build, which dropped older runs).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_RAW_ROOT = DATA_DIR / "buildkite_nightly_raw"
RESULTS_ROOT = DATA_DIR / "results"

SAFE_MODEL_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def validate_model_name(name: str) -> str:
    if not SAFE_MODEL_NAME.match(name):
        raise argparse.ArgumentTypeError(
            "model_name must be a single directory segment (letters, digits, ._- only; no path separators)",
        )
    return name


def build_id_from_path(path: Path, raw_root: Path) -> int:
    """Return Buildkite build number from .../buildkite_nightly_raw/<id>/... or -1."""
    try:
        rel = path.relative_to(raw_root)
    except ValueError:
        return -1
    if not rel.parts:
        return -1
    head = rel.parts[0]
    try:
        return int(head)
    except ValueError:
        return -1


def iter_source_files(raw_root: Path, model_keywords: str) -> list[Path]:
    if not raw_root.is_dir():
        return []
    needle = model_keywords
    out: list[Path] = []
    for pattern in (
        "result_test_*.json",
        "diffusion_result_*.json",
        "benchmark_results_*.json",
    ):
        for path in raw_root.rglob(pattern):
            if needle not in path.as_posix() and needle not in path.name:
                continue
            if path.is_file():
                out.append(path)
    return out


def dest_subdir_for_source(path: Path, raw_root: Path) -> str:
    """Subdirectory name under data/results/<model_name>/ (numeric build id or _nogroup)."""
    bid = build_id_from_path(path, raw_root)
    return str(bid) if bid >= 0 else "_nogroup"


def sync_files(
    *,
    raw_root: Path,
    dest_dir: Path,
    model_keywords: str,
    dry_run: bool,
    move: bool,
    verbose: bool,
) -> int:
    sources = sorted(iter_source_files(raw_root, model_keywords))
    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for src in sources:
        sub = dest_subdir_for_source(src, raw_root)
        dst = dest_dir / sub / src.name
        if dry_run:
            if verbose:
                print(f"would {'move' if move else 'copy'} {src} -> {dst}")
            copied += 1
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        if move:
            if dst.exists():
                dst.unlink()
            shutil.move(str(src), str(dst))
            if verbose:
                print(f"moved {src} -> {dst}")
        else:
            shutil.copy2(src, dst)
            if verbose:
                print(f"copied {src} -> {dst}")
        copied += 1

    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--model-name",
        type=validate_model_name,
        required=True,
        help="Destination directory name under data/results/ (e.g. qwen3omni).",
    )
    parser.add_argument(
        "--model-keywords",
        required=True,
        help="Substring that must appear in the source path (POSIX) or in the filename (e.g. qwen3_omni, qwen3_tts).",
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=None,
        help=f"Override raw tree root (default: {DEFAULT_RAW_ROOT}).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without copying.")
    parser.add_argument("--move", action="store_true", help="Move files instead of copy (not recommended in CI).")
    parser.add_argument("--verbose", "-v", action="store_true", help="Log each file.")
    args = parser.parse_args(argv)

    raw_root = Path(args.raw_root).resolve() if args.raw_root else DEFAULT_RAW_ROOT
    dest_dir = (RESULTS_ROOT / args.model_name).resolve()
    if not str(dest_dir.resolve()).startswith(str(RESULTS_ROOT.resolve())):
        print("sync_buildkite_raw_model_results: refusing destination outside data/results", file=sys.stderr)
        return 2

    if not raw_root.is_dir():
        if args.verbose:
            print(f"sync_buildkite_raw_model_results: raw root missing ({raw_root}), nothing to do", file=sys.stderr)
        return 0

    copied = sync_files(
        raw_root=raw_root,
        dest_dir=dest_dir,
        model_keywords=args.model_keywords,
        dry_run=args.dry_run,
        move=args.move,
        verbose=args.verbose,
    )
    if args.verbose:
        label = args.model_name
        print(f"sync_buildkite_raw_model_results[{label}]: {'would sync' if args.dry_run else 'synced'} {copied} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
