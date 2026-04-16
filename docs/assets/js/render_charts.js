const charts = new Map();
let resizeBound = false;

/** Metric groups in the main trend grid before "More charts" (through E2EL + Audio RTF). */
const OMNI_HISTORY_PRIMARY_CHART_COUNT = 7;

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

/**
 * Data lines use palette; baseline uses neutral slate (see omniBaselineChrome) for contrast.
 */
function applyOmniLineSeriesColors(seriesList) {
  const bl = omniBaselineChrome();
  seriesList.forEach((s, i) => {
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
        // Avoid grid clipPath cutting off the baseline label at the right edge (see ECharts markLine + label).
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
          position: "end",
          // Pull left from the plot edge so the full pill (incl. border) stays inside the canvas.
          distance: [-22, 2 + i * 14],
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
          // confine:true was squeezing/clipping the box; rely on grid.right + distance instead.
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

async function loadChart(container) {
  const src = chartSrc(container, selectedRange());
  if (!src || typeof echarts === "undefined") {
    return;
  }

  try {
    const option = applyTheme(await fetchJson(src));
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
    e2el: "E2EL",
    rtf: "RTF",
    qps: "QPS",
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
      chart.dispose();
      charts.delete(container);
    }
  });
}

function omniOptionHasMarkLineSeries(option) {
  const s = option?.series;
  return Array.isArray(s) && s.some((x) => x?.markLine);
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

function setChart(container, option) {
  if (typeof echarts === "undefined") {
    return;
  }
  const chart = charts.get(container) || echarts.init(container);
  if (typeof chart.__omniBaselineDispose === "function") {
    chart.__omniBaselineDispose();
    chart.__omniBaselineDispose = null;
  }
  chart.setOption(applyTheme(option), true);
  charts.set(container, chart);
  if (omniOptionHasMarkLineSeries(option)) {
    wireOmniBaselineHover(chart);
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

function filterRecords(records, filters) {
  return records.filter((record) => Object.entries(filters).every(([field, value]) => {
    if (!value) {
      return true;
    }
    const raw = record[field];
    if (raw === null || raw === undefined) {
      return false;
    }
    if (typeof raw === "number") {
      return String(raw) === value.trim();
    }
    // Exact string match (substring match would e.g. let qwen3_omni match qwen3_omni_chunk).
    return String(raw).trim() === value.trim();
  }));
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
    const points = rows
      .sort((left, right) => left.sort_timestamp.localeCompare(right.sort_timestamp))
      .map((item) => {
        const day = recordCalendarDay(item);
        // Use local midnight so dots sit on time-axis day ticks (ECharts places day ticks at 00:00).
        const xVal = pointPerDay && day ? `${day}T00:00:00` : item.date;
        return {
          value: [xVal, item[metric]],
          meta: {
            test_name: item.test_name,
            dataset_name: item.dataset_name,
            max_concurrency: item.max_concurrency,
            num_prompts: item.num_prompts,
            random_input_len: item.random_input_len,
            random_output_len: item.random_output_len,
            metric,
            source_file: item.source_file,
            baseline: baseVal,
          },
        };
      });
    if (points.length > 0) {
      const n = points.length;
      const lineSeries = {
        name: buildSeriesLabel(items[0], groupFields),
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
            position: "end",
            formatter: () => `baseline ${formatMetricValue(baseVal)}`,
          },
          data: [{ yAxis: baseVal }],
        };
      }
      series.push(lineSeries);
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
    `Value: ${formatMetricValue(val)}`,
  ];
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
    `Random input len: ${escapeHtml(String(meta.random_input_len ?? "--"))}`,
    `Random output len: ${escapeHtml(String(meta.random_output_len ?? "--"))}`,
  );
  return lines.join("<br>");
}

function buildOmniChartOption(metricGroup, records, groupFields, chartPointPerDay) {
  const opts = { pointPerDay: chartPointPerDay !== false };
  const series = applyOmniLineSeriesColors(
    metricGroup.metrics.flatMap((metric) => buildOmniMetricSeries(records, metric, groupFields, opts)),
  );
  const maxPoints = series.reduce((maxCount, s) => Math.max(maxCount, s.data?.length || 0), 0);
  const hasBaseline = series.some((s) => s.markLine);
  const yValues = [];
  const baselineValues = [];
  series.forEach((s) => {
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
    yMin = minV - pad;
    yMax = maxV + pad;
  }
  return {
    color: OMNI_LINE_SERIES_PALETTE,
    animationDurationUpdate: 200,
    tooltip: {
      trigger: "item",
      formatter: formatOmniHistoryTooltipHtml,
    },
    legend: {
      type: "scroll",
      top: 0,
      textStyle: { fontSize: 11 },
    },
    grid: {
      left: 56,
      right: hasBaseline ? 132 : 24,
      top: 60,
      bottom: 24,
      containLabel: true,
    },
    xAxis: {
      type: "time",
      minInterval: 24 * 60 * 60 * 1000,
      axisLabel: {
        show: maxPoints > 0,
        hideOverlap: true,
        formatter(value) {
          return formatOmniHistoryChartDate(value);
        },
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

function ensureHistoryInstanceId(root) {
  if (!root.dataset.historyInstance) {
    root.dataset.historyInstance = String(_historyInstanceSeq++);
  }
  return root.dataset.historyInstance;
}

function renderOmniFilterBar(payload, filters, root) {
  const container = root.querySelector("[data-omni-history-filters]");
  if (!container) {
    return;
  }
  const hid = ensureHistoryInstanceId(root);
  container.innerHTML = payload.filters.map((field) => {
    const datalistId = `omni-filter-${field}-${hid}`;
    const options = (payload.filter_options?.[field] || [])
      .map((option) => `<option value="${escapeHtml(String(option))}"></option>`)
      .join("");
    return `
      <label class="omni-filter">
        <span class="omni-filter__label">${escapeHtml(humanizeField(field))}</span>
        <input
          class="omni-filter__input"
          type="text"
          list="${datalistId}"
          data-omni-filter="${field}"
          value="${escapeHtml(filters[field] || "")}"
          placeholder="All"
        >
        <datalist id="${datalistId}">${options}</datalist>
      </label>
    `;
  }).join("") + `
    <button type="button" class="omni-filter__reset" data-omni-filter-reset>Reset filters</button>
  `;

  container.querySelectorAll("[data-omni-filter]").forEach((input) => {
    input.addEventListener("input", () => {
      renderQwen3OmniHistory(payload, root);
    });
  });
  container.querySelector("[data-omni-filter-reset]")?.addEventListener("click", () => {
    container.querySelectorAll("[data-omni-filter]").forEach((input) => {
      input.value = "";
    });
    renderQwen3OmniHistory(payload, root);
  });
}

function currentOmniFilters(payload, root) {
  const inputs = [...root.querySelectorAll("[data-omni-filter]")];
  return payload.filters.reduce((acc, field) => {
    const input = inputs.find((item) => item.dataset.omniFilter === field);
    acc[field] = input?.value?.trim() || "";
    return acc;
  }, {});
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

function renderOmniChartSection(section, metricGroup, records, groupFields, chartPointPerDay) {
  const opts = { pointPerDay: chartPointPerDay !== false };
  const chartRoot = document.createElement("section");
  chartRoot.className = "omni-chart-card";
  const allSeries = metricGroup.metrics.flatMap((metric) => buildOmniMetricSeries(records, metric, groupFields, opts));

  chartRoot.innerHTML = `
    <div class="omni-chart-card__header">
      <div>
        <h3>${escapeHtml(metricGroup.title)}</h3>
        <p>${metricGroup.metrics.map(humanizeField).join(" · ")}</p>
      </div>
      <span class="omni-chart-card__badge">${allSeries.length} series</span>
    </div>
  `;

  if (allSeries.length === 0) {
    const empty = document.createElement("div");
    empty.className = "omni-empty-state";
    empty.textContent = "当前筛选条件下没有数据。";
    chartRoot.append(empty);
    section.append(chartRoot);
    return;
  }

  const chart = document.createElement("div");
  chart.className = "chart-frame omni-chart-frame";
  chartRoot.append(chart);
  section.append(chartRoot);
  setChart(chart, buildOmniChartOption(metricGroup, records, groupFields, chartPointPerDay));
}

function renderOmniCharts(payload, records, root) {
  const container = root.querySelector("[data-omni-history-charts]");
  if (!container) {
    return;
  }
  const chartPointPerDay = payload.chart_point_per_day !== false;
  disposeChartsWithin(container);
  container.innerHTML = "";

  const primary = document.createElement("div");
  primary.className = "omni-chart-grid";
  container.append(primary);
  payload.metric_groups.slice(0, OMNI_HISTORY_PRIMARY_CHART_COUNT).forEach((metricGroup) => {
    renderOmniChartSection(primary, metricGroup, records, payload.group_fields, chartPointPerDay);
  });

  if (payload.metric_groups.length > OMNI_HISTORY_PRIMARY_CHART_COUNT) {
    const details = document.createElement("details");
    details.className = "omni-more-charts";
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
      payload.metric_groups.slice(OMNI_HISTORY_PRIMARY_CHART_COUNT).forEach((metricGroup) => {
        renderOmniChartSection(extra, metricGroup, records, payload.group_fields, chartPointPerDay);
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

function renderQwen3OmniHistory(payload, root) {
  const filters = currentOmniFilters(payload, root);
  renderOmniFilterBar(payload, filters, root);
  const filtered = sortRecordsByTimeDesc(filterRecords(payload.records, filters));
  renderOmniSummary(filtered, payload.group_fields, root);
  renderOmniCharts(payload, filtered, root);
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

document.addEventListener("DOMContentLoaded", async () => {
  ensureTechnicalRail();
  renderRailModelNodes();
  bindRangePicker();
  bindRailSpy();
  observeColorScheme();
  await Promise.all([loadHealth(), loadHardwareStatus(), reloadCharts(), loadQwen3OmniHistory()]);
});
