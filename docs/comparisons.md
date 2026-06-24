---
hide:
  - toc
---

# Framework Comparison

<p class="dashboard-intro">
Compare one metric under the same test configuration. vLLM-Omni is shown as a multi-day trend, while selected SGLang dates are overlaid as comparison points and reference lines.
</p>

<section
  class="omni-history-page framework-comparison-page"
  data-framework-comparison-src="../assets/charts/framework_comparison.json"
  markdown="1"
>

## Filters

<div class="omni-section">
  <div class="omni-section__header">
    <p>Choose a comparable workload and the date range to inspect.</p>
  </div>
  <div class="omni-filter-bar comparison-control-bar" data-framework-comparison-controls></div>
</div>

## Selected Config

<div class="omni-summary-grid" data-framework-comparison-summary></div>

<div class="omni-section">
  <div class="omni-section__header">
    <p>Compact view of the workload currently shown in the chart.</p>
  </div>
  <div data-framework-comparison-config></div>
</div>

## Metric Comparison Chart

<div class="omni-section">
  <div class="omni-section__header">
    <p>Switch metrics here without returning to the filters. vLLM-Omni is rendered as a trend line, and SGLang is rendered as reference points and lines.</p>
  </div>
  <div data-framework-comparison-metrics></div>
  <div data-framework-comparison-chart></div>
</div>

## Raw Values

<div class="omni-section">
  <div class="omni-section__header">
    <p>Only records participating in the current chart are listed.</p>
  </div>
  <div data-framework-comparison-values></div>
</div>

</section>
