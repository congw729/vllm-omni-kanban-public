# Qwen3 Omni — Buildkite Raw Ingest & Filename Schema Plan

**Date:** 2026-04-02  
**Last updated:** 2026-04-02  
**Status:** In progress (sync + MkDocs hook implemented; Qwen3 Omni **history** pipeline items in §8.2 still open)  
**References:** [Kanban design](2025-03-13-kanban-design.md) · [Implementation plan](2026-03-13-implementation-plan.md)

---

## 1. Background

The Qwen3 Omni page (`docs/models/qwen3-omni.md`) depends on `generate_charts.py` reading `result_test_*.json` under `data/results/qwen3omni/`, aggregating them into `docs/assets/charts/qwen3_omni_history.json`, which `render_charts.js` then renders.

Nightly artifacts land first under **`data/buildkite_nightly_raw/<build_number>/...`** (via `fetch_buildkite_nightly_files.py` and Actions). This plan adds a **repeatable sync** from that tree into `data/results/<model_name>/` and wires it into **local MkDocs** runs.

---

## 2. Goals

1. **Automated sync:** Scan `data/buildkite_nightly_raw/` for JSON result files matching a configurable path substring (`--model-keywords`) and copy them into `data/results/<model_name>/` as the canonical input for `generate_charts.py` (e.g. `qwen3omni` must match `kanban_pages.qwen3_omni_history.source_dir` in `config.json`).
2. **File contents win:** Any field already present in the JSON (e.g. `num_prompts`, `max_concurrency`, `request_rate`, `date`, …) **must** take precedence over filename-derived values; filename parsing is fallback or supplemental for `test_name` / `dataset_name` / ordering.
3. **Fix random-mm floats in filenames:** In `result_test_qwen3_omni_*random-mm_0.1_10_<ts>.json`, `0.1` is **request rate**, not `max_concurrency`; that segment must not be passed through `int()`. Display and grouping for rate must follow the in-file `request_rate`.
4. **Correct grouping:** Workloads swept by **request rate** must include **`request_rate`** (or an equivalent field) in the grouping dimensions so different rates are not merged into one configuration series.

---

## 3. Current flow (as implemented vs remaining)

| Step | Behavior |
|------|----------|
| Fetch | CI or local `fetch_buildkite_nightly_files.py` writes under `data/buildkite_nightly_raw/<build>/...`. |
| Collect | **`scripts/sync_buildkite_raw_model_results.py`** copies `result_test_*.json` paths containing `--model-keywords` into `data/results/<model-name>/`. Same basename under multiple builds: **higher numeric build folder wins**, then **newer mtime**. If `data/buildkite_nightly_raw` is missing, the script **exits 0** and does nothing. |
| **MkDocs** | **`mkdocs serve`** and **`mkdocs build`** load `mkdocs.yml` → **`hooks`** → **`scripts/mkdocs_hooks.py`**. **`on_startup`** runs each entry in **`_BUILDKITE_RAW_SYNCS`** (currently `("qwen3omni", "qwen3_omni")`) via the sync script, then runs **`generate_charts.py`**. **Important:** `on_startup` runs **once per MkDocs process** (when `serve` / `build` starts), **not** on every live-reload rebuild. After adding new files under `buildkite_nightly_raw`, **restart `mkdocs serve`** or run `sync_buildkite_raw_model_results.py` + `generate_charts.py` manually to refresh charts. |
| Charts / page | `generate_charts.py` builds `qwen3_omni_history.json`; the Omni page consumes it. Until §8.2 is done, **`random-mm`** filenames with a **float** third segment are **skipped** by `parse_qwen3_omni_filename`, and runs that differ only by **`request_rate`** may be **merged** incorrectly (see §8.2). |

---

## 4. Target data pipeline (reference diagram)

### 4.1 End-to-end

```
data/buildkite_nightly_raw/
  └── <build>/.../result_test_*.json   # path contains --model-keywords
           │
           │  sync_buildkite_raw_model_results.py (copy; see §5)
           ▼
data/results/<model_name>/
           │
           ▼
scripts/generate_charts.py  →  docs/assets/charts/qwen3_omni_history.json (and other charts)
```

### 4.2 Local developer entry point

- Run from repo root: **`mkdocs serve`** (or **`mkdocs build`**).
- No separate manual sync step is required for the **first** load **if** raw data already exists under `data/buildkite_nightly_raw/`.
- After updating raw on disk, **restart the dev server** (or run the two scripts by hand) so `on_startup` runs again — see §3.
- To add another model later: extend **`_BUILDKITE_RAW_SYNCS`** in `scripts/mkdocs_hooks.py` with a new `(model_name, model_keywords)` pair, and ensure `generate_charts` / any dedicated page reads from `data/results/<model_name>/`.

### 4.3 CI (optional follow-up)

- Run **sync** before `generate_charts` in **GitHub Actions** (e.g. after nightly fetch) so committed `data/results/` and charts match the latest raw pull in one commit.
- Sequence: `fetch` → `sync_buildkite_raw_model_results.py` (per model) → `generate_charts.py`.

---

## 5. Technical design

### 5.1 Scan scope and matching

- **Root:** `data/buildkite_nightly_raw/` (recursive), overridable with `--raw-root`.
- **Files:** `result_test_*.json` only (`rglob`).
- **Match:** full path must contain the **`--model-keywords`** string (POSIX path, case-sensitive). Example for Qwen3 Omni: `qwen3_omni`.

### 5.2 Sync semantics (copy vs move)

| Mode | Use | Notes |
|------|-----|-------|
| **Copy (default)** | CI / local dev / MkDocs hook | Keeps `buildkite_nightly_raw` intact; idempotent overwrites in `data/results/<model_name>/`. |
| **Move** | Local cleanup only | `--move`; **not** used by MkDocs hook. |

**Multi-build collisions:** Prefer **higher build directory number**, then **newer `st_mtime`**.

### 5.3 Sync script (implemented)

- **Path:** `scripts/sync_buildkite_raw_model_results.py`
- **CLI:** `--model-name <dir under data/results/>` (validated single segment), **`--model-keywords <substring>`** (required), optional `--raw-root`, `--dry-run`, `--move`, `-v`.
- **MkDocs:** `scripts/mkdocs_hooks.py` invokes it once per tuple in **`_BUILDKITE_RAW_SYNCS`**.

### 5.4 `generate_charts.py`: filename parsing + JSON first (§8.2)

**Merge order** after loading each `result_test_*.json`:

1. From **file body:** `num_prompts`, `max_concurrency`, `request_rate`, `date`, plus existing fields such as `endpoint_type`, `backend`, `model_id`, `tokenizer_id`.
2. From **filename:** `test_name`, `dataset_name`, and fallbacks only when missing from the file.
3. **Overrides:** Values from step 1 **win** where defined; **`request_rate`** must match JSON when the key is present (including numeric vs `"inf"`).

**`random-mm` / float slot:** If the third-from-end filename segment parses as **float**, treat as request-rate encoding; **do not** `int()` it.

**Timestamps:** Prefer **`date` in JSON** (`%Y%m%d-%H%M%S` style as in artifacts) for `sort_timestamp` / display `date` when parseable; else filename timestamp.

### 5.5 Grouping / filters: `request_rate` (§8.2)

- Add **`request_rate`** to `QWEN3_OMNI_GROUP_FIELDS` in `generate_charts.py`.
- Add **`request_rate`** to `kanban_pages.qwen3_omni_history.filters` and `table_columns` in `data/config.json`.
- Normalize numeric vs `"inf"` / missing consistently in grouping keys (align with §9 open questions if needed).

### 5.6 Front end (§8.2)

- **`render_charts.js`:** Extend `buildSeriesLabel`, chart tooltip `meta`, and any legend text so **`request_rate`** is visible when present (e.g. `rr=`), so series do not look identical when only rate differs.

---

## 6. Testing plan (TDD order)

1. **`parse_qwen3_omni_filename` / merge helper** — `random-mm` + `0.1` + valid timestamp; JSON overrides for `request_rate`, `max_concurrency`, `date`.
2. **`load_qwen3_omni_history`** — records previously skipped (float filename slot); distinct groups for distinct `request_rate`.
3. **`sync_buildkite_raw_model_results`** — `tests/unit/test_sync_buildkite_raw_model_results.py` (keyword filter, collision policy).
4. **Regression:** `pytest` + **`mkdocs serve`** (after restart if raw changed) → open Qwen3 Omni page.

---

## 7. Documentation & ops

- **Local preview:** **`mkdocs serve`** / **`build`** triggers sync + `generate_charts` via **`mkdocs.yml` → `hooks` → `scripts/mkdocs_hooks.py`** (see §3 for `on_startup` frequency).
- Optional: one line in `contributing.md` pointing to this plan.

---

## 8. Checklist

### 8.1 Done

- [x] `scripts/sync_buildkite_raw_model_results.py` + unit tests (`tests/unit/test_sync_buildkite_raw_model_results.py`)
- [x] `mkdocs.yml` → `hooks` → `scripts/mkdocs_hooks.py` (`_BUILDKITE_RAW_SYNCS` + `generate_charts.py`)

### 8.2 TODO — `generate_charts.py` / `request_rate` / UI (remaining product work)

- [ ] **`parse_qwen3_omni_filename`:** If `parts[-3]` is a **float** (e.g. `0.1`), treat as **request-rate slot** in the filename; **do not** call `int()` on it. If it is an **int**, treat as **`max_concurrency`** in the filename. Reject truly invalid segments.
- [ ] **`load_qwen3_omni_history` merge:** **JSON first** for `num_prompts`, `max_concurrency`, `request_rate`, `date` / `sort_timestamp` when present; filename fills gaps and supplies `test_name` / `dataset_name`. If JSON has **`max_concurrency: null`**, do **not** overwrite with a bogus int from a float slot.
- [ ] **`QWEN3_OMNI_GROUP_FIELDS`:** Append **`request_rate`** (order near `num_prompts`) so `config_key` / grouping / `qwen3_omni_history.json` split rate-swept configs.
- [ ] **`data/config.json`:** Add **`request_rate`** to `kanban_pages.qwen3_omni_history.filters` and `table_columns`.
- [ ] **`docs/assets/js/render_charts.js`:** Show **`request_rate`** in series labels / tooltip meta (and any other place where `mc` / `np` are shown).
- [ ] **`tests/unit/test_generate_charts.py`:** Cover float filename + JSON `request_rate`; cover different rates → different groups; cover JSON `date` driving sort/display.

### 8.3 Optional / verification

- [ ] `.github/workflows/...`: run sync (per model) + `generate_charts` before commit or deploy when desired.
- [ ] Manual check on a real `buildkite_nightly_raw` tree: `qwen3_omni_history.json` **record_count** includes `random-mm` rows; multiple **`request_rate`** values appear as separate series/groups.

---

## 9. Open questions

1. Restrict sync to `tests/dfx/perf/results/` subtree?  
2. Placeholder for **missing** `request_rate` in grouping keys vs concurrency-only runs?  
3. Disallow `--move` in CI only (document for local use)?  

---

**Next step:** Complete §8.2, then §8.3 verification.
