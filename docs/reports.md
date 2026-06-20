---
hide:
  - toc
---

# Reports

<p class="dashboard-intro">
Browse archived Buildkite nightly and release test reports. Pick a report type card, choose a date, and read the full HTML snapshot below.
</p>

<section
  class="test-reports-page"
  data-test-reports-manifest="../assets/test_reports/manifest.json"
  markdown="1"
>

<div class="test-reports-panel" data-test-reports-panel>
  <div class="test-reports-panel__header">
    <div class="test-reports-type-cards" data-test-reports-type-tabs role="tablist" aria-label="Report type">
      <button
        type="button"
        role="tab"
        class="test-reports-type-card is-active"
        data-test-report-type="nightly"
        aria-selected="true"
      >Nightly</button>
      <button
        type="button"
        role="tab"
        class="test-reports-type-card"
        data-test-report-type="release"
        aria-selected="false"
      >Release</button>
    </div>
    <div class="test-reports-panel__date">
      <label class="test-reports-panel__date-label" for="test-report-date">Date</label>
      <select id="test-report-date" class="test-reports-date-select" data-test-report-date></select>
    </div>
  </div>
  <div class="test-reports-panel__body" data-test-reports-viewer>
    <iframe
      class="test-reports-frame"
      data-test-reports-frame
      title="Test report"
      loading="lazy"
      sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
    ></iframe>
    <div class="omni-empty-state test-reports-empty" data-test-reports-empty hidden>
      No reports available for this type yet. Add HTML files under
      <code>data/nightly_test_report/</code> or <code>data/release_test_report/</code> and rebuild the site.
    </div>
  </div>
</div>

<p class="test-reports-status" data-test-reports-status hidden></p>

</section>
