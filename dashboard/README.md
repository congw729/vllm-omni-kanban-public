# vllm-omni Perf Dashboard

An Astro static site that reads the nightly Buildkite raw data already committed
to `data/buildkite_nightly_raw/` and renders per-model performance trend charts
with PR attribution — no aggregation pipeline required.

## Why this exists

The existing `process_results.py` aggregation has been failing since 2026-03-14,
so `docs/reports/` and `data/index.json` haven't refreshed.  This dashboard reads
`data/buildkite_nightly_raw/<build_id>/tests/dfx/perf/results/*.json` directly
and aggregates metrics client-side, staying fresh as long as raw data lands.

## Live URL (after merge + deploy)

`https://jiusiserve.github.io/vllm-omni-kanban/dashboard/`

The MkDocs site at `https://jiusiserve.github.io/vllm-omni-kanban/` is
unaffected — the deploy workflow uses `keep_files: true` so neither site wipes
the other.

## Local development

```bash
# From repo root: refresh data from local raw files
uv run python -m scripts.fetch_perf_local

# From this directory: start the dev server
cd dashboard
pnpm install
pnpm dev
# → http://localhost:4321/vllm-omni-kanban/dashboard/
```

## Data refresh (CI)

`.github/workflows/dashboard-sync.yml` runs daily at 03:45 UTC:

1. `scripts/fetch_perf_local.py` — reads `data/buildkite_nightly_raw/`, writes
   snapshot + manifest JSON to `dashboard/src/data/`
2. `scripts/fetch_prs.py` — walks `git log` on a local vllm-omni clone, buckets
   PRs by model, writes per-model PR feeds to `dashboard/src/data/prs/`
3. `scripts/verify_data.py` — schema + drift gate before committing
4. Commits changed `dashboard/src/data/` files to main

## Site deploy (CI)

`.github/workflows/dashboard-deploy.yml` triggers on any push to `main` that
touches `dashboard/**`:

1. `pnpm build` — produces `dashboard/dist/`
2. Publishes `dashboard/dist/` to `gh-pages` under the `dashboard/` subdirectory

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/fetch_perf_local.py` | Local-FS perf data extractor (reads `data/buildkite_nightly_raw/`) |
| `scripts/fetch_prs.py` | PR attribution via `git log` on a local vllm-omni clone |
| `scripts/verify_data.py` | Schema + drift gate |
| `scripts/test_variants.yml` | Declarative variant → file-glob mapping |
| `scripts/pr_mapping.yml` | Declarative PR → model bucketing rules |

## Tests

```bash
# Python unit tests (from repo root)
uv run pytest tests/python -q

# E2e smoke tests (from dashboard/)
cd dashboard
pnpm build && pnpm test:e2e
```
