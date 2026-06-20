(function () {
  const page = document.querySelector(".test-reports-page");
  if (!page) {
    return;
  }

  const manifestSrc = page.dataset.testReportsManifest;
  const typeTabs = page.querySelector("[data-test-reports-type-tabs]");
  const dateSelect = page.querySelector("[data-test-report-date]");
  const frame = page.querySelector("[data-test-reports-frame]");
  const emptyState = page.querySelector("[data-test-reports-empty]");
  const statusEl = page.querySelector("[data-test-reports-status]");

  /** @type {{ nightly: string[], release: string[] } | null} */
  let manifest = null;
  let activeType = "nightly";
  let manifestBaseUrl = "";

  function resolveAssetUrl(relativePath) {
    return new URL(relativePath, window.location.href).href;
  }

  function reportAssetPath(type, date) {
    return `${manifestBaseUrl}${type}/${date}.html`;
  }

  function datesForType(type) {
    if (!manifest) {
      return [];
    }
    return manifest[type] || [];
  }

  function setStatus(message) {
    if (!statusEl) {
      return;
    }
    if (!message) {
      statusEl.hidden = true;
      statusEl.textContent = "";
      return;
    }
    statusEl.hidden = false;
    statusEl.textContent = message;
  }

  function syncTypeCardState() {
    if (!typeTabs) {
      return;
    }
    typeTabs.querySelectorAll("[data-test-report-type]").forEach((btn) => {
      const isActive = btn.dataset.testReportType === activeType;
      btn.classList.toggle("is-active", isActive);
      btn.setAttribute("aria-selected", isActive ? "true" : "false");
    });
  }

  function populateDateSelect() {
    if (!dateSelect) {
      return;
    }
    const dates = datesForType(activeType);
    dateSelect.innerHTML = "";
    dates.forEach((date) => {
      const option = document.createElement("option");
      option.value = date;
      option.textContent = date;
      dateSelect.appendChild(option);
    });
    dateSelect.disabled = dates.length === 0;
  }

  function showReport(date) {
    if (!frame || !emptyState) {
      return;
    }
    const dates = datesForType(activeType);
    if (!dates.length || !date) {
      frame.hidden = true;
      frame.removeAttribute("src");
      emptyState.hidden = false;
      setStatus(`No ${activeType} reports archived yet.`);
      return;
    }
    emptyState.hidden = true;
    frame.hidden = false;
    frame.src = reportAssetPath(activeType, date);
    setStatus("");
  }

  function pickDefaultDate() {
    const dates = datesForType(activeType);
    return dates[0] || "";
  }

  function refreshView() {
    syncTypeCardState();
    populateDateSelect();
    const date = dateSelect?.value || pickDefaultDate();
    if (dateSelect && date) {
      dateSelect.value = date;
    }
    showReport(date);
  }

  async function init() {
    if (!manifestSrc) {
      setStatus("Report manifest path is missing.");
      return;
    }
    try {
      const manifestUrl = resolveAssetUrl(manifestSrc);
      manifestBaseUrl = manifestUrl.replace(/manifest\.json$/, "");
      const response = await fetch(manifestUrl);
      if (!response.ok) {
        throw new Error(`failed to load ${manifestUrl}`);
      }
      manifest = await response.json();
    } catch (error) {
      setStatus(`Could not load report index: ${error.message}`);
      if (emptyState) {
        emptyState.hidden = false;
      }
      if (frame) {
        frame.hidden = true;
      }
      return;
    }

    if (typeTabs) {
      typeTabs.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-test-report-type]");
        if (!btn || !typeTabs.contains(btn)) {
          return;
        }
        const nextType = btn.dataset.testReportType;
        if (!nextType || nextType === activeType) {
          return;
        }
        activeType = nextType;
        refreshView();
      });
    }

    dateSelect?.addEventListener("change", () => {
      showReport(dateSelect.value);
    });

    refreshView();
  }

  init();
})();
