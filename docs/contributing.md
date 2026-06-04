# Contributing

## Add a model

Adding a model means wiring the same stable model identity through ingestion,
the dashboard snapshot build, PR attribution, and MkDocs pages.

1. Add the model key under `data/config.json` -> `models`.
2. Add the model identity under `dashboard/src/data/identity.json`.
   Keep `kanban_name` identical to the `data/config.json` model key.
3. Add variants under `scripts/test_variants.yml`.
   Each variant should match one stable workload with `file_glob`, and
   diffusion workloads should also set `inner_test_name` when a JSON file
   contains multiple test entries.
4. Add PR attribution in `scripts/pr_mapping.yml`.
   Include direct changed-file globs and title tags when the upstream PR title
   convention is stable.
5. If the model needs a MkDocs history page, add a `kanban_pages` entry in
   `data/config.json`, a `docs/models/<model-slug>.md` page, the chart builder
   hook in `scripts/generate_charts.py`, and raw-result sync entries in
   `scripts/mkdocs_hooks.py`.
6. Add the page to `mkdocs.yml` only when the model is actively tracked in the
   primary docs navigation.
7. Run the local fetch/chart generation and data verification commands before
   submitting the change.

### Archive a model

When a model stops receiving new data, keep the historical data and model page
available unless the data is invalid. Remove it from primary navigation if it is
no longer an active tracking target, and add a clearly labeled archived link on
the homepage instead.

Do not delete its identity, snapshots, or raw history unless there is an
explicit cleanup plan. Keeping the identity stable lets old reports and links
continue to render.

## Add hardware

Update `data/config.json` under `hardware` with a stable hardware key and display name.

## Add a metric

1. Add it to the relevant model's `required` or `optional` list
2. Update ingestion and report generation if it needs special handling
3. Add tests before implementation changes
