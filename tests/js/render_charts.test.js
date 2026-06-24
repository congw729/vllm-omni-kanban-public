const assert = require("node:assert/strict");
const test = require("node:test");

global.document = {
  body: {},
  addEventListener: () => {},
  createElement: () => ({
    innerHTML: "",
    set textContent(value) {
      this.innerHTML = String(value);
    },
  }),
};
global.getComputedStyle = () => ({ getPropertyValue: () => "" });

const {
  buildOmniChartOption,
  buildMetricComparisonOption,
  compareNullableNumber,
  comparableModelFamilies,
  comparisonMetricToolbarHtml,
  metricOptionsForRecords,
  selectDefaultVisibleSeriesKeys,
} = require("../../docs/assets/js/render_charts.js");

function series(key, meta) {
  return {
    __omniSeriesKey: key,
    data: [{ meta }],
  };
}

function record(name, maxConcurrency, inputLen, metricValue) {
  return {
    config_key: name,
    scenario: name,
    test_name: name,
    dataset_name: "random",
    max_concurrency: maxConcurrency,
    num_prompts: 10,
    random_input_len: inputLen,
    random_output_len: 100,
    mean_ttft_ms: metricValue,
    sort_timestamp: "2026-06-01T00:00:00",
    date: "2026-06-01 00:00:00",
  };
}

function colorBySeriesKey(option) {
  return Object.fromEntries(
    option.series
      .filter((item) => item.type === "line")
      .map((item) => [item.__omniSeriesKey, item.color]),
  );
}

test("nullable number comparison keeps missing values stable and last", () => {
  assert.equal(compareNullableNumber(null, null), 0);
  assert.equal(compareNullableNumber(null, 1), 1);
  assert.equal(compareNullableNumber(1, null), -1);
  assert.equal(compareNullableNumber(1, 2, "asc"), -1);
  assert.equal(compareNullableNumber(1, 2, "desc"), 1);
});

test("key scenario selection covers long sequence, high throughput, and low latency", () => {
  const selected = selectDefaultVisibleSeriesKeys(
    [
      series("long", { max_concurrency: 8, random_input_len: 2500 }),
      series("high", { max_concurrency: 32, random_input_len: 100 }),
      series("low", { max_concurrency: 1, random_input_len: 100 }),
      series("missing-a", { random_input_len: 100 }),
      series("missing-b", { random_input_len: 100 }),
    ],
    3,
  );

  assert.deepEqual([...selected], ["long", "high", "low"]);
});

test("series colors stay stable between key scenarios and all series views", () => {
  const metricGroup = { metrics: ["mean_ttft_ms"] };
  const groupFields = ["scenario"];
  const records = [
    record("long", 8, 2500, 10),
    record("middle", 16, 100, 20),
    record("high", 32, 100, 30),
    record("low", 1, 100, 40),
  ];
  const allOption = buildOmniChartOption(metricGroup, records, groupFields, true);
  const visibleKeys = new Set([
    "mean_ttft_ms::long",
    "mean_ttft_ms::high",
    "mean_ttft_ms::low",
  ]);
  const keyOption = buildOmniChartOption(metricGroup, records, groupFields, true, visibleKeys);
  const allColors = colorBySeriesKey(allOption);
  const keyColors = colorBySeriesKey(keyOption);

  visibleKeys.forEach((key) => {
    assert.equal(keyColors[key], allColors[key]);
  });
});

test("framework comparison models only include comparable workloads", () => {
  const payload = {
    workload_options: [
      { model_family: "Qwen Image", comparable: true },
      { model_family: "WAN 2.2", comparable: false },
    ],
  };
  const records = [
    { model_family: "Qwen Image" },
    { model_family: "WAN 2.2" },
  ];

  assert.deepEqual(comparableModelFamilies(payload, records), ["Qwen Image"]);
});

test("framework comparison metric options require vLLM and SGLang values", () => {
  const payload = {
    baseline_framework: "vllm-omni",
    metric_options: [
      { value: "latency_mean_s", label: "Latency Mean" },
      { value: "mean_ttft_ms", label: "TTFT" },
    ],
  };
  const records = [
    { framework: "vllm-omni", latency_mean_s: 4.2, mean_ttft_ms: 10 },
    { framework: "sglang", latency_mean_s: 5.1 },
  ];

  assert.deepEqual(
    metricOptionsForRecords(payload, records).map((item) => item.value),
    ["latency_mean_s"],
  );
});

test("framework comparison metric toolbar keeps overflow collapsed", () => {
  const html = comparisonMetricToolbarHtml(
    [
      { value: "latency_mean_s", label: "Latency Mean" },
      { value: "latency_p50_s", label: "Latency P50" },
      { value: "latency_p99_s", label: "Latency P99" },
      { value: "throughput_qps", label: "Throughput" },
    ],
    "throughput_qps",
  );

  assert.match(html, /Latency Mean/);
  assert.match(html, /More metrics/);
  assert.match(html, /comparison-metric-more" open/);
  assert.equal((html.match(/data-comparison-metric=/g) || []).length, 4);
});

test("framework comparison chart ignores malformed single-day reference dates", () => {
  const option = buildMetricComparisonOption(
    { baseline_framework: "vllm-omni" },
    { metric: "latency_mean_s" },
    {
      vllm: [{ framework: "vllm-omni", sort_timestamp: "not-a-date", latency_mean_s: 4 }],
      sglang: [{ framework: "sglang", sort_timestamp: "not-a-date", latency_mean_s: 5 }],
    },
  );

  assert.equal(option.series.length, 2);
  assert.deepEqual(option.legend.data, ["vLLM-Omni", "SGLang"]);
});
