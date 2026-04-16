# Qwen3 Omni

<p class="dashboard-intro">
This page focuses on historical Qwen3 Omni nightly performance by full test configuration, including dataset, concurrency, prompt count, throughput, latency, and audio metrics.
</p>

<section
  class="omni-history-page"
  data-omni-history-src="../../assets/charts/qwen3_omni_history.json"
  markdown="1"
>

## Filters

<div class="omni-section">
  <div class="omni-section__header">
    <p>Search by model first, then narrow by test profile and runtime settings.</p>
  </div>
  <div class="omni-filter-bar" data-omni-history-filters></div>
</div>

<div class="omni-summary-grid" data-omni-history-summary></div>

## Trend Charts

<div class="omni-section">
  <div class="omni-section__header">
    <p>Each line represents one full configuration key over time.</p>
  </div>
  <div data-omni-history-charts></div>
</div>

## History Table

<div class="omni-section">
  <div class="omni-section__header">
    <p>Rows are grouped by run date (newest date first; expand/collapse each day). Within a day, newest run first.</p>
  </div>
  <div data-omni-history-table></div>
</div>

</section>
