function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showToast(message, type = "info") {
  const container = document.getElementById("toasts");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-hide");
    setTimeout(() => toast.remove(), 250);
  }, 2400);
}

async function loadSessionOptions() {
  const select = document.getElementById("session_id");
  if (!select) return;

  try {
    const res = await fetch("/api/sessions");
    const sessions = await res.json();

    if (!res.ok || !Array.isArray(sessions)) {
      showToast("Could not load session list.", "error");
      return;
    }

    const previousValue = select.value;

    select.innerHTML = `<option value="">All sessions</option>`;

    sessions
      .slice()
      .sort((a, b) => Number(a.session_id) - Number(b.session_id))
      .forEach((session) => {
        const option = document.createElement("option");
        option.value = session.session_id;
        option.textContent = `Session #${session.session_id}`;
        select.appendChild(option);
      });

    const canRestore = [...select.options].some(
      (opt) => opt.value === previousValue
    );

    if (canRestore) {
      select.value = previousValue;
    }
  } catch (err) {
    console.error("Could not load session options:", err);
    showToast("Could not load session list.", "error");
  }
}

function renderEmptyState(message) {
  const container = document.getElementById("results-container");
  const header = document.getElementById("results-header");
  const meta = document.getElementById("results-meta");
  const queryLabel = document.getElementById("results-query-label");

  container.innerHTML = `
    <div class="result-item">
      <div class="result-title">${escapeHtml(message)}</div>
    </div>
  `;

  header.style.display = "none";
  meta.textContent = "";
  queryLabel.textContent = "";
}

function renderResults(data) {
  const container = document.getElementById("results-container");
  const header = document.getElementById("results-header");
  const meta = document.getElementById("results-meta");
  const queryLabel = document.getElementById("results-query-label");

  const results = Array.isArray(data.results) ? data.results : [];

  if (results.length === 0) {
    renderEmptyState("No results found.");
    return;
  }

  meta.textContent = `${results.length} result${results.length === 1 ? "" : "s"} found`;
  queryLabel.textContent = `Query: "${data.query || ""}"`;
  header.style.display = "flex";

  container.innerHTML = results.map((item) => {
    const url = escapeHtml(item.relevant_url || item.url || "");
    const origin = escapeHtml(item.origin_url || "-");
    const sessionId = escapeHtml(item.session_id ?? "-");
    const score = Number(item.score || 0);
    const percent = Math.max(0, Math.min(100, Math.round(score * 100)));

    return `
      <article class="result-item">
        <div class="result-title">
          <a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>
        </div>

        <div class="result-url">${url}</div>

        <div class="result-meta">
          <span><b>Origin:</b> ${origin}</span>
          <span><b>Session:</b> ${sessionId}</span>
          <span><b>Score:</b> ${score}</span>
        </div>

        <div class="score-bar">
          <div class="score-bar-track">
            <div class="score-bar-fill" style="width:${percent}%"></div>
          </div>
          <span class="score-bar-label">${percent}%</span>
        </div>
      </article>
    `;
  }).join("");
}

async function runSearch() {
  const queryInput = document.getElementById("query");
  const sessionSelect = document.getElementById("session_id");
  const limitInput = document.getElementById("limit");

  const query = queryInput.value.trim();
  const sessionId = sessionSelect.value;
  const limit = limitInput.value || "20";

  if (!query) {
    showToast("Please enter a search query.", "error");
    queryInput.focus();
    return;
  }

  const container = document.getElementById("results-container");
  const header = document.getElementById("results-header");
  const meta = document.getElementById("results-meta");
  const queryLabel = document.getElementById("results-query-label");

  header.style.display = "flex";
  meta.textContent = "Searching…";
  queryLabel.textContent = `Query: "${query}"`;
  container.innerHTML = `
    <div class="result-item">
      <div class="result-title">Searching index…</div>
    </div>
  `;

  try {
    let url = `/api/search?q=${encodeURIComponent(query)}&limit=${encodeURIComponent(limit)}`;

    if (sessionId) {
      url += `&session_id=${encodeURIComponent(sessionId)}`;
    }

    const res = await fetch(url);
    const data = await res.json();

    if (!res.ok) {
      renderEmptyState(data.error || "Search failed.");
      showToast(data.error || "Search failed.", "error");
      return;
    }

    renderResults(data);
  } catch (err) {
    console.error("Search failed:", err);
    renderEmptyState("Search failed.");
    showToast("Search failed.", "error");
  }
}

function clearResults() {
  document.getElementById("query").value = "";
  document.getElementById("session_id").value = "";
  document.getElementById("limit").value = "20";

  const container = document.getElementById("results-container");
  const header = document.getElementById("results-header");
  const meta = document.getElementById("results-meta");
  const queryLabel = document.getElementById("results-query-label");

  container.innerHTML = "";
  header.style.display = "none";
  meta.textContent = "";
  queryLabel.textContent = "";
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadSessionOptions();

  const queryInput = document.getElementById("query");
  queryInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      runSearch();
    }
  });
});