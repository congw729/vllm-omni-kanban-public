---
hide:
  - toc
---

# vLLM-Omni Kanban

<p class="dashboard-intro">
This dashboard tracks one daily snapshot per model and hardware combination for vLLM-omni multimodal CI. Open the dedicated model pages for metric-specific performance analysis.
</p>

## Model Performance

<p class="section-note">Open a dedicated page for each model family to inspect the metrics that matter for that workload.</p>

<div class="model-directory-grid">
  <a class="model-directory-card" href="models/qwen3-omni/">
    <span class="model-directory-card__eyebrow">Multimodal</span>
    <strong>Qwen3 Omni</strong>
    <span>TTFT, TPOT, TTFP, RTF, throughput</span>
  </a>
  <a class="model-directory-card" href="models/qwen3-tts/">
    <span class="model-directory-card__eyebrow">Audio Synthesis</span>
    <strong>Qwen3 TTS</strong>
    <span>TTFT, TPOT, TTFP, RTF, throughput</span>
  </a>
  <a class="model-directory-card" href="models/qwen-image/">
    <span class="model-directory-card__eyebrow">Image Generation</span>
    <strong>Qwen Image</strong>
    <span>E2E latency, peak memory</span>
  </a>
  <a class="model-directory-card" href="models/qwen-image-layered/">
    <span class="model-directory-card__eyebrow">Image Generation</span>
    <strong>Qwen Image Layered</strong>
    <span>E2E latency, peak memory</span>
  </a>
  <a class="model-directory-card" href="models/qwen-image-edit/">
    <span class="model-directory-card__eyebrow">Image Editing</span>
    <strong>Qwen Image Edit</strong>
    <span>E2E latency, peak memory</span>
  </a>
  <a class="model-directory-card" href="models/qwen-image-edit-2511/">
    <span class="model-directory-card__eyebrow">Image Editing</span>
    <strong>Qwen Image Edit 2511</strong>
    <span>E2E latency, peak memory</span>
  </a>
  <a class="model-directory-card" href="models/wan22/">
    <span class="model-directory-card__eyebrow">Video Generation</span>
    <strong>WAN 2.2</strong>
    <span>E2E latency, peak memory</span>
  </a>
  <a class="model-directory-card" href="models/hunyuan-image3/">
    <span class="model-directory-card__eyebrow">Image Editing</span>
    <strong>Hunyuan Image 3</strong>
    <span>E2E latency, throughput, peak memory</span>
  </a>
  <a class="model-directory-card" href="models/bagel/">
    <span class="model-directory-card__eyebrow">Image Generation</span>
    <strong>BAGEL</strong>
    <span>Single-stage and multi-stage image workloads</span>
  </a>
  <a class="model-directory-card" href="models/voxcpm2/">
    <span class="model-directory-card__eyebrow">Audio Synthesis</span>
    <strong>VoxCPM2</strong>
    <span>RTF, TTFP, E2E latency, throughput</span>
  </a>
</div>

## Recent Alerts

Open the [Alerts](alerts.md) page for the latest persisted alert history.

## Reports

Browse [Reports](reports.md) for nightly and release HTML test snapshots.
