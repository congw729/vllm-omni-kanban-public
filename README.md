# vLLM-Omni Kanban

Monitoring dashboard for vLLM multimodal model stability, performance, and accuracy across hardware platforms. Tracks daily CI results with 90-day retention and alerting.

## Features

- **Models:** Qwen-image, Qwen-Image-edit, WAN2.2, Qwen3-Omni, Qwen3-TTS
- **Hardware:** NVIDIA A100/H100/H20, AMD MI300X, Ascend NPU A2, Ascend NPU A3
- **Metrics:** Pass rate, latency (p50/p99), throughput, TTFT, benchmark scores
- **90-day rolling retention**, daily Markdown reports, alerts (absolute + regression), WeChat & Email notifications

## Quick Start

```bash
pip install -r requirements.txt
pytest
mkdocs build --strict
```

To preview locally:

```bash
mkdocs serve
```

Core scripts:

- `scripts/process_results.py`: validate inputs, maintain one daily snapshot per `(date, hardware, model)`, prune old data, generate reports
- `scripts/check_alerts.py`: evaluate absolute thresholds and 7-day regressions, persist alert history, send notifications
- `scripts/generate_charts.py`: build JSON chart payloads for the dashboard
- `scripts/fetch_latest_results.py`: fetch the scheduled daily batch from an external source

## Docs

Run `mkdocs serve` to preview the site locally, or `mkdocs build --strict` for a production build.

## Dashboard

A live Astro trend dashboard that reads `data/buildkite_nightly_raw/` directly is available at `dashboard/` — see [dashboard/README.md](dashboard/README.md) for details.

## License

Apache-2.0
