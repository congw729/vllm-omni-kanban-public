const charts = new Map();
let resizeBound = false;

/** Metric groups in the main trend grid before "More charts" (through Audio TTFP; Audio Duration stays under More). */
const OMNI_HISTORY_PRIMARY_CHART_COUNT = 8;

function isDashboardHome() {
  return Boolean(document.querySelector("[data-dashboard-home]"));
}

function cloneOption(option) {
  if (Array.isArray(option)) {
    return option.map((item) => cloneOption(item));
  }
  if (option && typeof option === "object") {
    const cloned = {};
    Object.entries(option).forEach(([key, value]) => {
      cloned[key] = cloneOption(value);
    });
    return cloned;
  }
  return option;
}

function chartPalette() {
  const styles = getComputedStyle(document.body);
  return {
    text: styles.getPropertyValue("--dashboard-chart-text").trim() || "#5b6775",
    grid: styles.getPropertyValue("--dashboard-chart-grid").trim() || "rgba(148, 163, 184, 0.18)",
    tooltipBg: styles.getPropertyValue("--dashboard-tooltip-bg").trim() || "rgba(15, 23, 42, 0.92)",
    tooltipBorder: styles.getPropertyValue("--dashboard-tooltip-border").trim() || "rgba(148, 163, 184, 0.24)",
    tooltipText: styles.getPropertyValue("--dashboard-tooltip-text").trim() || "#f8fafc",
  };
}

/** Baseline markLine / label colors — neutral vs. data series; theme-aware via dashboard.css */
function omniBaselineChrome() {
  const styles = getComputedStyle(document.body);
  return {
    line: styles.getPropertyValue("--omni-baseline-line").trim() || "#64748b",
    labelBg: styles.getPropertyValue("--omni-baseline-label-bg").trim() || "rgba(241, 245, 249, 0.96)",
    labelFg: styles.getPropertyValue("--omni-baseline-label-fg").trim() || "#0f172a",
    labelBorder: styles.getPropertyValue("--omni-baseline-label-border").trim() || "rgba(100, 116, 139, 0.45)",
  };
}

/** ECharts default categorical palette — must match per-series assignment so legend / line / symbol stay aligned. */
const OMNI_LINE_SERIES_PALETTE = [
  "#5470c6",
  "#91cc75",
  "#fac858",
  "#ee6666",
  "#73c0de",
  "#3ba272",
  "#fc8452",
  "#9a60b4",
  "#ea7ccc",
];

/** Path and style for "bad / bridged" day markers (X); series-level so hover can show/hide without per-point itemStyle override. */
const OMNI_BAD_DAY_MARK_SYMBOL = "path://M-5,-5 L5,5 M5,-5 L-5,5";
const OMNI_BAD_DAY_MARK_SIZE = 10;
const OMNI_BAD_DAY_MARK_ITEM_STYLE = {
  color: "#dc2626",
  borderColor: "#dc2626",
  borderWidth: 2,
};

/**
 * Data lines use palette; baseline uses neutral slate (see omniBaselineChrome) for contrast.
 */
function applyOmniLineSeriesColors(seriesList) {
  const bl = omniBaselineChrome();
  let linePaletteIndex = 0;
  seriesList.forEach((s) => {
    if (s.__omniBadMarkers) {
      return;
    }
    const i = linePaletteIndex;
    linePaletteIndex += 1;
    const c = OMNI_LINE_SERIES_PALETTE[i % OMNI_LINE_SERIES_PALETTE.length];
    s.color = c;
    s.lineStyle = { width: 2.5, ...(s.lineStyle || {}), color: c };
    s.itemStyle = { ...(s.itemStyle || {}), color: c };
    s.emphasis = {
      focus: "series",
      blurScope: "coordinateSystem",
      scale: false,
      ...(s.emphasis || {}),
      lineStyle: { ...(s.emphasis?.lineStyle || {}), color: c, width: 3 },
      itemStyle: { ...(s.emphasis?.itemStyle || {}), color: c },
    };
    s.blur = {
      lineStyle: { opacity: 0, width: 1 },
      itemStyle: { opacity: 0 },
    };
    if (s.markLine) {
      const ml = s.markLine;
      const labelFmt = ml.label?.formatter;
      // Series-level clip also affects markLine graphics in ECharts; disable so the label pill is not cropped.
      s.clip = false;
      s.markLine = {
        ...ml,
        // Avoid grid clipPath cutting off the baseline label at the left edge (see ECharts markLine + label).
        clip: false,
        lineStyle: {
          type: "dashed",
          width: 2,
          ...(ml.lineStyle || {}),
          color: bl.line,
          opacity: 0,
        },
        label: {
          ...(ml.label || {}),
          show: false,
          position: "start",
          // Nudge right from the line start so the pill sits inside the grid (see grid.left reserve).
          distance: [10, 2 + i * 14],
          color: bl.labelFg,
          backgroundColor: bl.labelBg,
          borderColor: bl.labelBorder,
          borderWidth: 1,
          borderRadius: 4,
          padding: [6, 12],
          fontSize: 11,
          fontWeight: 600,
          // Default truncate can hide digits; keep full "baseline …" string visible inside the pill.
          overflow: "none",
          confine: false,
          formatter: labelFmt,
        },
      };
    }
  });
  return seriesList;
}

function patchAxis(axis, colors) {
  if (!axis) {
    return axis;
  }
  const axes = Array.isArray(axis) ? axis : [axis];
  axes.forEach((entry) => {
    entry.axisLabel = { ...(entry.axisLabel || {}), color: colors.text };
    entry.axisLine = { ...(entry.axisLine || {}), lineStyle: { color: colors.grid } };
    entry.axisTick = { ...(entry.axisTick || {}), lineStyle: { color: colors.grid } };
    if (entry.type === "value" || entry.splitLine) {
      entry.splitLine = {
        ...(entry.splitLine || {}),
        lineStyle: { color: colors.grid },
      };
    }
  });
  return axis;
}

function applyTheme(option) {
  const colors = chartPalette();
  const themed = cloneOption(option);
  themed.backgroundColor = "transparent";
  themed.textStyle = { ...(themed.textStyle || {}), color: colors.text };
  themed.tooltip = {
    ...(themed.tooltip || {}),
    backgroundColor: colors.tooltipBg,
    borderColor: colors.tooltipBorder,
    textStyle: { ...(themed.tooltip?.textStyle || {}), color: colors.tooltipText },
  };
  if (themed.legend) {
    themed.legend = { ...(themed.legend || {}), textStyle: { ...(themed.legend.textStyle || {}), color: colors.text } };
  }
  if (themed.visualMap) {
    themed.visualMap = {
      ...(themed.visualMap || {}),
      textStyle: { ...(themed.visualMap.textStyle || {}), color: colors.text },
    };
  }
  themed.xAxis = patchAxis(themed.xAxis, colors);
  themed.yAxis = patchAxis(themed.yAxis, colors);
  return themed;
}

function chartSrc(container, range) {
  if (container.dataset.chartBase) {
    const base = container.dataset.chartBase;
    return base.includes("/") ? `${base}_${range}.json` : `assets/charts/${base}_${range}.json`;
  }
  return container.dataset.chartSrc || "";
}

function selectedRange() {
  const picker = document.querySelector("[data-time-range]");
  return picker?.value || "7d";
}

async function fetchJson(src) {
  const response = await fetch(src);
  if (!response.ok) {
    throw new Error(`failed to load ${src}`);
  }
  return response.json();
}

// Try a range-suffixed chart path first; if it 404s (the corresponding
// generate_charts.py output may not have landed yet, or the range simply has
// no data), fall back to the unsuffixed base file so the dropdown still
// produces a chart rather than an error.
async function fetchChartWithFallback(src) {
  try {
    return await fetchJson(src);
  } catch (err) {
    const baseFallback = src.replace(/_(1d|7d|30d|90d)\.json$/, ".json");
    if (baseFallback !== src) {
      const response = await fetch(baseFallback);
      if (response.ok) {
        return response.json();
      }
    }
    throw err;
  }
}

async function loadChart(container) {
  const src = chartSrc(container, selectedRange());
  if (!src || typeof echarts === "undefined") {
    return;
  }

  try {
    const option = applyTheme(await fetchChartWithFallback(src));
    const chart = charts.get(container) || echarts.init(container);
    chart.setOption(option, true);
    charts.set(container, chart);
    container.dataset.loadedSrc = src;
    container.classList.remove("chart-frame--error");
    if (!resizeBound) {
      window.addEventListener("resize", () => {
        charts.forEach((instance) => instance.resize());
      });
      resizeBound = true;
    }
  } catch (error) {
    container.classList.add("chart-frame--error");
    container.innerHTML = `<pre>${error.message}</pre>`;
  }
}

async function reloadCharts() {
  const containers = [...document.querySelectorAll("[data-chart-src], [data-chart-base]")];
  await Promise.all(containers.map((container) => loadChart(container)));
}

function escapeHtml(text) {
  if (typeof text !== "string") {
    return "";
  }
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatPercent(value) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "--";
}

function formatLatency(value) {
  return typeof value === "number" ? `${value.toFixed(1)} ms` : "--";
}

function railNav() {
  return document.querySelector(".md-sidebar--secondary .md-nav--secondary");
}

function railLinkMap() {
  return new Map(
    [...document.querySelectorAll(".md-sidebar--secondary .md-nav--secondary .md-nav__link[href^='#']")]
      .map((link) => [link.getAttribute("href"), link]),
  );
}

function ensureTechnicalRail() {
  if (!isDashboardHome()) {
    return;
  }
  document.body.classList.add("dashboard-home");
  const nav = railNav();
  if (!nav || nav.dataset.technicalRail === "true") {
    return;
  }

  const title = nav.querySelector(".md-nav__title");
  if (title) {
    title.innerHTML = [
      '<span class="technical-rail__eyebrow">In This Snapshot</span>',
      '<span class="technical-rail__snapshot" data-technical-rail-title>Snapshot pending</span>',
    ].join("");
  }

  const track = document.createElement("div");
  track.className = "technical-rail__track";
  const indicator = document.createElement("div");
  indicator.className = "technical-rail__indicator";
  nav.append(track, indicator);

  railLinkMap().forEach((link) => {
    if (link.dataset.technicalRail === "true") {
      return;
    }
    const labelText = link.textContent.trim();
    link.dataset.technicalRail = "true";
    link.textContent = "";

    const content = document.createElement("span");
    content.className = "technical-rail__content";
    const dot = document.createElement("span");
    dot.className = "technical-rail__dot";
    const label = document.createElement("span");
    label.className = "technical-rail__label";
    label.textContent = labelText;
    const badge = document.createElement("span");
    badge.className = "technical-rail__badge";
    badge.hidden = true;

    content.append(dot, label);
    link.append(content, badge);
  });

  nav.dataset.technicalRail = "true";
}

function setRailStatus(hash, status, badgeText = "") {
  const link = railLinkMap().get(hash);
  if (!link) {
    return;
  }

  const dot = link.querySelector(".technical-rail__dot");
  const badge = link.querySelector(".technical-rail__badge");
  if (dot) {
    dot.className = `technical-rail__dot technical-rail__dot--${status}`;
  }
  if (badge) {
    badge.hidden = !badgeText;
    badge.textContent = badgeText;
  }
}

function updateRailSummary(summary) {
  if (!isDashboardHome()) {
    return;
  }
  const title = document.querySelector("[data-technical-rail-title]");
  if (title) {
    title.textContent = summary.latest_date ? `Snapshot: ${summary.latest_date}` : "Snapshot unavailable";
  }

  const performanceStatus = typeof summary.overall_pass_rate === "number"
    ? (summary.overall_pass_rate >= 0.9 ? "healthy" : summary.overall_pass_rate >= 0.8 ? "warning" : "critical")
    : "unknown";
  const alertStatus = summary.recent_alerts
    ? (summary.critical_alerts ? "critical" : "warning")
    : "healthy";

  setRailStatus("#model-performance", performanceStatus);
  setRailStatus("#pass-rate", alertStatus);
  setRailStatus("#recent-alerts", alertStatus, summary.recent_alerts ? String(summary.recent_alerts) : "");
  setRailStatus("#reports", summary.latest_date ? "healthy" : "unknown");
}

function updateRailIndicator() {
  const nav = railNav();
  const indicator = nav?.querySelector(".technical-rail__indicator");
  const active = nav?.querySelector(".technical-rail__link--active");
  if (!nav || !indicator || !active) {
    return;
  }
  indicator.style.opacity = "1";
  indicator.style.transform = `translateY(${active.offsetTop}px)`;
  indicator.style.height = `${active.offsetHeight}px`;
}

function renderRailModelNodes() {
  if (!isDashboardHome()) {
    return;
  }
  const modelLink = railLinkMap().get("#model-performance");
  const modelItem = modelLink?.closest(".md-nav__item");
  if (!modelItem) {
    return;
  }

  const models = [...document.querySelectorAll("[data-model-anchor]")]
    .map((section) => {
      const heading = section.querySelector("h3");
      return heading ? { id: section.id, label: heading.textContent.trim() } : null;
    })
    .filter(Boolean);
  if (models.length === 0) {
    return;
  }

  const sublist = modelItem.querySelector(".technical-rail__sublist") || document.createElement("ul");
  sublist.className = "technical-rail__sublist";
  sublist.innerHTML = models
    .map((model) => `
      <li class="technical-rail__subitem">
        <a href="#${model.id}" class="technical-rail__sublink" data-model-link="${model.id}">${escapeHtml(model.label)}</a>
      </li>
    `)
    .join("");

  if (!sublist.parentElement) {
    modelItem.append(sublist);
  }
}

function bindRailSpy() {
  if (!isDashboardHome()) {
    return;
  }
  const links = [...railLinkMap().values()];
  const sections = links
    .map((link) => ({ link, section: document.querySelector(link.getAttribute("href")) }))
    .filter((entry) => entry.section);
  if (sections.length === 0) {
    return;
  }

  const refreshActive = () => {
    let current = sections[0];
    sections.forEach((entry) => {
      if (entry.section.getBoundingClientRect().top <= 140) {
        current = entry;
      }
    });
    sections.forEach(({ link }) => {
      link.classList.toggle("technical-rail__link--active", link === current.link);
    });

    const modelLinks = [...document.querySelectorAll(".technical-rail__sublink[data-model-link]")];
    if (current.link.getAttribute("href") === "#model-performance" && modelLinks.length) {
      const threshold = 180;
      let currentModel = modelLinks[0];
      modelLinks.forEach((link) => {
        const section = document.getElementById(link.dataset.modelLink);
        if (section && section.getBoundingClientRect().top <= threshold) {
          currentModel = link;
        }
      });
      modelLinks.forEach((link) => {
        link.classList.toggle("technical-rail__sublink--active", link === currentModel);
      });
    } else {
      modelLinks.forEach((link) => link.classList.remove("technical-rail__sublink--active"));
    }

    updateRailIndicator();
  };

  window.addEventListener("scroll", refreshActive, { passive: true });
  window.addEventListener("resize", refreshActive);
  links.forEach((link) => {
    link.addEventListener("click", () => window.setTimeout(refreshActive, 80));
  });
  refreshActive();
}

function homeModelCardHtml(card) {
  return `
    <a class="model-directory-card home-model-card" href="${escapeHtml(card.href || "#")}">
      <span class="home-model-card__heading">
        <strong>${escapeHtml(card.title || "Untitled model")}</strong>
      </span>
      <span class="home-model-card__date">Latest ${escapeHtml(card.latest_date || "--")}</span>
      <span class="home-model-card__metrics">${escapeHtml(card.metrics_label || "")}</span>
    </a>
  `;
}

function renderHomeOverview(data) {
  const root = document.querySelector("[data-home-overview-src]");
  if (!root) {
    return;
  }
  const groups = Array.isArray(data.groups) ? data.groups : [];
  const archivedGroups = Array.isArray(data.archived_groups) ? data.archived_groups : [];
  root.innerHTML = `
    ${groups.map((group) => `
      <section class="home-model-group" id="home-model-group-${escapeHtml(group.id || "models")}">
        <div class="home-model-group__header">
          <h3>${escapeHtml(group.title || "Models")}</h3>
          <p>${escapeHtml(group.description || "")}</p>
        </div>
        <div class="model-directory-grid model-directory-grid--overview">
          ${(Array.isArray(group.cards) ? group.cards : []).map(homeModelCardHtml).join("")}
        </div>
      </section>
    `).join("")}
    ${archivedGroups.map((group) => `
      <details class="home-model-group home-model-group--archived" id="home-model-group-${escapeHtml(group.id || "archived")}">
        <summary>
          <span>${escapeHtml(group.title || "Archived Models")}</span>
          <small>${escapeHtml(group.description || "")}</small>
        </summary>
        <div class="model-directory-grid model-directory-grid--overview">
          ${(Array.isArray(group.cards) ? group.cards : []).map(homeModelCardHtml).join("")}
        </div>
      </details>
    `).join("")}
  `;
}

async function loadHomeOverview() {
  const root = document.querySelector("[data-home-overview-src]");
  if (!root) {
    return;
  }
  try {
    renderHomeOverview(await fetchJson(root.dataset.homeOverviewSrc));
  } catch (error) {
    root.innerHTML = `<div class="omni-empty-state">Failed to load model overview: ${escapeHtml(error.message)}</div>`;
  }
}

function renderHealth(summary) {
  const banner = document.querySelector("[data-summary-src]");
  if (!banner) {
    return;
  }

  const alerts = summary.recent_alerts || 0;
  const warningAlerts = summary.warning_alerts || 0;
  const criticalAlerts = summary.critical_alerts || 0;
  const healthy = alerts === 0;
  const title = banner.querySelector("[data-health-title]");
  const meta = banner.querySelector("[data-health-meta]");

  banner.classList.toggle("health-banner--healthy", healthy);
  banner.classList.toggle("health-banner--alert", !healthy);
  if (title) {
    title.textContent = healthy ? "All systems normal" : `${alerts} alerts firing`;
  }
  if (meta) {
    meta.textContent = healthy
      ? `Latest snapshot ${summary.latest_date || "--"} · pass rate ${formatPercent(summary.overall_pass_rate)} · latency ${formatLatency(summary.overall_latency_p99_ms)}`
      : `${criticalAlerts} critical · ${warningAlerts} warning · latest snapshot ${summary.latest_date || "--"}`;
  }
  updateRailSummary(summary);
}

async function loadHealth() {
  const banner = document.querySelector("[data-summary-src]");
  if (!banner) {
    return;
  }

  try {
    renderHealth(await fetchJson(banner.dataset.summarySrc));
  } catch (error) {
    const title = banner.querySelector("[data-health-title]");
    const meta = banner.querySelector("[data-health-meta]");
    banner.classList.add("health-banner--alert");
    if (title) {
      title.textContent = "Health summary unavailable";
    }
    if (meta) {
      meta.textContent = error.message;
    }
  }
}

function renderHardwareStatus(data) {
  const container = document.querySelector("[data-hardware-status-src]");
  if (!container) {
    return;
  }

  const hardwareList = data.hardware || [];
  if (hardwareList.length === 0) {
    container.innerHTML = '<p class="hardware-status-empty">No hardware status available</p>';
    return;
  }

  const statusIcons = {
    healthy: "✅",
    warning: "⚠️",
    critical: "❌",
    unknown: "❓",
  };

  const html = hardwareList
    .map((hw) => {
      const icon = statusIcons[hw.status] || statusIcons.unknown;
      const passRateText = typeof hw.pass_rate === "number" ? formatPercent(hw.pass_rate) : "--";
      const latencyText = typeof hw.latency_p99_ms === "number" ? formatLatency(hw.latency_p99_ms) : "--";
      return `
        <div class="hardware-status-card hardware-status-card--${escapeHtml(hw.status)}">
          <span class="hardware-status-icon">${icon}</span>
          <span class="hardware-status-name">${escapeHtml(hw.display_name)}</span>
          <span class="hardware-status-pass">${passRateText}</span>
          <span class="hardware-status-latency">${latencyText}</span>
        </div>
      `;
    })
    .join("");

  container.innerHTML = `<div class="hardware-status-grid">${html}</div>`;
}

async function loadHardwareStatus() {
  const container = document.querySelector("[data-hardware-status-src]");
  if (!container) {
    return;
  }

  try {
    renderHardwareStatus(await fetchJson(container.dataset.hardwareStatusSrc));
  } catch (error) {
    container.innerHTML = `<p class="hardware-status-error">Failed to load hardware status: ${error.message}</p>`;
  }
}

function isNumeric(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function formatMetricValue(value, digits = 4) {
  return isNumeric(value) ? value.toFixed(digits) : "--";
}

/** Relative delta vs baseline for tooltip (e.g. latency higher = positive %). */
function formatBaselineDeltaPct(value, baseline) {
  if (!isNumeric(value) || !isNumeric(baseline) || baseline === 0) {
    return null;
  }
  const pct = ((value - baseline) / baseline) * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function formatTableValue(field, value) {
  if (field === "model_id" || field === "tokenizer_id") {
    return escapeHtml(String(value || "--"));
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (isNumeric(value)) {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (value === null || value === undefined || value === "") {
    return "--";
  }
  return escapeHtml(String(value));
}

function humanizeToken(value) {
  const mapping = {
    ttft: "TTFT",
    tpot: "TPOT",
    ttfp: "TTFP",
    itl: "ITL",
    e2e: "E2E",
    e2el: "E2EL",
    rtf: "RTF",
    qps: "Request Rate",
    // Unit suffixes: keep lowercase with parentheses ("TTFT (ms)" not "TTFT Ms").
    ms: "(ms)",
    s: "(s)",
    db: "(dB)",
    gb: "(GB)",
    mb: "(MB)",
  };
  return mapping[value.toLowerCase()] || `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
}

/** P50 / P99 / Mean label for stage_*_QwenImagePipeline_* fields (shown at end of title). */
function humanizeStageStatToken(stat) {
  const s = String(stat).toLowerCase();
  if (s === "mean") {
    return "Mean";
  }
  if (s === "p50") {
    return "P50";
  }
  if (s === "p99") {
    return "P99";
  }
  return humanizeToken(stat);
}

function humanizeField(field) {
  const fixedLabels = {
    input_len: "INPUT LEN",
    output_len: "OUTPUT LEN",
    qps: "Request Rate",
    benchmark_name: "Benchmark Params Name",
    // Distinct from "Num Prompts": many filenames use two ints (e.g. …_10_10_…) so values can match by coincidence.
    max_concurrency: "Max concurrency (config)",
    num_prompts: "Prompt count",
    max_concurrent_requests: "Peak concurrent requests",
  };
  if (fixedLabels[field]) {
    return fixedLabels[field];
  }
  const qwenStage = field.match(/^stage_(mean|p50|p99)_(.+)$/i);
  if (qwenStage) {
    const rawStage = qwenStage[2]
      .replace(/^QwenImageEditPlusPipeline_/i, "")
      .replace(/^QwenImageEditPipeline_/i, "")
      .replace(/^QwenImagePipeline_/i, "");
    const stageParts = rawStage
      .split("_")
      .filter((part) => !/pipeline$/i.test(part))
      .filter((part) => part)
      .map((part) => humanizeToken(part));
    const stageLabel = stageParts.join(" ");
    const statLabel = humanizeStageStatToken(qwenStage[1]);
    return `${stageLabel} ${statLabel}`;
  }
  const rest = field.startsWith("serve_args_") ? field.slice("serve_args_".length) : field;
  return rest
    .split("_")
    .map((part) => humanizeToken(part))
    .join(" ");
}

function disposeChartsWithin(root) {
  [...charts.entries()].forEach(([container, chart]) => {
    if (root.contains(container)) {
      if (typeof chart.__omniBaselineDispose === "function") {
        chart.__omniBaselineDispose();
        chart.__omniBaselineDispose = null;
      }
      if (typeof chart.__omniBadMarkersDispose === "function") {
        chart.__omniBadMarkersDispose();
        chart.__omniBadMarkersDispose = null;
      }
      chart.__omniSeriesKeyByIndex = null;
      chart.__omniBadSeriesIndexSet = null;
      chart.dispose();
      charts.delete(container);
    }
  });
}

function omniOptionHasMarkLineSeries(option) {
  const s = option?.series;
  return Array.isArray(s) && s.some((x) => x?.markLine);
}

function omniOptionHasBadMarkerSeries(option) {
  const s = option?.series;
  return Array.isArray(s) && s.some((x) => x?.__omniBadMarkers);
}

/** ECharts does not drive markLine emphasis from parent line series; toggle opacity by events instead. */
function omniSetMarkLineVisibility(chart, activeSeriesIndex) {
  const opt = chart.getOption();
  const list = opt.series;
  if (!Array.isArray(list) || list.length === 0) {
    return;
  }
  chart.setOption(
    {
      series: list.map((s, i) => {
        if (!s?.markLine) {
          return {};
        }
        const show = activeSeriesIndex >= 0 && i === activeSeriesIndex;
        const ml = s.markLine;
        const prevLs = ml.lineStyle && typeof ml.lineStyle === "object" && !Array.isArray(ml.lineStyle) ? ml.lineStyle : {};
        const prevLb = ml.label && typeof ml.label === "object" && !Array.isArray(ml.label) ? ml.label : {};
        return {
          markLine: {
            lineStyle: {
              ...prevLs,
              opacity: show ? 1 : 0,
            },
            label: {
              ...prevLb,
              show,
            },
          },
        };
      }),
    },
    false,
  );
}

function omniSetBadMarkerVisibility(chart, activeSeriesKey) {
  const opt = chart.getOption();
  const list = opt.series;
  if (!Array.isArray(list) || list.length === 0) {
    return;
  }
  const keyByIndex = Array.isArray(chart.__omniSeriesKeyByIndex) ? chart.__omniSeriesKeyByIndex : [];
  const badSet = chart.__omniBadSeriesIndexSet instanceof Set ? chart.__omniBadSeriesIndexSet : new Set();
  chart.setOption(
    {
      series: list.map((_, i) => {
        if (!badSet.has(i)) {
          return {};
        }
        const markerKey = String(keyByIndex[i] ?? "");
        const show = !activeSeriesKey || markerKey === String(activeSeriesKey);
        return {
          symbol: show ? OMNI_BAD_DAY_MARK_SYMBOL : "none",
          symbolSize: show ? OMNI_BAD_DAY_MARK_SIZE : 0,
          itemStyle: {
            ...OMNI_BAD_DAY_MARK_ITEM_STYLE,
            opacity: show ? 1 : 0,
          },
          silent: !show,
        };
      }),
    },
    false,
  );
}


function wireOmniBaselineHover(chart) {
  if (typeof chart.__omniBaselineDispose === "function") {
    chart.__omniBaselineDispose();
    chart.__omniBaselineDispose = null;
  }
  const showBySeriesIndex = (params) => {
    let idx = -1;
    if (typeof params?.seriesIndex === "number") {
      idx = params.seriesIndex;
    }
    if (idx >= 0) {
      omniSetMarkLineVisibility(chart, idx);
    }
  };
  const onLeaveChart = () => {
    omniSetMarkLineVisibility(chart, -1);
  };
  // In some ECharts interaction paths only one of these events fires; listen to both.
  // IMPORTANT: do not hide on `hideTip` (fires whenever cursor is not on a symbol),
  // otherwise baseline disappears while still hovering the line itself.
  chart.on("showTip", showBySeriesIndex);
  chart.on("mouseover", showBySeriesIndex);
  chart.on("globalout", onLeaveChart);
  chart.__omniBaselineDispose = () => {
    chart.off("showTip", showBySeriesIndex);
    chart.off("mouseover", showBySeriesIndex);
    chart.off("globalout", onLeaveChart);
  };
}

function wireOmniBadMarkersHover(chart) {
  if (typeof chart.__omniBadMarkersDispose === "function") {
    chart.__omniBadMarkersDispose();
    chart.__omniBadMarkersDispose = null;
  }
  const showBySeries = (params) => {
    let seriesKey = "";
    if (typeof params?.seriesIndex === "number" && Array.isArray(chart.__omniSeriesKeyByIndex)) {
      seriesKey = String(chart.__omniSeriesKeyByIndex[params.seriesIndex] || "");
    }
    if (!seriesKey && typeof params?.data?.meta?.series_key === "string") {
      seriesKey = params.data.meta.series_key;
    }
    if (!seriesKey && params?.seriesName) {
      const opt = chart.getOption();
      const list = opt?.series;
      const keys = chart.__omniSeriesKeyByIndex;
      if (Array.isArray(list) && Array.isArray(keys)) {
        const j = list.findIndex((s) => s && s.name === params.seriesName);
        if (j >= 0) {
          seriesKey = String(keys[j] || "");
        }
      }
    }
    if (seriesKey) {
      omniSetBadMarkerVisibility(chart, seriesKey);
    }
  };
  const onLeaveChart = () => {
    omniSetBadMarkerVisibility(chart, "");
  };
  chart.on("showTip", showBySeries);
  chart.on("mouseover", showBySeries);
  chart.on("globalout", onLeaveChart);
  chart.__omniBadMarkersDispose = () => {
    chart.off("showTip", showBySeries);
    chart.off("mouseover", showBySeries);
    chart.off("globalout", onLeaveChart);
  };
}

function setChart(container, option) {
  if (typeof echarts === "undefined") {
    return;
  }
  const chart = charts.get(container) || echarts.init(container);
  if (typeof chart.__omniBaselineDispose === "function") {
    chart.__omniBaselineDispose();
    chart.__omniBaselineDispose = null;
  }
  if (typeof chart.__omniBadMarkersDispose === "function") {
    chart.__omniBadMarkersDispose();
    chart.__omniBadMarkersDispose = null;
  }
  chart.__omniSeriesKeyByIndex = Array.isArray(option?.series)
    ? option.series.map((s) => String(s?.__omniSeriesKey || ""))
    : [];
  chart.__omniBadSeriesIndexSet = Array.isArray(option?.series)
    ? new Set(option.series.map((s, i) => (s?.__omniBadMarkers ? i : -1)).filter((i) => i >= 0))
    : new Set();
  chart.setOption(applyTheme(option), true);
  charts.set(container, chart);
  if (!resizeBound) {
    window.addEventListener("resize", () => {
      charts.forEach((instance) => instance.resize());
    });
    resizeBound = true;
  }
  if (omniOptionHasMarkLineSeries(option)) {
    wireOmniBaselineHover(chart);
  }
  if (omniOptionHasBadMarkerSeries(option)) {
    wireOmniBadMarkersHover(chart);
  }
}

/** Strip CI-style test_ / model-repo prefixes for shorter legend text. */
function abbreviateTestName(raw) {
  if (typeof raw !== "string" || !raw) {
    return "";
  }
  return raw
    .replace(/^test_qwen_image_/, "")
    .replace(/^test_qwen3_omni_/, "")
    .replace(/^test_qwen3_tts_/, "")
    .replace(/^test_higgs_audio_v3_/, "")
    .replace(/^test_/, "");
}

function shortRepoPath(raw) {
  if (typeof raw !== "string" || !raw) {
    return "";
  }
  const i = raw.lastIndexOf("/");
  return i >= 0 ? raw.slice(i + 1) : raw;
}

/** Shown in trend legend; grouping keys still use full `group_fields` from payload. */
const OMNI_LEGEND_SKIP_FIELDS = new Set(["backend", "model_id", "tokenizer_id", "endpoint_type"]);

function formatGroupFieldForLegend(field, record) {
  const v = record[field];
  if (v === null || v === undefined || v === "") {
    return "";
  }
  switch (field) {
    case "test_name":
      return abbreviateTestName(String(v)) || String(v);
    case "model_id":
    case "tokenizer_id":
      return shortRepoPath(String(v));
    case "max_concurrency":
      return `c${v}`;
    case "num_prompts":
      return `p${v}`;
    case "random_input_len":
      return `ri${v}`;
    case "random_output_len":
      return `ro${v}`;
    case "omni_metrics_profile":
      if (v === "audio_metrics") {
        return "audio";
      }
      if (v === "text_only_metrics") {
        return "text-only";
      }
      return String(v);
    default:
      return String(v);
  }
}

function truncateLegendLabel(text, maxLen) {
  const t = String(text || "").trim();
  if (t.length <= maxLen) {
    return t;
  }
  return `${t.slice(0, Math.max(0, maxLen - 1))}…`;
}

/**
 * Short legend: `group_fields` order, skipping backend / model / tokenizer / endpoint_type.
 */
function buildSeriesLabel(record, groupFields) {
  const gf = Array.isArray(groupFields) ? groupFields : [];
  const parts = [];
  for (const field of gf) {
    if (OMNI_LEGEND_SKIP_FIELDS.has(field)) {
      continue;
    }
    const piece = formatGroupFieldForLegend(field, record);
    if (piece) {
      parts.push(piece);
    }
  }
  let label = parts.length > 0 ? parts.join(" · ") : "";
  if (!label) {
    label = [
      record.test_name,
      record.dataset_name || "dataset:n/a",
      `ri=${record.random_input_len ?? "--"}`,
      `ro=${record.random_output_len ?? "--"}`,
      `mc=${record.max_concurrency}`,
      `np=${record.num_prompts}`,
    ].join(" · ");
  }
  return truncateLegendLabel(label, 72);
}

function normalizeFilterSelection(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (value == null || value === "") {
    return [];
  }
  return [String(value).trim()].filter(Boolean);
}

function recordFilterValue(record, field) {
  const raw = record[field];
  if (raw === null || raw === undefined) {
    return null;
  }
  return String(raw).trim();
}

function filterRecords(records, filters) {
  return records.filter((record) => Object.entries(filters).every(([field, value]) => {
    const selected = normalizeFilterSelection(value);
    if (!selected.length) {
      return true;
    }
    const recordValue = recordFilterValue(record, field);
    if (recordValue === null) {
      return false;
    }
    // Exact string match (substring match would e.g. let qwen3_omni match qwen3_omni_chunk).
    return selected.some((item) => recordValue === item);
  }));
}

function formatFilterTriggerLabel(selectedValues) {
  if (!selectedValues.length) {
    return "All";
  }
  if (selectedValues.length === 1) {
    return selectedValues[0];
  }
  return `${selectedValues.length} selected`;
}

/** Newest run first (for summary, table, and consistent “latest” semantics). */
function sortRecordsByTimeDesc(records) {
  return [...records].sort((a, b) => {
    const ta = a.sort_timestamp || "";
    const tb = b.sort_timestamp || "";
    return tb.localeCompare(ta);
  });
}

function recordCalendarDay(record) {
  const ts = record.sort_timestamp;
  if (typeof ts === "string" && ts.length >= 10) {
    return ts.slice(0, 10);
  }
  const d = record.date;
  if (typeof d === "string" && d.length >= 10) {
    return d.slice(0, 10);
  }
  return "";
}

/** Group by calendar day (YYYY-MM-DD), days newest-first; within each day, newest run first. */
function groupRecordsByCalendarDay(records) {
  const buckets = new Map();
  records.forEach((record) => {
    const day = recordCalendarDay(record) || "Unknown date";
    if (!buckets.has(day)) {
      buckets.set(day, []);
    }
    buckets.get(day).push(record);
  });
  buckets.forEach((items) => {
    items.sort((a, b) => {
      const ta = a.sort_timestamp || "";
      const tb = b.sort_timestamp || "";
      return tb.localeCompare(ta);
    });
  });
  const keys = [...buckets.keys()];
  const known = keys.filter((k) => k !== "Unknown date").sort((a, b) => b.localeCompare(a));
  const ordered = buckets.has("Unknown date") ? [...known, "Unknown date"] : known;
  return ordered.map((day) => ({ day, records: buckets.get(day) }));
}

/** YYYY-MM-DD for omnibus trend charts (hide time-of-day on axis / tooltip). */
function formatOmniHistoryChartDate(value) {
  if (value == null || value === "") {
    return "";
  }
  if (typeof value === "number" && !Number.isNaN(value)) {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) {
      return "";
    }
    const y = d.getFullYear();
    const mo = String(d.getMonth() + 1).padStart(2, "0");
    const da = String(d.getDate()).padStart(2, "0");
    return `${y}-${mo}-${da}`;
  }
  const s = String(value);
  const head = s.match(/^(\d{4}-\d{2}-\d{2})/);
  if (head) {
    return head[1];
  }
  const parsed = new Date(s);
  if (Number.isNaN(parsed.getTime())) {
    return s;
  }
  const y = parsed.getFullYear();
  const mo = String(parsed.getMonth() + 1).padStart(2, "0");
  const da = String(parsed.getDate()).padStart(2, "0");
  return `${y}-${mo}-${da}`;
}

/**
 * Time axis can place two ticks on the same calendar day (e.g. min/max padding vs day boundary);
 * hide the duplicate label when the tick instant changes but YYYY-MM-DD repeats vs the previous tick.
 */
function createOmniXAxisDateLabelFormatter() {
  let prevMs = NaN;
  let prevText = "";
  return (value) => {
    const text = formatOmniHistoryChartDate(value);
    if (!text) {
      return "";
    }
    let ms = NaN;
    if (typeof value === "number" && Number.isFinite(value)) {
      ms = value;
    } else {
      const s = String(value).trim();
      const normalized = s.includes(" ") && !s.includes("T") ? s.replace(" ", "T") : s;
      const parsed = Date.parse(normalized);
      ms = Number.isFinite(parsed) ? parsed : NaN;
    }
    if (Number.isFinite(prevMs) && Number.isFinite(ms) && ms !== prevMs && text === prevText) {
      return "";
    }
    if (Number.isFinite(ms)) {
      prevMs = ms;
    }
    prevText = text;
    return text;
  };
}

function groupRecords(records, fields) {
  const grouped = new Map();
  records.forEach((record) => {
    const key = fields.map((field) => record[field]).join("||");
    if (!grouped.has(key)) {
      grouped.set(key, []);
    }
    grouped.get(key).push(record);
  });
  return grouped;
}

/** One row per calendar day, keeping the latest run (by sort_timestamp). */
function pickLatestPerCalendarDay(rows) {
  const byDay = new Map();
  rows.forEach((item) => {
    const day = recordCalendarDay(item);
    if (!day) {
      return;
    }
    const prev = byDay.get(day);
    if (!prev || String(item.sort_timestamp || "") > String(prev.sort_timestamp || "")) {
      byDay.set(day, item);
    }
  });
  return Array.from(byDay.values());
}

/** Baseline from payload (`baseline_<metric>`), constant per config group. */
function baselineValueForMetric(items, metric) {
  const key = `baseline_${metric}`;
  const latest = [...items].sort((a, b) =>
    String(b.sort_timestamp || "").localeCompare(String(a.sort_timestamp || "")),
  )[0];
  if (latest && isNumeric(latest[key])) {
    return Number(latest[key]);
  }
  return null;
}

function formatLocalIsoDate(d) {
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const da = String(d.getDate()).padStart(2, "0");
  return `${y}-${mo}-${da}`;
}

function buildDailyIsoRange(startDay, endDay) {
  if (!startDay || !endDay) {
    return [];
  }
  const start = new Date(`${startDay}T00:00:00`);
  const end = new Date(`${endDay}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) {
    return [];
  }
  const days = [];
  const current = new Date(start);
  while (current <= end) {
    days.push(formatLocalIsoDate(current));
    current.setDate(current.getDate() + 1);
  }
  return days;
}

/** Missing day or numeric metric exactly zero — treated as abnormal (cross), line y is bridged between neighbors. */
function omniMetricDayIsBad(item, isMissingDay, rawY) {
  if (isMissingDay) {
    return true;
  }
  return isNumeric(rawY) && Number(rawY) === 0;
}

function bridgeOmniBadDayY(entries, index) {
  const e = entries[index];
  if (!e.isBad) {
    return e.numY;
  }
  let prev = null;
  for (let j = index - 1; j >= 0; j -= 1) {
    if (!entries[j].isBad) {
      prev = entries[j];
      break;
    }
  }
  let next = null;
  for (let k = index + 1; k < entries.length; k += 1) {
    if (!entries[k].isBad) {
      next = entries[k];
      break;
    }
  }
  if (!prev && !next) {
    return 0;
  }
  if (!prev) {
    return next.numY;
  }
  if (!next) {
    return prev.numY;
  }
  const denom = next.xMs - prev.xMs;
  if (!Number.isFinite(denom) || denom === 0) {
    return prev.numY;
  }
  const t = (e.xMs - prev.xMs) / denom;
  return prev.numY + t * (next.numY - prev.numY);
}

function buildOmniMetricSeries(records, metric, groupFields, options) {
  const pointPerDay = options?.pointPerDay !== false;
  const grouped = groupRecords(records, groupFields);
  const series = [];
  grouped.forEach((items) => {
    let rows = items.filter((item) => isNumeric(item[metric]));
    if (pointPerDay) {
      rows = pickLatestPerCalendarDay(rows);
    }
    const baseVal = baselineValueForMetric(items, metric);
    const sortedRows = rows
      .sort((left, right) => left.sort_timestamp.localeCompare(right.sort_timestamp));
    const dayMap = new Map(sortedRows.map((item) => [recordCalendarDay(item), item]));
    const dailyRange = pointPerDay && sortedRows.length > 1
      ? buildDailyIsoRange(recordCalendarDay(sortedRows[0]), recordCalendarDay(sortedRows[sortedRows.length - 1]))
      : [];
    const badScatterData = [];
    const daySequence = dailyRange.length ? dailyRange : sortedRows.map((row) => recordCalendarDay(row));
    const entries = daySequence.map((day) => {
      const item = dayMap.get(day);
      const isMissingDay = !item;
      const xVal = pointPerDay && day ? `${day}T00:00:00` : item?.date;
      let xMs = parseSeriesPointTime(xVal);
      if (xMs == null && typeof day === "string" && /^\d{4}-\d{2}-\d{2}$/.test(day)) {
        xMs = Date.parse(`${day}T12:00:00`);
      }
      if (xMs == null && item?.sort_timestamp) {
        xMs = parseIsoDate(item.sort_timestamp);
      }
      const rawY = isMissingDay ? null : item[metric];
      const isNumericY = isNumeric(rawY);
      const numY = isNumericY ? Number(rawY) : null;
      const isBad = omniMetricDayIsBad(item, isMissingDay, rawY);
      return {
        day,
        xVal,
        xMs: xMs != null && Number.isFinite(xMs) ? xMs : 0,
        item,
        isMissingDay,
        rawY,
        numY,
        isBad,
      };
    });
    entries.sort((a, b) => a.xMs - b.xMs);
    const bridgedYs = entries.map((_, i) => bridgeOmniBadDayY(entries, i));
    const points = entries.map((e, i) => {
      const { item, isMissingDay, xVal, isBad } = e;
      const lineY = bridgedYs[i];
      const meta = {
        test_name: item?.test_name,
        dataset_name: item?.dataset_name,
        benchmark_name: item?.benchmark_name,
        max_concurrency: item?.max_concurrency,
        num_prompts: item?.num_prompts,
        random_input_len: item?.random_input_len,
        random_output_len: item?.random_output_len,
        metric,
        source_file: item?.source_file,
        baseline: baseVal,
        missing_day: isMissingDay,
        is_bad_day: isBad,
        bridged_line_y: isBad ? lineY : null,
        actual_metric_y: isMissingDay ? null : e.numY,
        series_key: "",
      };
      if (isBad && Number.isFinite(lineY)) {
        badScatterData.push({ value: [xVal, lineY], meta });
      }
      return {
        value: [xVal, lineY],
        ...(isBad
          ? {
              symbol: "none",
              symbolSize: 0,
            }
          : {}),
        meta,
      };
    });
    if (points.length > 0) {
      const label = buildSeriesLabel(items[0], groupFields);
      const seriesKey = `${metric}::${String(items[0]?.config_key || label || "")}`;
      points.forEach((p) => {
        if (p?.meta) {
          p.meta.series_key = seriesKey;
        }
      });
      badScatterData.forEach((p) => {
        if (p?.meta) {
          p.meta.series_key = seriesKey;
        }
      });
      const n = points.length;
      const lineSeries = {
        name: label,
        __omniSeriesKey: seriesKey,
        type: "line",
        triggerLineEvent: true,
        showSymbol: true,
        symbolSize: n <= 12 ? 6 : n <= 30 ? 4 : 3,
        smooth: false,
        data: points,
      };
      if (baseVal !== null) {
        lineSeries.markLine = {
          silent: true,
          symbol: ["none", "none"],
          lineStyle: {
            type: "dashed",
            width: 2,
            opacity: 0,
          },
          label: {
            show: false,
            position: "start",
            formatter: () => `baseline ${formatMetricValue(baseVal)}`,
          },
          data: [{ yAxis: baseVal }],
        };
      }
      series.push(lineSeries);
      if (badScatterData.length > 0) {
        series.push({
          __omniBadMarkers: true,
          __omniSeriesKey: seriesKey,
          name: lineSeries.name,
          type: "scatter",
          symbol: OMNI_BAD_DAY_MARK_SYMBOL,
          symbolSize: OMNI_BAD_DAY_MARK_SIZE,
          itemStyle: { ...OMNI_BAD_DAY_MARK_ITEM_STYLE },
          data: badScatterData,
          z: 10,
          emphasis: {
            disabled: true,
          },
          select: {
            disabled: true,
          },
        });
      }
    }
  });
  return series;
}

/** Single-point tooltip keeps hovered data semantics clear. */
function formatOmniHistoryTooltipHtml(params) {
  if (!params || !params.data) {
    return "";
  }
  const meta = params.data?.meta || {};
  const val = params.data?.value?.[1];
  const bl = meta.baseline;
  const lines = [
    `<strong>${escapeHtml(params.seriesName || "")}</strong>`,
    `Date: ${escapeHtml(formatOmniHistoryChartDate(params.data?.value?.[0]))}`,
  ];
  if (meta.is_bad_day) {
    lines.push(`Line (bridged): ${formatMetricValue(val)}`);
    lines.push(
      meta.missing_day
        ? "No data this day; segment linearly connects the previous and next normal days."
        : `Abnormal value (${formatMetricValue(meta.actual_metric_y)}); segment connects neighbors.`,
    );
  } else {
    lines.push(`Value: ${formatMetricValue(val)}`);
  }
  if (isNumeric(bl)) {
    lines.push(`baseline: ${formatMetricValue(bl)}`);
    const d = formatBaselineDeltaPct(val, bl);
    if (d) {
      lines.push(`vs baseline: ${escapeHtml(d)}`);
    }
  }
  lines.push(
    `Test: ${escapeHtml(meta.test_name || "--")}`,
    `Dataset: ${escapeHtml(meta.dataset_name || "--")}`,
    `Max concurrency: ${escapeHtml(String(meta.max_concurrency ?? "--"))}`,
    `Num prompts: ${escapeHtml(String(meta.num_prompts ?? "--"))}`,
  );
  if (!meta.benchmark_name) {
    lines.push(
      `Random input len: ${escapeHtml(String(meta.random_input_len ?? "--"))}`,
      `Random output len: ${escapeHtml(String(meta.random_output_len ?? "--"))}`,
    );
  }
  return lines.join("<br>");
}

function parseSeriesPointTime(xVal) {
  if (xVal == null || xVal === "") {
    return null;
  }
  if (typeof xVal === "number" && Number.isFinite(xVal)) {
    return xVal;
  }
  const s = String(xVal).trim();
  const normalized = s.includes(" ") && !s.includes("T") ? s.replace(" ", "T") : s;
  const ts = Date.parse(normalized);
  return Number.isFinite(ts) ? ts : null;
}

function timeExtentFromOmniSeries(seriesList) {
  let minT = Infinity;
  let maxT = -Infinity;
  seriesList.forEach((s) => {
    if (s.__omniBadMarkers) {
      return;
    }
    (s.data || []).forEach((p) => {
      const t = parseSeriesPointTime(p?.value?.[0]);
      if (t !== null) {
        minT = Math.min(minT, t);
        maxT = Math.max(maxT, t);
      }
    });
  });
  if (!Number.isFinite(minT) || !Number.isFinite(maxT)) {
    return null;
  }
  return { minT, maxT };
}

/** First point meta of a line series (carries scenario fields like max_concurrency). */
function omniSeriesScenarioMeta(series) {
  const point = (series.data || []).find((p) => p?.meta);
  return point?.meta || {};
}

function compareNullableNumber(a, b, direction = "asc") {
  const aMissing = a === null;
  const bMissing = b === null;
  if (aMissing || bMissing) {
    if (aMissing && bMissing) {
      return 0;
    }
    return aMissing ? 1 : -1;
  }
  if (a === b) {
    return 0;
  }
  return direction === "desc" ? b - a : a - b;
}

/**
 * Pick at most `cap` default-visible series, spread across the three scenarios that
 * matter for capacity planning: long sequence (large input len), high throughput
 * (high concurrency) and low latency (low concurrency). Remaining slots are filled
 * in original order; everything else stays hidden until "Show all" is clicked.
 */
function selectDefaultVisibleSeriesKeys(lineSeries, cap) {
  const entries = lineSeries.map((s, index) => {
    const meta = omniSeriesScenarioMeta(s);
    const conc = Number(meta.max_concurrency);
    const inputLen = Number(meta.random_input_len);
    return {
      key: s.__omniSeriesKey,
      index,
      conc: Number.isFinite(conc) ? conc : null,
      inputLen: Number.isFinite(inputLen) ? inputLen : null,
    };
  });
  const isLongSequence = (entry) => entry.inputLen !== null && entry.inputLen >= 1000;
  const longSeq = entries.filter(isLongSequence)
    .sort((a, b) => (
      compareNullableNumber(a.inputLen, b.inputLen, "desc")
      || compareNullableNumber(a.conc, b.conc, "desc")
      || a.index - b.index
    ));
  const shortSeq = entries.filter((entry) => !isLongSequence(entry));
  const highThroughput = [...shortSeq].sort((a, b) => (
    compareNullableNumber(a.conc, b.conc, "desc") || a.index - b.index
  ));
  const lowLatency = [...shortSeq].sort((a, b) => (
    compareNullableNumber(a.conc, b.conc, "asc") || a.index - b.index
  ));

  const selected = new Set();
  const perScenario = Math.max(1, Math.floor(cap / 3));
  [longSeq, highThroughput, lowLatency].forEach((bucket) => {
    let taken = 0;
    bucket.forEach((entry) => {
      if (taken < perScenario && selected.size < cap && !selected.has(entry.key)) {
        selected.add(entry.key);
        taken += 1;
      }
    });
  });
  entries.forEach((entry) => {
    if (selected.size < cap) {
      selected.add(entry.key);
    }
  });
  return selected;
}

function buildOmniChartOption(metricGroup, records, groupFields, chartPointPerDay, visibleKeys) {
  const opts = { pointPerDay: chartPointPerDay !== false };
  const rawSeries = applyOmniLineSeriesColors(
    metricGroup.metrics.flatMap((metric) => buildOmniMetricSeries(records, metric, groupFields, opts)),
  );
  const series = visibleKeys ? rawSeries.filter((s) => visibleKeys.has(s.__omniSeriesKey)) : rawSeries;
  const maxPoints = series.reduce((maxCount, s) => {
    if (s.__omniBadMarkers) {
      return maxCount;
    }
    return Math.max(maxCount, s.data?.length || 0);
  }, 0);
  const hasOmniBaseline = series.some((s) => s.markLine);
  const extent = timeExtentFromOmniSeries(series);
  let xAxisMin;
  let xAxisMax;
  if (extent) {
    const span = Math.max(extent.maxT - extent.minT, 24 * 60 * 60 * 1000);
    const padL = Math.min(span * 0.04, 36 * 60 * 60 * 1000);
    // Extra room on the max-time side so the last day label (e.g. 2026-04-19) is not clipped at the plot edge.
    const padR = padL + 10 * 60 * 60 * 1000;
    xAxisMin = extent.minT - padL;
    xAxisMax = extent.maxT + padR;
  }
  const yValues = [];
  const baselineValues = [];
  series.forEach((s) => {
    if (s.__omniBadMarkers) {
      return;
    }
    (s.data || []).forEach((p) => {
      const y = p?.value?.[1];
      if (isNumeric(y)) {
        yValues.push(Number(y));
      }
    });
    const bl = s?.markLine?.data?.[0]?.yAxis;
    if (isNumeric(bl)) {
      baselineValues.push(Number(bl));
    }
  });
  const allY = [...yValues, ...baselineValues];
  let yMin;
  let yMax;
  if (allY.length > 0) {
    const minV = Math.min(...allY);
    const maxV = Math.max(...allY);
    const span = maxV - minV;
    const pad = span > 0 ? span * 0.08 : Math.max(1, Math.abs(maxV) * 0.08);
    yMin = 0;
    yMax = maxV + pad;
    if (!Number.isFinite(yMax) || yMax <= 0) {
      yMax = 1;
    }
  }
  return {
    color: OMNI_LINE_SERIES_PALETTE,
    animationDurationUpdate: 200,
    tooltip: {
      trigger: "item",
      formatter: formatOmniHistoryTooltipHtml,
    },
    legend: { show: false },
    grid: {
      left: hasOmniBaseline ? 120 : 56,
      right: 48,
      top: 24,
      bottom: 56,
      containLabel: true,
    },
    xAxis: {
      type: "time",
      ...(extent ? { min: xAxisMin, max: xAxisMax } : {}),
      minInterval: 24 * 60 * 60 * 1000,
      axisLabel: {
        show: maxPoints > 0,
        rotate: 38,
        align: "right",
        margin: 14,
        hideOverlap: false,
        showMinLabel: true,
        showMaxLabel: true,
        formatter: createOmniXAxisDateLabelFormatter(),
      },
    },
    yAxis: {
      type: "value",
      min: yMin,
      max: yMax,
      axisLabel: {
        formatter(value) {
          return Number(value).toFixed(2);
        },
      },
    },
    series,
  };
}

let _historyInstanceSeq = 0;
let _omniFilterOutsideClickBound = false;

function ensureHistoryInstanceId(root) {
  if (!root.dataset.historyInstance) {
    root.dataset.historyInstance = String(_historyInstanceSeq++);
  }
  return root.dataset.historyInstance;
}

function resetOmniFilterDropdownStyle(dropdown) {
  if (!dropdown) {
    return;
  }
  dropdown.classList.remove("is-fixed");
  dropdown.style.position = "";
  dropdown.style.left = "";
  dropdown.style.top = "";
  dropdown.style.width = "";
  dropdown.style.right = "";
  dropdown.style.zIndex = "";
}

function positionOmniFilterDropdown(multiselect) {
  const button = multiselect.querySelector(".omni-filter__trigger");
  const dropdown = multiselect.querySelector(".omni-filter__dropdown");
  if (!button || !dropdown) {
    return;
  }
  const rect = button.getBoundingClientRect();
  dropdown.classList.add("is-fixed");
  dropdown.style.position = "fixed";
  dropdown.style.left = `${Math.max(8, rect.left)}px`;
  dropdown.style.top = `${rect.bottom + 4}px`;
  dropdown.style.width = `${rect.width}px`;
  dropdown.style.right = "auto";
  dropdown.style.zIndex = "40";
}

function syncOpenOmniFilterDropdownPositions() {
  const open = document.querySelectorAll(".omni-filter__multiselect.is-open");
  if (!open.length) {
    return;
  }
  open.forEach((multiselect) => {
    positionOmniFilterDropdown(multiselect);
  });
}

function bindOmniFilterOutsideClick() {
  if (_omniFilterOutsideClickBound) {
    return;
  }
  _omniFilterOutsideClickBound = true;
  document.addEventListener("click", () => {
    document.querySelectorAll(".omni-filter__multiselect.is-open").forEach((multiselect) => {
      multiselect.classList.remove("is-open");
      multiselect.querySelector(".omni-filter__trigger")?.setAttribute("aria-expanded", "false");
      resetOmniFilterDropdownStyle(multiselect.querySelector(".omni-filter__dropdown"));
    });
  });
  window.addEventListener("resize", () => syncOpenOmniFilterDropdownPositions(), { passive: true });
  document.addEventListener(
    "scroll",
    () => syncOpenOmniFilterDropdownPositions(),
    { passive: true, capture: true },
  );
}

function closeOmniFilterDropdowns(container) {
  container.querySelectorAll(".omni-filter__multiselect.is-open").forEach((multiselect) => {
    multiselect.classList.remove("is-open");
    multiselect.querySelector(".omni-filter__trigger")?.setAttribute("aria-expanded", "false");
    resetOmniFilterDropdownStyle(multiselect.querySelector(".omni-filter__dropdown"));
  });
}

function getOpenOmniFilterField(root) {
  const open = root.querySelector(".omni-filter__multiselect.is-open");
  if (!open) {
    return null;
  }
  return open.closest("[data-omni-filter-wrap]")?.dataset.omniFilterWrap ?? null;
}

function renderOmniFilterBar(payload, filters, root, options = {}) {
  const container = root.querySelector("[data-omni-history-filters]");
  if (!container) {
    return;
  }
  bindOmniFilterOutsideClick();
  const openField = options.openField ?? null;
  const hid = ensureHistoryInstanceId(root);
  const dateRange = currentOmniDateRange(root);
  container.innerHTML = payload.filters.map((field) => {
    const selected = new Set(normalizeFilterSelection(filters[field]));
    const options = (payload.filter_options?.[field] || [])
      .map((option) => {
        const value = String(option);
        const checked = selected.has(value) ? " checked" : "";
        return `
          <label class="omni-filter__option">
            <input
              type="checkbox"
              class="omni-filter__checkbox"
              data-omni-filter-option="${field}"
              value="${escapeHtml(value)}"
              ${checked}
            >
            <span class="omni-filter__option-label">${escapeHtml(value)}</span>
          </label>
        `;
      })
      .join("");
    const triggerLabel = formatFilterTriggerLabel([...selected]);
    const dropdownId = `omni-filter-${field}-${hid}`;
    return `
      <div class="omni-filter" data-omni-filter-wrap="${field}">
        <span class="omni-filter__label" id="${dropdownId}-label">${escapeHtml(humanizeField(field))}</span>
        <div class="omni-filter__multiselect">
          <button
            type="button"
            class="omni-filter__trigger"
            aria-expanded="false"
            aria-haspopup="listbox"
            aria-labelledby="${dropdownId}-label"
            data-omni-filter-trigger="${field}"
          >
            <span class="omni-filter__trigger-text">${escapeHtml(triggerLabel)}</span>
          </button>
          <div
            class="omni-filter__dropdown"
            id="${dropdownId}"
            role="listbox"
            aria-multiselectable="true"
          >${options || `<p class="omni-filter__empty">No options</p>`}</div>
        </div>
      </div>
    `;
  }).join("") + `
    <label class="omni-filter">
      <span class="omni-filter__label">From Date</span>
      <input class="omni-filter__input" type="date" data-omni-date-range="from" value="${escapeHtml(dateRange.from)}">
    </label>
    <label class="omni-filter">
      <span class="omni-filter__label">To Date</span>
      <input class="omni-filter__input" type="date" data-omni-date-range="to" value="${escapeHtml(dateRange.to)}">
    </label>
    <button type="button" class="omni-filter__reset" data-omni-filter-reset>Reset filters</button>
  `;

  container.querySelectorAll("[data-omni-filter-trigger]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const multiselect = button.closest(".omni-filter__multiselect");
      const wasOpen = multiselect.classList.contains("is-open");
      closeOmniFilterDropdowns(container);
      if (!wasOpen) {
        multiselect.classList.add("is-open");
        button.setAttribute("aria-expanded", "true");
        positionOmniFilterDropdown(multiselect);
      }
    });
  });
  container.querySelectorAll(".omni-filter__dropdown").forEach((dropdown) => {
    dropdown.addEventListener("click", (event) => {
      event.stopPropagation();
    });
  });
  container.querySelectorAll("[data-omni-filter-option]").forEach((input) => {
    input.addEventListener("change", () => {
      renderQwen3OmniHistory(payload, root, {
        preserveOpenFilter: input.dataset.omniFilterOption,
      });
    });
  });
  container.querySelectorAll("[data-omni-date-range]").forEach((input) => {
    input.addEventListener("change", () => {
      renderQwen3OmniHistory(payload, root);
    });
  });
  container.querySelector("[data-omni-filter-reset]")?.addEventListener("click", () => {
    container.querySelectorAll("[data-omni-filter-option]").forEach((input) => {
      input.checked = false;
    });
    container.querySelectorAll("[data-omni-date-range]").forEach((input) => {
      input.value = "";
    });
    renderQwen3OmniHistory(payload, root);
  });

  if (openField) {
    const wrap = container.querySelector(`[data-omni-filter-wrap="${openField}"]`);
    const multiselect = wrap?.querySelector(".omni-filter__multiselect");
    const trigger = multiselect?.querySelector(".omni-filter__trigger");
    if (multiselect && trigger) {
      multiselect.classList.add("is-open");
      trigger.setAttribute("aria-expanded", "true");
      positionOmniFilterDropdown(multiselect);
    }
  }
}

function currentOmniFilters(payload, root) {
  return payload.filters.reduce((acc, field) => {
    const wrap = root.querySelector(`[data-omni-filter-wrap="${field}"]`);
    if (!wrap) {
      acc[field] = [];
      return acc;
    }
    acc[field] = [...wrap.querySelectorAll(`[data-omni-filter-option="${field}"]:checked`)]
      .map((input) => input.value.trim())
      .filter(Boolean);
    return acc;
  }, {});
}

function currentOmniDateRange(root) {
  const read = (kind) => root.querySelector(`[data-omni-date-range="${kind}"]`)?.value?.trim() || "";
  return { from: read("from"), to: read("to") };
}

/** Keep records whose calendar day falls inside the inclusive [from, to] range. */
function filterRecordsByDateRange(records, dateRange) {
  const { from, to } = dateRange || {};
  if (!from && !to) {
    return records;
  }
  return records.filter((record) => {
    const day = recordCalendarDay(record);
    if (!day) {
      return false;
    }
    if (from && day < from) {
      return false;
    }
    if (to && day > to) {
      return false;
    }
    return true;
  });
}

function renderOmniSummary(records, groupFields, root) {
  const container = root.querySelector("[data-omni-history-summary]");
  if (!container) {
    return;
  }
  const latest = records[0];
  const configs = groupRecords(records, groupFields).size;
  container.innerHTML = `
    <div class="omni-summary-card">
      <span class="omni-summary-card__eyebrow">Visible Records</span>
      <strong class="omni-summary-card__value">${records.length}</strong>
    </div>
    <div class="omni-summary-card">
      <span class="omni-summary-card__eyebrow">Visible Configs</span>
      <strong class="omni-summary-card__value">${configs}</strong>
    </div>
    <div class="omni-summary-card">
      <span class="omni-summary-card__eyebrow">Latest Result</span>
      <strong class="omni-summary-card__value">${escapeHtml(latest?.date || "--")}</strong>
    </div>
  `;
}

function renderOmniTable(payload, records, root) {
  const container = root.querySelector("[data-omni-history-table]");
  if (!container) {
    return;
  }
  if (records.length === 0) {
    container.innerHTML = '<div class="omni-empty-state">当前筛选条件下没有数据。</div>';
    return;
  }

  const header = payload.table_columns
    .map((field) => `<th scope="col">${escapeHtml(humanizeField(field))}</th>`)
    .join("");

  const buildTbody = (dayRecords) => dayRecords.map((record) => {
    const cells = payload.table_columns.map((field) => {
      const numericClass = isNumeric(record[field]) ? " omni-history-table__cell--numeric" : "";
      return `<td class="omni-history-table__cell${numericClass}">${formatTableValue(field, record[field])}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");

  const dayGroups = groupRecordsByCalendarDay(records);
  const blocks = dayGroups.map(({ day, records: dayRecords }, index) => `
    <details class="omni-history-day"${index === 0 ? " open" : ""}>
      <summary class="omni-history-day__summary">
        <span class="omni-history-day__label">${escapeHtml(day)}</span>
        <span class="omni-history-day__meta">${dayRecords.length} run${dayRecords.length === 1 ? "" : "s"}</span>
      </summary>
      <div class="omni-history-table__wrap">
        <table class="omni-history-table">
          <thead><tr>${header}</tr></thead>
          <tbody>${buildTbody(dayRecords)}</tbody>
        </table>
      </div>
    </details>
  `).join("");

  container.innerHTML = `<div class="omni-history-by-date">${blocks}</div>`;
}

function omniMetricAnchorId(metricGroup) {
  return `omni-metric-${String(metricGroup.id || metricGroup.title || "metric")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-|-$/g, "")}`;
}

function ensureOmniMetricJumpNav(root, primaryGroups, extraGroups) {
  const container = root.querySelector("[data-omni-metric-jump-nav]");
  if (!container) {
    return;
  }
  if (primaryGroups.length === 0 && extraGroups.length === 0) {
    container.hidden = true;
    return;
  }
  container.hidden = false;
  const primaryLinks = primaryGroups.map((group) => (
    `<a href="#${escapeHtml(omniMetricAnchorId(group))}">${escapeHtml(group.title || humanizeField(group.id || ""))}</a>`
  ));
  const moreLink = extraGroups.length > 0
    ? ['<a href="#omni-more-charts">More charts <span class="omni-metric-jump-nav__muted">More</span></a>']
    : [];
  container.innerHTML = [...primaryLinks, ...moreLink].join("");
}

/** Series values pivoted to a day-by-series table (InferenceX-style "Table" view). */
function buildOmniSeriesTableHtml(lineSeries, visibleKeySet) {
  const visible = lineSeries.filter((s) => visibleKeySet.has(s.__omniSeriesKey));
  if (visible.length === 0) {
    return '<div class="omni-empty-state">没有可见的数据系列。</div>';
  }
  const days = [...new Set(
    visible.flatMap((s) => (s.data || [])
      .filter((p) => p?.meta && !p.meta.missing_day && isNumeric(p.meta.actual_metric_y))
      .map((p) => String(p.value?.[0] || "").slice(0, 10))),
  )].filter(Boolean).sort();
  const header = ['<th scope="col">Series</th>', ...days.map((day) => `<th scope="col">${escapeHtml(day)}</th>`)].join("");
  const rows = visible.map((s) => {
    const byDay = new Map((s.data || [])
      .filter((p) => p?.meta && !p.meta.missing_day)
      .map((p) => [String(p.value?.[0] || "").slice(0, 10), p.meta.actual_metric_y]));
    const cells = days.map((day) => {
      const value = byDay.get(day);
      return `<td class="omni-history-table__cell omni-history-table__cell--numeric">${isNumeric(value) ? formatMetricValue(value) : "--"}</td>`;
    }).join("");
    return `
      <tr>
        <td class="omni-history-table__cell omni-series-table__name">
          <span class="omni-series-dot" style="background:${escapeHtml(s.color || "#888")}"></span>${escapeHtml(s.name)}
        </td>
        ${cells}
      </tr>
    `;
  }).join("");
  return `
    <div class="omni-history-table__wrap">
      <table class="omni-history-table">
        <thead><tr>${header}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderOmniChartSection(section, metricGroup, records, groupFields, chartPointPerDay, seriesCap) {
  const opts = { pointPerDay: chartPointPerDay !== false };
  const chartRoot = document.createElement("section");
  chartRoot.className = "omni-chart-card";
  chartRoot.id = omniMetricAnchorId(metricGroup);
  // Colors assigned on the full list so they stay stable across visibility changes.
  const allSeries = applyOmniLineSeriesColors(
    metricGroup.metrics.flatMap((metric) => buildOmniMetricSeries(records, metric, groupFields, opts)),
  );
  const lineSeries = allSeries.filter((s) => !s.__omniBadMarkers);
  const capped = Number.isFinite(seriesCap) && seriesCap > 0 && lineSeries.length > seriesCap;

  chartRoot.innerHTML = `
    <div class="omni-chart-card__header">
      <div>
        <h3>${escapeHtml(metricGroup.title)}</h3>
        <p>${metricGroup.metrics.map(humanizeField).join(" · ")}</p>
      </div>
      <span class="omni-chart-card__badge" data-omni-series-badge></span>
      <div class="omni-view-toggle" data-omni-view-toggle>
        <button type="button" class="omni-view-toggle__btn omni-view-toggle__btn--active" data-omni-view="chart">Chart</button>
        <button type="button" class="omni-view-toggle__btn" data-omni-view="table">Table</button>
      </div>
    </div>
  `;

  if (lineSeries.length === 0) {
    chartRoot.querySelector("[data-omni-view-toggle]")?.remove();
    chartRoot.querySelector("[data-omni-series-badge]")?.remove();
    const empty = document.createElement("div");
    empty.className = "omni-empty-state";
    empty.textContent = "当前筛选条件下没有数据。";
    chartRoot.append(empty);
    section.append(chartRoot);
    return;
  }

  const chart = document.createElement("div");
  chart.className = "chart-frame omni-chart-frame";
  const tableWrap = document.createElement("div");
  tableWrap.className = "omni-series-table";
  tableWrap.hidden = true;
  chartRoot.append(chart, tableWrap);
  section.append(chartRoot);

  // Visibility state: capped charts start with representative scenarios only.
  const allKeys = lineSeries.map((s) => s.__omniSeriesKey);
  const defaultVisible = capped ? selectDefaultVisibleSeriesKeys(lineSeries, seriesCap) : new Set(allKeys);
  const hiddenKeys = new Set(allKeys.filter((key) => !defaultVisible.has(key)));
  let view = "chart";

  const badge = chartRoot.querySelector("[data-omni-series-badge]");
  const legend = document.createElement("details");
  legend.className = "omni-series-legend";
  legend.innerHTML = `
    <summary data-omni-legend-summary></summary>
    <div class="omni-series-legend__tools">
      <input type="search" class="omni-series-legend__search" placeholder="Search series..." data-omni-legend-search>
      <button type="button" class="omni-series-legend__btn" data-omni-legend-all>All</button>
      <button type="button" class="omni-series-legend__btn" data-omni-legend-none>None</button>
      ${capped ? '<button type="button" class="omni-series-legend__btn" data-omni-legend-default>Key scenarios</button>' : ""}
    </div>
    <ul class="omni-series-legend__list">
      ${lineSeries.map((s) => `
        <li class="omni-series-legend__item" data-omni-legend-key="${escapeHtml(s.__omniSeriesKey)}">
          <span class="omni-series-dot" style="background:${escapeHtml(s.color || "#888")}"></span>
          <span class="omni-series-legend__name">${escapeHtml(s.name)}</span>
        </li>
      `).join("")}
    </ul>
  `;
  chartRoot.append(legend);

  const visibleKeySet = () => new Set(allKeys.filter((key) => !hiddenKeys.has(key)));
  const applyView = () => {
    const visibleCount = allKeys.length - hiddenKeys.size;
    badge.textContent = hiddenKeys.size === 0
      ? `${allKeys.length} series`
      : `${visibleCount} of ${allKeys.length} series`;
    legend.querySelector("[data-omni-legend-summary]").textContent =
      `Legend (${visibleCount}/${allKeys.length} visible)`;
    legend.querySelectorAll("[data-omni-legend-key]").forEach((item) => {
      item.classList.toggle("omni-series-legend__item--hidden", hiddenKeys.has(item.dataset.omniLegendKey));
    });
    if (view === "chart") {
      chart.hidden = false;
      tableWrap.hidden = true;
      setChart(chart, buildOmniChartOption(
        metricGroup, records, groupFields, chartPointPerDay,
        hiddenKeys.size === 0 ? null : visibleKeySet(),
      ));
      charts.get(chart)?.resize();
    } else {
      chart.hidden = true;
      tableWrap.hidden = false;
      tableWrap.innerHTML = buildOmniSeriesTableHtml(lineSeries, visibleKeySet());
    }
    chartRoot.querySelectorAll("[data-omni-view]").forEach((btn) => {
      btn.classList.toggle("omni-view-toggle__btn--active", btn.dataset.omniView === view);
    });
  };

  chartRoot.querySelector("[data-omni-view-toggle]").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-omni-view]");
    if (btn && btn.dataset.omniView !== view) {
      view = btn.dataset.omniView;
      applyView();
    }
  });
  legend.querySelector("[data-omni-legend-search]").addEventListener("input", (event) => {
    const query = event.target.value.trim().toLowerCase();
    legend.querySelectorAll("[data-omni-legend-key]").forEach((item) => {
      const name = item.querySelector(".omni-series-legend__name")?.textContent?.toLowerCase() || "";
      item.hidden = Boolean(query) && !name.includes(query);
    });
  });
  legend.querySelector("[data-omni-legend-all]").addEventListener("click", () => {
    hiddenKeys.clear();
    applyView();
  });
  legend.querySelector("[data-omni-legend-none]").addEventListener("click", () => {
    allKeys.forEach((key) => hiddenKeys.add(key));
    applyView();
  });
  legend.querySelector("[data-omni-legend-default]")?.addEventListener("click", () => {
    hiddenKeys.clear();
    allKeys.forEach((key) => {
      if (!defaultVisible.has(key)) {
        hiddenKeys.add(key);
      }
    });
    applyView();
  });
  legend.querySelector(".omni-series-legend__list").addEventListener("click", (event) => {
    const item = event.target.closest("[data-omni-legend-key]");
    if (!item) {
      return;
    }
    const key = item.dataset.omniLegendKey;
    if (hiddenKeys.has(key)) {
      hiddenKeys.delete(key);
    } else {
      hiddenKeys.add(key);
    }
    applyView();
  });

  applyView();
}

function parseIsoDate(value) {
  if (value == null || value === "") {
    return null;
  }
  const s = String(value).trim();
  const normalized = s.includes(" ") && !s.includes("T") ? s.replace(" ", "T") : s;
  const ts = Date.parse(normalized);
  return Number.isFinite(ts) ? ts : null;
}

function filterRecordsByRecentDays(records, days) {
  if (!Number.isFinite(days) || days <= 0 || records.length === 0) {
    return records;
  }
  const latestTs = records.reduce((maxTs, item) => {
    const ts = parseIsoDate(item.sort_timestamp || item.date);
    return ts !== null && ts > maxTs ? ts : maxTs;
  }, -Infinity);
  if (!Number.isFinite(latestTs)) {
    return records;
  }
  const cutoff = latestTs - (days - 1) * 24 * 60 * 60 * 1000;
  return records.filter((item) => {
    const ts = parseIsoDate(item.sort_timestamp || item.date);
    return ts !== null && ts >= cutoff;
  });
}

function ensureOmniTrendRangeControl(root, onChange, disabled = false) {
  const container = root.querySelector("[data-omni-history-charts]");
  if (!container) {
    return 7;
  }
  const current = Number(root.dataset.omniTrendDays || "7");
  const activeDays = current === 30 ? 30 : 7;
  root.dataset.omniTrendDays = String(activeDays);

  let control = root.querySelector(".omni-chart-range");
  if (!control) {
    control = document.createElement("div");
    control.className = "omni-chart-range";
    control.innerHTML = `
      <span class="omni-chart-range__label">Trend Window</span>
      <button type="button" class="omni-chart-range__btn" data-omni-trend-days="7">7 days</button>
      <button type="button" class="omni-chart-range__btn" data-omni-trend-days="30">30 days</button>
    `;
    container.before(control);
    control.querySelectorAll("[data-omni-trend-days]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const days = Number(btn.dataset.omniTrendDays || "7");
        if (days !== 7 && days !== 30) {
          return;
        }
        if (Number(root.dataset.omniTrendDays || "7") === days) {
          return;
        }
        root.dataset.omniTrendDays = String(days);
        onChange();
      });
    });
  }

  control.querySelectorAll("[data-omni-trend-days]").forEach((btn) => {
    const days = Number(btn.dataset.omniTrendDays || "7");
    btn.classList.toggle("omni-chart-range__btn--active", !disabled && days === activeDays);
    btn.disabled = disabled;
    btn.title = disabled ? "Disabled while a From/To date filter is active" : "";
  });
  return activeDays;
}

/** Split metric groups into always-visible and collapsed ("More charts") sets.
 * Groups flagged `collapsed: true` in config drive the split; without flags,
 * fall back to the historical first-N behavior. */
function splitOmniMetricGroups(metricGroups) {
  if (metricGroups.some((group) => group.collapsed === true)) {
    return {
      primary: metricGroups.filter((group) => !group.collapsed),
      extra: metricGroups.filter((group) => group.collapsed),
    };
  }
  return {
    primary: metricGroups.slice(0, OMNI_HISTORY_PRIMARY_CHART_COUNT),
    extra: metricGroups.slice(OMNI_HISTORY_PRIMARY_CHART_COUNT),
  };
}

function renderOmniCharts(payload, records, root, renderFn) {
  const container = root.querySelector("[data-omni-history-charts]");
  if (!container) {
    return;
  }
  const dateRange = currentOmniDateRange(root);
  const hasDateRange = Boolean(dateRange.from || dateRange.to);
  const selectedDays = ensureOmniTrendRangeControl(root, () => renderFn(payload, root), hasDateRange);
  // An explicit date range replaces the relative trend window.
  const chartRecords = hasDateRange ? records : filterRecordsByRecentDays(records, selectedDays);
  const chartPointPerDay = payload.chart_point_per_day !== false;
  const seriesCap = Number(payload.default_visible_series) || null;
  disposeChartsWithin(container);
  container.innerHTML = "";

  const { primary: primaryGroups, extra: extraGroups } = splitOmniMetricGroups(payload.metric_groups);
  ensureOmniMetricJumpNav(root, primaryGroups, extraGroups);

  const primary = document.createElement("div");
  primary.className = "omni-chart-grid";
  container.append(primary);
  primaryGroups.forEach((metricGroup) => {
    renderOmniChartSection(primary, metricGroup, chartRecords, payload.group_fields, chartPointPerDay, seriesCap);
  });

  if (extraGroups.length > 0) {
    const details = document.createElement("details");
    details.className = "omni-more-charts";
    details.id = "omni-more-charts";
    details.innerHTML = '<summary>More charts</summary>';
    const extra = document.createElement("div");
    extra.className = "omni-chart-grid omni-chart-grid--stacked";
    details.append(extra);
    container.append(details);
    let extraRendered = false;
    const renderExtraCharts = () => {
      if (extraRendered) {
        return;
      }
      extraGroups.forEach((metricGroup) => {
        renderOmniChartSection(extra, metricGroup, chartRecords, payload.group_fields, chartPointPerDay, seriesCap);
      });
      extraRendered = true;
    };
    details.addEventListener("toggle", () => {
      if (details.open) {
        renderExtraCharts();
      }
    });
  }
}

function renderQwen3OmniHistory(payload, root, options = {}) {
  const filters = currentOmniFilters(payload, root);
  const dateRange = currentOmniDateRange(root);
  const openField = options.preserveOpenFilter ?? getOpenOmniFilterField(root);
  renderOmniFilterBar(payload, filters, root, { openField });
  const filtered = filterRecordsByDateRange(
    sortRecordsByTimeDesc(filterRecords(payload.records, filters)),
    dateRange,
  );
  renderOmniSummary(filtered, payload.group_fields, root);
  renderOmniCharts(payload, filtered, root, renderQwen3OmniHistory);
  renderOmniTable(payload, filtered, root);
}

async function loadQwen3OmniHistory() {
  const roots = document.querySelectorAll("[data-omni-history-src]");
  if (!roots.length) {
    return;
  }

  await Promise.all(
    [...roots].map(async (root) => {
      try {
        const payload = await fetchJson(root.dataset.omniHistorySrc);
        renderQwen3OmniHistory(payload, root);
      } catch (error) {
        const msg = document.createElement("div");
        msg.className = "omni-empty-state";
        msg.textContent = `Failed to load history: ${error.message}`;
        root.prepend(msg);
      }
    }),
  );
}

function frameworkComparisonScopedRecords(payload, root) {
  const modelFamily = root.dataset.frameworkComparisonModelFamily;
  const records = payload.records || [];
  if (!modelFamily) {
    return records;
  }
  return records.filter((record) => String(record.model_family || "") === modelFamily);
}

function comparisonMetricFields(payload) {
  return (payload.metric_groups || []).flatMap((group) => group.metrics || []);
}

function comparableWorkloadCount(records) {
  const byWorkload = new Map();
  records.forEach((record) => {
    const key = String(record.comparison_key || "");
    if (!byWorkload.has(key)) {
      byWorkload.set(key, new Set());
    }
    byWorkload.get(key).add(String(record.framework || ""));
  });
  return [...byWorkload.values()].filter((items) => items.size > 1).length;
}

function lowerIsBetterMetric(metric) {
  return /(latency|ttft|tpot|ttfp|e2e|e2el|itl|rtf|memory|duration|ms|gb)$/i.test(metric)
    && !/(throughput|score|mos|similarity)$/i.test(metric);
}

function frameworkBaselineCandidates(payload) {
  const candidates = Array.isArray(payload.baseline_candidates) ? payload.baseline_candidates : [];
  return [payload.baseline_framework, ...candidates].filter(Boolean).map((item) => String(item));
}

function formatComparisonDelta(value, baseline, metric) {
  if (!isNumeric(value) || !isNumeric(baseline) || Number(baseline) === 0) {
    return { html: "--", className: "" };
  }
  const pct = ((Number(value) - Number(baseline)) / Number(baseline)) * 100;
  const better = lowerIsBetterMetric(metric) ? pct < 0 : pct > 0;
  const sign = pct > 0 ? "+" : "";
  return {
    html: `${sign}${pct.toFixed(1)}%`,
    className: better ? "comparison-delta comparison-delta--good" : "comparison-delta comparison-delta--bad",
  };
}

function renderFrameworkComparisonSummary(payload, records, root) {
  const container = root.querySelector("[data-framework-comparison-summary]");
  if (!container) {
    return;
  }
  const comparable = comparableWorkloadCount(records);
  container.innerHTML = `
    <div class="omni-summary-card">
      <span class="omni-summary-card__eyebrow">Visible Records</span>
      <strong class="omni-summary-card__value">${records.length}</strong>
    </div>
    <div class="omni-summary-card">
      <span class="omni-summary-card__eyebrow">Comparable Workloads</span>
      <strong class="omni-summary-card__value">${comparable}</strong>
    </div>
    <div class="omni-summary-card">
      <span class="omni-summary-card__eyebrow">Baseline</span>
      <strong class="omni-summary-card__value">${escapeHtml(payload.baseline_framework || "--")}</strong>
    </div>
  `;
}

function comparisonDay(record) {
  const ts = record.sort_timestamp || record.date || "";
  return typeof ts === "string" && ts.length >= 10 ? ts.slice(0, 10) : "";
}

function comparisonFrameworkIsVllm(record, payload) {
  const candidates = new Set(frameworkBaselineCandidates(payload));
  return candidates.has(String(record.framework || ""));
}

function uniqueSorted(values) {
  return [...new Set(values.filter(Boolean).map((value) => String(value)))].sort();
}

function recordsForWorkload(records, workloadKey) {
  return records.filter((record) => String(record.workload_key || "") === String(workloadKey || ""));
}

function metricHasBothFrameworks(payload, records, metric) {
  const hasVllm = records.some((record) => comparisonFrameworkIsVllm(record, payload) && isNumeric(record[metric]));
  const hasSglang = records.some((record) => record.framework === "sglang" && isNumeric(record[metric]));
  return hasVllm && hasSglang;
}

function metricOptionsForRecords(payload, records) {
  const fields = comparisonMetricFields(payload);
  return (payload.metric_options || fields.map((field) => ({ value: field, label: humanizeField(field) })))
    .filter((item) => metricHasBothFrameworks(payload, records, item.value));
}

function comparisonMetricButtonsHtml(metricOptions, selectedMetric) {
  return metricOptions.map((item) => {
    const active = item.value === selectedMetric ? " comparison-metric-button--active" : "";
    return `
      <button
        type="button"
        class="comparison-metric-button${active}"
        data-comparison-metric="${escapeHtml(item.value)}"
      >${escapeHtml(item.label || humanizeField(item.value))}</button>
    `;
  }).join("");
}

function comparisonMetricToolbarHtml(metricOptions, selectedMetric) {
  const primaryMetrics = metricOptions.slice(0, 3);
  const overflowMetrics = metricOptions.slice(3);
  const moreMetricsOpen = overflowMetrics.some((item) => item.value === selectedMetric) ? " open" : "";
  return `
    <div class="comparison-metric-buttons">
      ${comparisonMetricButtonsHtml(primaryMetrics, selectedMetric)}
      ${overflowMetrics.length ? `
        <details class="comparison-metric-more"${moreMetricsOpen}>
          <summary>More metrics</summary>
          <div class="comparison-metric-more__items">
            ${comparisonMetricButtonsHtml(overflowMetrics, selectedMetric)}
          </div>
        </details>
      ` : ""}
    </div>
  `;
}

function latestRecordPerDay(records) {
  const byDay = new Map();
  records.forEach((record) => {
    const day = comparisonDay(record);
    if (!day) {
      return;
    }
    const previous = byDay.get(day);
    if (!previous || String(record.sort_timestamp || "") > String(previous.sort_timestamp || "")) {
      byDay.set(day, record);
    }
  });
  return [...byDay.values()].sort((a, b) => String(a.sort_timestamp || "").localeCompare(String(b.sort_timestamp || "")));
}

function comparableModelFamilies(payload, records) {
  const visibleModels = new Set(records.map((record) => record.model_family).filter(Boolean));
  return uniqueSorted((payload.workload_options || [])
    .filter((item) => item.comparable && visibleModels.has(item.model_family))
    .map((item) => item.model_family));
}

function comparisonDefaultState(payload, records, root) {
  const modelFamilies = comparableModelFamilies(payload, records);
  const selectedModel = root.dataset.comparisonModelFamily && modelFamilies.includes(root.dataset.comparisonModelFamily)
    ? root.dataset.comparisonModelFamily
    : modelFamilies[0] || "";
  root.dataset.comparisonModelFamily = selectedModel;

  const modelWorkloads = (payload.workload_options || []).filter((item) => item.model_family === selectedModel);
  const currentWorkload = modelWorkloads.find((item) => item.key === root.dataset.comparisonWorkloadKey);
  const selectedWorkload = currentWorkload || modelWorkloads.find((item) => item.comparable) || modelWorkloads[0] || null;
  root.dataset.comparisonWorkloadKey = selectedWorkload?.key || "";

  const workloadRecords = recordsForWorkload(records, root.dataset.comparisonWorkloadKey);
  const metricOptions = metricOptionsForRecords(payload, workloadRecords);
  const currentMetric = metricOptions.find((item) => item.value === root.dataset.comparisonMetric);
  const selectedMetric = currentMetric?.value || metricOptions[0]?.value || "";
  root.dataset.comparisonMetric = selectedMetric;

  const vllmDays = uniqueSorted(workloadRecords.filter((record) => comparisonFrameworkIsVllm(record, payload)).map(comparisonDay));
  const sglangDays = uniqueSorted(workloadRecords.filter((record) => record.framework === "sglang").map(comparisonDay));
  if (!root.dataset.comparisonVllmFrom && vllmDays.length) {
    root.dataset.comparisonVllmFrom = vllmDays[0];
  }
  if (!root.dataset.comparisonVllmTo && vllmDays.length) {
    root.dataset.comparisonVllmTo = vllmDays[vllmDays.length - 1];
  }
  if (!root.dataset.comparisonSglangDate || !sglangDays.includes(root.dataset.comparisonSglangDate)) {
    root.dataset.comparisonSglangDate = sglangDays[sglangDays.length - 1] || "";
  }

  return {
    modelFamily: root.dataset.comparisonModelFamily,
    workloadKey: root.dataset.comparisonWorkloadKey,
    metric: root.dataset.comparisonMetric,
    vllmFrom: root.dataset.comparisonVllmFrom || "",
    vllmTo: root.dataset.comparisonVllmTo || "",
    sglangDate: root.dataset.comparisonSglangDate || "",
  };
}

function renderComparisonControls(payload, records, root, state) {
  const container = root.querySelector("[data-framework-comparison-controls]");
  if (!container) {
    return;
  }
  const modelFamilies = comparableModelFamilies(payload, records);
  const workloadOptions = (payload.workload_options || []).filter((item) => item.model_family === state.modelFamily);
  const workloadRecords = recordsForWorkload(records, state.workloadKey);
  const vllmDays = uniqueSorted(workloadRecords.filter((record) => comparisonFrameworkIsVllm(record, payload)).map(comparisonDay));
  const sglangDays = uniqueSorted(workloadRecords.filter((record) => record.framework === "sglang").map(comparisonDay));
  const optionHtml = (items, selected, labelFn = (item) => item) => items.map((item) => {
    const value = typeof item === "string" ? item : item.value || item.key;
    const label = labelFn(item);
    const isSelected = String(value) === String(selected) ? " selected" : "";
    return `<option value="${escapeHtml(String(value))}"${isSelected}>${escapeHtml(String(label))}</option>`;
  }).join("");
  container.innerHTML = `
    <label class="omni-filter comparison-control--wide">
      <span class="omni-filter__label">Model</span>
      <select class="omni-filter__input" data-comparison-control="modelFamily">
        ${optionHtml(modelFamilies, state.modelFamily)}
      </select>
    </label>
    <label class="omni-filter comparison-control--xwide">
      <span class="omni-filter__label">Test Config</span>
      <select class="omni-filter__input" data-comparison-control="workloadKey">
        ${optionHtml(workloadOptions, state.workloadKey, (item) => `${item.comparable ? "" : "[not comparable] "}${item.label}`)}
      </select>
    </label>
    <label class="omni-filter">
      <span class="omni-filter__label">vLLM From</span>
      <input class="omni-filter__input" type="date" value="${escapeHtml(state.vllmFrom)}" data-comparison-control="vllmFrom">
    </label>
    <label class="omni-filter">
      <span class="omni-filter__label">vLLM To</span>
      <input class="omni-filter__input" type="date" value="${escapeHtml(state.vllmTo)}" data-comparison-control="vllmTo">
    </label>
    <label class="omni-filter">
      <span class="omni-filter__label">SGLang Date</span>
      <select class="omni-filter__input" data-comparison-control="sglangDate">
        <option value="">No SGLang date</option>
        ${optionHtml(sglangDays, state.sglangDate)}
      </select>
    </label>
  `;
  container.querySelectorAll("[data-comparison-control]").forEach((input) => {
    input.addEventListener("change", () => {
      const key = input.dataset.comparisonControl;
      const datasetKey = `comparison${key.charAt(0).toUpperCase()}${key.slice(1)}`;
      root.dataset[datasetKey] = input.value;
      if (key === "modelFamily") {
        root.dataset.comparisonWorkloadKey = "";
        root.dataset.comparisonMetric = "";
        root.dataset.comparisonVllmFrom = "";
        root.dataset.comparisonVllmTo = "";
        root.dataset.comparisonSglangDate = "";
      }
      if (key === "workloadKey") {
        root.dataset.comparisonMetric = "";
        root.dataset.comparisonVllmFrom = "";
        root.dataset.comparisonVllmTo = "";
        root.dataset.comparisonSglangDate = "";
      }
      renderFrameworkComparison(payload, root);
    });
  });
}

function filterVllmByDateRange(records, state) {
  return records.filter((record) => {
    const day = comparisonDay(record);
    if (!day) {
      return false;
    }
    if (state.vllmFrom && day < state.vllmFrom) {
      return false;
    }
    if (state.vllmTo && day > state.vllmTo) {
      return false;
    }
    return true;
  });
}

function selectedComparisonRecords(payload, records, state) {
  const workloadRecords = recordsForWorkload(records, state.workloadKey);
  const vllm = filterVllmByDateRange(
    workloadRecords.filter((record) => comparisonFrameworkIsVllm(record, payload) && isNumeric(record[state.metric])),
    state,
  );
  const sglang = workloadRecords.filter((record) =>
    record.framework === "sglang"
    && isNumeric(record[state.metric])
    && (!state.sglangDate || comparisonDay(record) === state.sglangDate),
  );
  return { workloadRecords, vllm: latestRecordPerDay(vllm), sglang: latestRecordPerDay(sglang) };
}

function renderSelectedConfigSummary(records, state, root) {
  const container = root.querySelector("[data-framework-comparison-config]");
  if (!container) {
    return;
  }
  const sample = recordsForWorkload(records, state.workloadKey)[0];
  if (!sample) {
    container.innerHTML = '<div class="omni-empty-state">Select a comparable workload to inspect its dimensions.</div>';
    return;
  }
  const fields = [
    "model_family", "workload_profile", "task", "dataset_name", "endpoint", "hardware",
    "parallelism", "width", "height", "num_inference_steps", "num_input_images",
    "max_concurrency", "num_prompts",
  ];
  const resolution = sample.width && sample.height ? `${sample.width}x${sample.height}` : "";
  const summaryItems = [
    sample.model_family,
    sample.workload_profile,
    sample.task,
    resolution,
    sample.num_inference_steps ? `${sample.num_inference_steps} steps` : "",
    sample.num_input_images !== undefined && sample.num_input_images !== null ? `${sample.num_input_images} images` : "",
    sample.parallelism,
    sample.hardware,
  ].filter((value) => value !== undefined && value !== null && value !== "");
  container.innerHTML = `
    <div class="comparison-config-compact">
      <div class="comparison-config-compact__summary">
        ${summaryItems.map((item) => `<span class="comparison-config-chip">${escapeHtml(String(item))}</span>`).join("")}
      </div>
      <details class="comparison-config-details">
        <summary>Show config details</summary>
        <div class="comparison-config-detail-grid">
          ${fields.map((field) => `
            <div class="comparison-config-detail">
              <span>${escapeHtml(humanizeField(field))}</span>
              <strong>${formatTableValue(field, sample[field])}</strong>
            </div>
          `).join("")}
        </div>
      </details>
    </div>
  `;
}

function renderComparisonMetricToolbar(payload, records, state, root) {
  const container = root.querySelector("[data-framework-comparison-metrics]");
  if (!container) {
    return;
  }
  const workloadRecords = recordsForWorkload(records, state.workloadKey);
  const metricOptions = metricOptionsForRecords(payload, workloadRecords);
  if (!metricOptions.length) {
    container.innerHTML = '<div class="omni-empty-state">No shared metrics are available for this workload.</div>';
    return;
  }
  container.innerHTML = `
    <div class="comparison-metric-toolbar">
      <span class="comparison-metric-toolbar__label">Metric</span>
      ${comparisonMetricToolbarHtml(metricOptions, state.metric)}
    </div>
  `;
  container.querySelectorAll("[data-comparison-metric]").forEach((button) => {
    button.addEventListener("click", () => {
      root.dataset.comparisonMetric = button.dataset.comparisonMetric || "";
      renderFrameworkComparison(payload, root);
    });
  });
}

function buildMetricComparisonOption(payload, state, selected) {
  const chartDays = uniqueSorted([...(selected.vllm || []), ...(selected.sglang || [])].map(comparisonDay));
  let referenceStart = chartDays[0] || "";
  let referenceEnd = chartDays[chartDays.length - 1] || referenceStart;
  if (referenceStart && referenceStart === referenceEnd) {
    const center = new Date(`${referenceStart}T00:00:00`);
    if (Number.isNaN(center.getTime())) {
      referenceStart = "";
      referenceEnd = "";
    } else {
      const halfDayMs = 12 * 60 * 60 * 1000;
      referenceStart = new Date(center.getTime() - halfDayMs).toISOString();
      referenceEnd = new Date(center.getTime() + halfDayMs).toISOString();
    }
  }
  const vllmSeries = {
    name: "vLLM-Omni",
    type: "line",
    z: 2,
    color: OMNI_LINE_SERIES_PALETTE[0],
    lineStyle: { width: 2.5, color: OMNI_LINE_SERIES_PALETTE[0] },
    itemStyle: { color: OMNI_LINE_SERIES_PALETTE[0] },
    showSymbol: true,
    symbolSize: 6,
    smooth: false,
    data: selected.vllm.map((record) => ({
      value: [comparisonDay(record), Number(record[state.metric])],
      meta: record,
    })),
  };
  const sglangSeries = {
    name: "SGLang",
    type: "scatter",
    z: 4,
    color: OMNI_LINE_SERIES_PALETTE[3],
    itemStyle: { color: OMNI_LINE_SERIES_PALETTE[3] },
    symbolSize: 12,
    data: selected.sglang.map((record) => ({
      value: [comparisonDay(record), Number(record[state.metric])],
      meta: record,
    })),
  };
  const sglangReferenceSeries = (selected.sglang || [])
    .filter((record) => referenceStart && referenceEnd && isNumeric(record[state.metric]))
    .map((record) => {
      const value = Number(record[state.metric]);
      return {
        name: `SGLang ${formatMetricValue(value)}`,
        type: "line",
        z: 1,
        showSymbol: false,
        silent: true,
        showInLegend: false,
        lineStyle: { type: "dashed", width: 2, color: OMNI_LINE_SERIES_PALETTE[3] },
        data: [
          [referenceStart, value],
          [referenceEnd, value],
        ],
        endLabel: {
          show: true,
          formatter: `SGLang ${formatMetricValue(value)}`,
          color: OMNI_LINE_SERIES_PALETTE[3],
        },
        emphasis: {
          disabled: true,
        },
      };
    });
  return {
    color: OMNI_LINE_SERIES_PALETTE,
    tooltip: {
      trigger: "item",
      formatter(params) {
        const record = params.data?.meta || {};
        return [
          `<strong>${escapeHtml(params.seriesName || "")}</strong>`,
          `Date: ${escapeHtml(comparisonDay(record) || "--")}`,
          `${escapeHtml(humanizeField(state.metric))}: ${formatMetricValue(params.data?.value?.[1])}`,
          `Config: ${escapeHtml(record.workload_label || "--")}`,
          `Test: ${escapeHtml(record.test_name || "--")}`,
          `Parallelism: ${escapeHtml(record.parallelism || "--")}`,
          `Source: ${escapeHtml(record.source_format || "--")}`,
        ].join("<br>");
      },
    },
    legend: { top: 0, left: 0, data: ["vLLM-Omni", "SGLang"] },
    grid: { left: 72, right: 48, top: 56, bottom: 64, containLabel: true },
    xAxis: {
      type: "time",
      axisLabel: {
        rotate: 35,
        formatter: createOmniXAxisDateLabelFormatter(),
      },
    },
    yAxis: {
      type: "value",
      name: humanizeField(state.metric),
      axisLabel: {
        formatter(value) {
          return Number(value).toFixed(2);
        },
      },
    },
    series: [vllmSeries, ...sglangReferenceSeries, sglangSeries],
  };
}

function renderMetricComparisonChart(payload, records, state, root) {
  const container = root.querySelector("[data-framework-comparison-chart]");
  if (!container) {
    return null;
  }
  disposeChartsWithin(container);
  container.innerHTML = "";
  const selected = selectedComparisonRecords(payload, records, state);
  if (!state.metric || (selected.vllm.length === 0 && selected.sglang.length === 0)) {
    container.innerHTML = '<div class="omni-empty-state">No chartable values for the selected workload and metric.</div>';
    return selected;
  }
  const chart = document.createElement("div");
  chart.className = "chart-frame chart-frame-tall";
  container.append(chart);
  setChart(chart, buildMetricComparisonOption(payload, state, selected));
  return selected;
}

function renderSelectedRawValues(payload, selected, state, root) {
  const container = root.querySelector("[data-framework-comparison-values]");
  if (!container) {
    return;
  }
  const rows = [...(selected?.vllm || []), ...(selected?.sglang || [])]
    .sort((a, b) => String(a.framework || "").localeCompare(String(b.framework || "")) || comparisonDay(a).localeCompare(comparisonDay(b)));
  if (!rows.length) {
    container.innerHTML = '<div class="omni-empty-state">No values are selected for the current chart.</div>';
    return;
  }
  const sglangValue = selected?.sglang?.[0]?.[state.metric];
  const header = [
    "framework", "date", state.metric, "vs_sglang", "test_name", "parallelism",
    "peak_memory_status", "source_format", "source_run_id", "source_file",
  ]
    .map((field) => `<th scope="col">${escapeHtml(humanizeField(field))}</th>`)
    .join("");
  const body = rows.map((record) => {
    const delta = record.framework === "sglang" ? { html: "baseline", className: "" } : formatComparisonDelta(record[state.metric], sglangValue, state.metric);
    const cells = [
      record.framework,
      comparisonDay(record),
      formatMetricValue(record[state.metric]),
      `<span class="${delta.className}">${delta.html}</span>`,
      record.test_name,
      record.parallelism,
      record.peak_memory_status,
      record.source_format,
      record.source_run_id,
      record.source_file,
    ].map((value) => `<td class="omni-history-table__cell">${typeof value === "string" && value.startsWith("<span") ? value : escapeHtml(String(value ?? "--"))}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  container.innerHTML = `
    <div class="omni-history-table__wrap">
      <table class="omni-history-table">
        <thead><tr>${header}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function renderFrameworkComparison(payload, root) {
  const scopedRecords = frameworkComparisonScopedRecords(payload, root);
  const records = sortRecordsByTimeDesc(scopedRecords);
  const state = comparisonDefaultState(payload, records, root);
  renderComparisonControls(payload, records, root, state);
  renderFrameworkComparisonSummary(payload, records, root);
  renderSelectedConfigSummary(records, state, root);
  renderComparisonMetricToolbar(payload, records, state, root);
  const selected = renderMetricComparisonChart(payload, records, state, root);
  renderSelectedRawValues(payload, selected, state, root);
}

async function loadFrameworkComparison() {
  const roots = document.querySelectorAll("[data-framework-comparison-src]");
  if (!roots.length) {
    return;
  }
  await Promise.all([...roots].map(async (root) => {
    try {
      const payload = await fetchJson(root.dataset.frameworkComparisonSrc);
      renderFrameworkComparison(payload, root);
    } catch (error) {
      const msg = document.createElement("div");
      msg.className = "omni-empty-state";
      msg.textContent = `Failed to load framework comparison: ${error.message}`;
      root.prepend(msg);
    }
  }));
}

function bindRangePicker() {
  const picker = document.querySelector("[data-time-range]");
  if (!picker) {
    return;
  }
  picker.addEventListener("change", async () => {
    await reloadCharts();
  });
}

function observeColorScheme() {
  const target = document.body;
  if (!target) {
    return;
  }
  const observer = new MutationObserver(() => {
    reloadCharts();
  });
  observer.observe(target, { attributes: true, attributeFilter: ["data-md-color-scheme"] });
}

/**
 * InferenceX-style page view tabs. Markdown wraps page regions in
 * `<div data-omni-tab="Performance">…</div>`; the nav (`[data-omni-page-tabs]`)
 * is filled with one button per region, in document order.
 */
function initOmniPageTabs() {
  const nav = document.querySelector("[data-omni-page-tabs]");
  const panels = [...document.querySelectorAll("[data-omni-tab]")];
  if (!nav || panels.length === 0) {
    return;
  }
  const found = [...new Set(panels.map((panel) => panel.dataset.omniTab).filter(Boolean))];
  // Optional explicit order: <nav data-omni-page-tabs="Performance,Accuracy,History">.
  const explicit = (nav.dataset.omniPageTabs || "").split(",").map((s) => s.trim()).filter(Boolean);
  const names = explicit.length
    ? [...explicit.filter((name) => found.includes(name)), ...found.filter((name) => !explicit.includes(name))]
    : found;
  if (names.length < 2) {
    nav.hidden = true;
    return;
  }
  nav.innerHTML = names.map((name) => `
    <button type="button" class="omni-page-tabs__btn" data-omni-tab-target="${escapeHtml(name)}">${escapeHtml(name)}</button>
  `).join("");

  const activate = (name) => {
    nav.querySelectorAll("[data-omni-tab-target]").forEach((btn) => {
      btn.classList.toggle("omni-page-tabs__btn--active", btn.dataset.omniTabTarget === name);
    });
    panels.forEach((panel) => {
      panel.hidden = panel.dataset.omniTab !== name;
    });
    // Charts initialized while hidden have zero size; re-measure the visible ones.
    charts.forEach((instance, container) => {
      if (container.offsetParent !== null) {
        instance.resize();
      }
    });
  };
  nav.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-omni-tab-target]");
    if (btn) {
      activate(btn.dataset.omniTabTarget);
    }
  });
  activate(names[0]);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    buildOmniChartOption,
    buildMetricComparisonOption,
    compareNullableNumber,
    comparableModelFamilies,
    comparisonMetricToolbarHtml,
    metricOptionsForRecords,
    selectDefaultVisibleSeriesKeys,
  };
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", async () => {
    ensureTechnicalRail();
    renderRailModelNodes();
    bindRangePicker();
    bindRailSpy();
    observeColorScheme();
    initOmniPageTabs();
    await Promise.all([loadHomeOverview(), loadHealth(), loadHardwareStatus(), reloadCharts(), loadQwen3OmniHistory(), loadFrameworkComparison()]);
  });
}
