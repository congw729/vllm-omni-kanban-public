#!/usr/bin/env python3
"""Download nightly perf-related artifacts from a Buildkite build (build-level listing).

Keeps only basenames aligned with test-nightly perf uploads:
  - result_test_*.json, result_test_*.html
  - diffusion_result_*.json, diffusion_result_*.html (current CI prefix)
  - benchmark_results_*.json, benchmark_results_*.html (legacy until CI renames uploads)

Uses BUILDKITE_TOKEN or BUILDKITE_API_TOKEN (read_builds + read_artifacts scopes).

Default org / pipeline: vllm / vllm-omni (override with flags or BUILDKITE_ORG / BUILDKITE_PIPELINE*).
If --build is omitted, resolves the newest build on --branch whose message contains
--nightly-message-contains (default matches UI label "Scheduled nightly build").
By default --latest-build-state is any (passed and failed); failed runs may still have uploaded files.
When --build is omitted (auto-resolve), prints the newest 5 matching branch builds on stderr
before download. With explicit --build, listing is off by default; pass --list-matching-builds N
to show the newest N matching builds for context (or 0 to disable auto-resolve listing).
In GitHub Actions, pass --write-resolved-to-github-output to append resolved build metadata to GITHUB_OUTPUT.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

# When this module is imported as ``scripts.fetch_buildkite_nightly_files`` (e.g. pytest),
# ``sys.path`` has the repo root but not ``scripts/``, so a bare ``retry_utils`` import fails.
# Prepending this file's directory matches direct ``python scripts/...py`` behavior.
_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from retry_utils import with_retry


API_ROOT = "https://api.buildkite.com/v2"
DEFAULT_ORG = "vllm"
DEFAULT_PIPELINE = "vllm-omni"
DEFAULT_NIGHTLY_MESSAGE_SUBSTRING = "Scheduled nightly build"
LIST_BUILDS_PAGE_SIZE = 100
RECENT_MATCHING_BUILDS_MAX = 5
ALLOWED_BASENAME_PREFIXES = (
    "result_test_",
    "diffusion_result_",
    "benchmark_results_",
)
ALLOWED_BASENAME_SUFFIXES = (".json", ".html")


def token_from_env() -> str:
    for key in ("BUILDKITE_TOKEN", "BUILDKITE_API_TOKEN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    sys.stderr.write(
        "Missing token: set BUILDKITE_TOKEN or BUILDKITE_API_TOKEN.\n",
    )
    raise SystemExit(2)


@with_retry
def _request_json(url: str, token: str):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body.strip() else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        sys.stderr.write(f"HTTP {e.code} {e.reason} for {url}\n{detail}\n")
        raise


def build_matches_latest_nightly_criteria(
    build_rec: dict,
    *,
    message_contains: str,
    require_state: str | None,
) -> bool:
    """Whether a build record from the REST API matches scheduled-nightly selection."""
    if require_state is not None and build_rec.get("state") != require_state:
        return False
    msg = build_rec.get("message") or ""
    if message_contains and message_contains not in msg:
        return False
    return True


def first_matching_build_number(
    builds: list[dict],
    *,
    message_contains: str,
    require_state: str | None,
) -> str | None:
    """Return the first matching build number (API returns newest builds first per page)."""
    for item in builds:
        if not isinstance(item, dict):
            continue
        if not build_matches_latest_nightly_criteria(
            item, message_contains=message_contains, require_state=require_state
        ):
            continue
        num = item.get("number")
        if num is not None:
            return str(num)
    return None


def _append_matching_builds_until_cap(
    out: list[dict],
    page_items: list,
    *,
    message_contains: str,
    require_state: str | None,
    cap: int,
) -> None:
    for item in page_items:
        if not isinstance(item, dict):
            continue
        if not build_matches_latest_nightly_criteria(
            item, message_contains=message_contains, require_state=require_state
        ):
            continue
        out.append(item)
        if len(out) >= cap:
            return


def collect_matching_nightly_builds(
    org: str,
    pipeline: str,
    token: str,
    *,
    branch: str,
    message_contains: str,
    require_state: str | None,
    max_matches: int = RECENT_MATCHING_BUILDS_MAX,
) -> list[dict]:
    """Collect up to max_matches build dicts (newest first) from the pipeline branch."""
    out: list[dict] = []
    page = 1
    while len(out) < max_matches:
        url = _builds_list_url(org, pipeline, branch=branch, page=page)
        data = _request_json(url, token)
        if not isinstance(data, list):
            sys.stderr.write(
                f"Unexpected response (expected JSON array): {url}\n")
            sys.exit(1)
        if not data:
            break
        _append_matching_builds_until_cap(
            out,
            data,
            message_contains=message_contains,
            require_state=require_state,
            cap=max_matches,
        )
        if len(out) >= max_matches:
            break
        if len(data) < LIST_BUILDS_PAGE_SIZE:
            break
        page += 1
    return out


def write_recent_matching_builds_banner(
    matches: list[dict],
    *,
    branch: str,
    fetch_build: str,
    require_state: str | None,
) -> None:
    """Log the newest matching builds (stderr). fetch_build is the one selected for artifact download."""
    if not matches:
        return
    state_note = "build state: any (passed, failed, …)" if require_state is None else f"build state must be {require_state!r}"
    print(
        f"Newest {len(matches)} build(s) on branch {branch!r} matching message filter ({state_note}, newest first):",
        file=sys.stderr,
    )
    for i, rec in enumerate(matches, start=1):
        num = rec.get("number")
        st = rec.get("state")
        msg = rec.get("message") or ""
        one_line = " ".join(msg.split())
        if len(one_line) > 120:
            one_line = one_line[:117] + "..."
        mark = " <- fetching artifacts" if fetch_build and str(
            num) == str(fetch_build) else ""
        print(f"  {i}. #{num}  state={st}  {one_line}{mark}", file=sys.stderr)


def _builds_list_url(org: str, pipeline: str, *, branch: str, page: int) -> str:
    o = urllib.parse.quote(org)
    pl = urllib.parse.quote(pipeline)
    q = urllib.parse.urlencode(
        {
            "branch": branch,
            "page": page,
            "per_page": LIST_BUILDS_PAGE_SIZE,
        }
    )
    return f"{API_ROOT}/organizations/{o}/pipelines/{pl}/builds?{q}"


def _build_show_url(org: str, pipeline: str, build: str) -> str:
    o = urllib.parse.quote(org)
    pl = urllib.parse.quote(pipeline)
    b = urllib.parse.quote(build)
    return f"{API_ROOT}/organizations/{o}/pipelines/{pl}/builds/{b}"


def _artifact_list_url(org: str, pipeline: str, build: str) -> str:
    o = urllib.parse.quote(org)
    pl = urllib.parse.quote(pipeline)
    b = urllib.parse.quote(build)
    return f"{API_ROOT}/organizations/{o}/pipelines/{pl}/builds/{b}/artifacts"


def fetch_build_metadata(org: str, pipeline: str, build_no: str, token: str) -> tuple[str, str]:
    """Best-effort (commit_sha, web_url) for GitHub Actions commit metadata."""
    url = _build_show_url(org, pipeline, build_no)
    try:
        data = _request_json(url, token)
    except (urllib.error.HTTPError, OSError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    commit = ""
    c = data.get("commit")
    if isinstance(c, str):
        commit = c.strip()
    elif isinstance(c, dict):
        commit = str(c.get("id") or c.get("sha") or "").strip()
    web = str(data.get("web_url") or data.get("url") or "").strip()
    return commit, web


def append_resolved_build_github_output(
    *,
    build_no: str,
    commit: str,
    web_url: str,
) -> None:
    """Append named outputs for GitHub Actions (respects GITHUB_OUTPUT)."""
    out_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not out_path:
        return
    pairs = {
        "resolved_build_number": build_no,
        "resolved_commit": commit,
        "resolved_build_url": web_url,
    }
    with open(out_path, "a", encoding="utf-8") as fh:
        for key, value in pairs.items():
            if "\n" in value:
                delim = "GITHUB_OUTPUT_EOF"
                fh.write(f"{key}<<{delim}\n{value}\n{delim}\n")
            else:
                fh.write(f"{key}={value}\n")


def fetch_all_artifact_records(org: str, pipeline: str, build: str, token: str) -> list[dict]:
    base_url = _artifact_list_url(org, pipeline, build)
    out: list[dict] = []
    page = 1
    while True:
        url = f"{base_url}?page={page}"
        data = _request_json(url, token)
        if not isinstance(data, list):
            sys.stderr.write(
                f"Unexpected response (expected JSON array): {url}\n")
            sys.exit(1)
        if not data:
            break
        for item in data:
            if isinstance(item, dict):
                out.append(item)
        page += 1
    return out


def _safe_relative_artifact_path(path: str) -> PurePosixPath:
    p = PurePosixPath(path)
    if p.is_absolute():
        raise ValueError(f"absolute artifact path not allowed: {path!r}")
    for part in p.parts:
        if part == "..":
            raise ValueError(f"invalid artifact path: {path!r}")
    return p


class StripAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = urllib.request.HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, headers, newurl)
        if new_req is None:
            return None
        old_host = urllib.parse.urlparse(req.full_url).netloc
        new_host = urllib.parse.urlparse(newurl).netloc
        if old_host != new_host and new_req.has_header("Authorization"):
            new_req.remove_header("Authorization")
        return new_req


@with_retry
def _download_file(download_url: str, dest: str, token: str) -> None:
    req = urllib.request.Request(
        download_url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    opener = urllib.request.build_opener(StripAuthOnRedirect)
    with opener.open(req, timeout=300) as resp:
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)


def is_nightly_sync_artifact_basename(filename: str) -> bool:
    """Return True if basename should be downloaded (nightly perf JSON/HTML, same stem rules)."""
    name = PurePosixPath(filename).name
    return name.startswith(ALLOWED_BASENAME_PREFIXES) and name.endswith(ALLOWED_BASENAME_SUFFIXES)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Buildkite nightly perf files (result_test_* / diffusion_* / benchmark_results_*; .json and .html) "
        "for one build. Omit --build to auto-pick the latest main nightly (see --branch / --nightly-message-contains).",
    )
    env_org = os.environ.get("BUILDKITE_ORG", "").strip()
    env_pipe = os.environ.get("BUILDKITE_PIPELINE", os.environ.get(
        "BUILDKITE_PIPELINE_SLUG", "")).strip()
    parser.add_argument(
        "--org",
        default=env_org or DEFAULT_ORG,
        required=False,
        help=f"Buildkite org slug (default: {DEFAULT_ORG} or BUILDKITE_ORG)",
    )
    parser.add_argument(
        "--pipeline",
        default=env_pipe or DEFAULT_PIPELINE,
        required=False,
        help=f"Pipeline slug (default: {DEFAULT_PIPELINE} or BUILDKITE_PIPELINE / BUILDKITE_PIPELINE_SLUG)",
    )
    parser.add_argument(
        "--build",
        default=None,
        help="Build number (UI number). If omitted, resolves latest matching nightly on --branch.",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help='Branch when auto-resolving nightly (default: main); ignored when --build is set.',
    )
    parser.add_argument(
        "--nightly-message-contains",
        default=DEFAULT_NIGHTLY_MESSAGE_SUBSTRING,
        metavar="SUBSTR",
        help=f'Substring for build message when auto-resolving (default: "{DEFAULT_NIGHTLY_MESSAGE_SUBSTRING}")',
    )
    parser.add_argument(
        "--latest-build-state",
        default="any",
        metavar="STATE",
        help='When matching nightly builds on a branch, require this Buildkite build state (default: any = passed or failed). Use "passed" to only pick successful builds.',
    )
    parser.add_argument(
        "--list-matching-builds",
        type=int,
        metavar="N",
        default=-1,
        help=(
            "List the N newest builds on --branch matching the nightly message/state filter on stderr. "
            f"Default: {RECENT_MATCHING_BUILDS_MAX} if --build is omitted; 0 if --build is set. "
            "Use 0 with no --build to disable listing (then auto-resolve is unavailable). "
            "Any N>0 forces listing even with explicit --build."
        ),
    )
    parser.add_argument(
        "--output-dir", default="buildkite-nightly-files", help="Output directory root")
    parser.add_argument(
        "--state",
        default="finished",
        help="Only artifacts in this state (default: finished); use empty string for any",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="List only, no download")
    parser.add_argument(
        "--write-resolved-to-github-output",
        action="store_true",
        help="Append resolved_build_number, resolved_commit, resolved_build_url to $GITHUB_OUTPUT (for Actions).",
    )
    args = parser.parse_args()

    org = args.org.strip()
    pipeline = args.pipeline.strip()
    if not org or not pipeline:
        sys.stderr.write("Provide non-empty --org and --pipeline.\n")
        sys.exit(2)

    token = token_from_env()
    output_dir = os.path.abspath(args.output_dir)

    req_raw = (args.latest_build_state or "").strip().lower()
    require_state: str | None = None if req_raw in (
        "", "any") else args.latest_build_state.strip()
    branch_clean = args.branch.strip()

    build_no = (args.build or "").strip()
    explicit_build = bool(build_no)
    if args.list_matching_builds < 0:
        list_n = 0 if explicit_build else RECENT_MATCHING_BUILDS_MAX
    else:
        list_n = max(0, int(args.list_matching_builds))
    if list_n > 0:
        recent = collect_matching_nightly_builds(
            org,
            pipeline,
            token,
            branch=branch_clean,
            message_contains=args.nightly_message_contains,
            require_state=require_state,
            max_matches=list_n,
        )
        if not build_no:
            if not recent:
                sys.stderr.write(
                    "No build on this branch matched the nightly message filter. "
                    "Try an explicit --build <number>, or adjust --branch / --nightly-message-contains / --latest-build-state.\n",
                )
                sys.exit(2)
            build_no = first_matching_build_number(
                recent,
                message_contains=args.nightly_message_contains,
                require_state=require_state,
            ) or ""
            if not build_no:
                sys.stderr.write("Resolved build list missing build number.\n")
                sys.exit(2)
            write_recent_matching_builds_banner(
                recent, branch=branch_clean, fetch_build=build_no, require_state=require_state
            )
            print(
                f"Using build number {build_no} (org={org} pipeline={pipeline} branch={branch_clean})",
                file=sys.stderr,
            )
        else:
            write_recent_matching_builds_banner(
                recent, branch=branch_clean, fetch_build=build_no, require_state=require_state
            )
            print(
                f"Fetching artifacts for explicit --build {build_no} (org={org} pipeline={pipeline})",
                file=sys.stderr,
            )
    elif not build_no:
        sys.stderr.write(
            "No --build given and --list-matching-builds is 0; cannot auto-resolve. "
            "Pass --build or a positive --list-matching-builds.\n",
        )
        sys.exit(2)

    records = fetch_all_artifact_records(org, pipeline, build_no, token)
    if not records:
        sys.stderr.write(
            "No artifacts are listed for this Buildkite build (API returned none). "
            "Possible causes: run canceled or failed before any upload, wrong build number, or artifacts expired.\n",
        )
        sys.exit(1)

    state_filter = (args.state or "").strip().lower()
    n_ok = 0
    overwritten_count = 0
    for rec in records:
        st = str(rec.get("state", "")).lower()
        if state_filter and st != state_filter:
            continue
        path = rec.get("path")
        download_url = rec.get("download_url")
        if not path or not download_url:
            continue
        filename = rec.get("filename") or PurePosixPath(str(path)).name
        filename = str(filename)
        if not is_nightly_sync_artifact_basename(filename):
            continue
        try:
            rel = _safe_relative_artifact_path(str(path))
        except ValueError as e:
            sys.stderr.write(f"skip unsafe path {path!r}: {e}\n")
            continue
        dest = os.path.join(output_dir, *rel.parts)
        if args.dry_run:
            print(f"would download: {path} -> {dest}")
            n_ok += 1
            continue
        if os.path.exists(dest):
            print(f"overwriting existing file: {dest}")
            overwritten_count += 1
        print(f"downloading: {path} -> {dest}")
        _download_file(str(download_url), dest, token)
        n_ok += 1
    print(
        f"downloaded file count: {n_ok}; overwritten existing: {overwritten_count}")

    if n_ok == 0:
        sys.stderr.write(
            "No nightly sync files to download: nothing matched allowed prefixes "
            f"{ALLOWED_BASENAME_PREFIXES} with suffix .json or .html "
            f"for build {build_no} (after artifact --state filter).\n"
            "Failed or partial runs sometimes upload only some steps' files; if perf steps did upload, "
            "they may use other filenames or artifact rows may not be in the default finished state.\n",
        )
        if state_filter:
            sys.stderr.write(
                f"Hint: current --state is {args.state!r}; try --state \"\" to include non-finished artifact states.\n",
            )
        sys.stderr.write(
            f"Hint: this build has {len(records)} total artifact row(s) from the API; check paths if expecting other names.\n",
        )
        basenames: list[str] = []
        seen: set[str] = set()
        for rec in records:
            path = rec.get("path")
            if not path:
                continue
            fn = str(rec.get("filename") or PurePosixPath(str(path)).name)
            if fn and fn not in seen:
                seen.add(fn)
                basenames.append(fn)
        if basenames:
            preview = basenames[:60]
            sys.stderr.write(
                f"Artifact basenames in this build (first {len(preview)} of {len(basenames)} unique; compare to allowed prefixes):\n",
            )
            for name in preview:
                sys.stderr.write(f"  {name}\n")
        sys.exit(1)

    if args.write_resolved_to_github_output:
        meta_c, meta_u = fetch_build_metadata(org, pipeline, build_no, token)
        append_resolved_build_github_output(
            build_no=build_no, commit=meta_c, web_url=meta_u)


if __name__ == "__main__":
    main()
