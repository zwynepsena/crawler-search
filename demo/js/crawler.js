"use strict";

function showToast(message, type = "info") {
  const container = document.getElementById("toasts");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}

function getFloat(id) {
  return parseFloat(document.getElementById(id).value);
}

function getInt(id) {
  return parseInt(document.getElementById(id).value, 10);
}

function getString(id) {
  return document.getElementById(id).value.trim();
}

function resetForm() {
  document.getElementById("origin_url").value = "";
  document.getElementById("max_depth").value = "2";
  document.getElementById("max_urls").value = "200";
  document.getElementById("queue_capacity").value = "100";
  document.getElementById("num_workers").value = "4";
  document.getElementById("requests_per_sec").value = "2";
  document.getElementById("result-panel").style.display = "none";
  document.getElementById("origin_url").focus();
}

function setStartButtonLoading(isLoading) {
  const btn = document.getElementById("btn-start");
  const icon = document.getElementById("btn-start-icon");
  const text = document.getElementById("btn-start-text");

  btn.disabled = isLoading;

  if (isLoading) {
    icon.className = "spinner";
    icon.textContent = "";
    if (text) text.textContent = "Starting...";
  } else {
    icon.className = "";
    icon.textContent = "▶";
    if (text) text.textContent = "Start Crawl";
  }
}

async function startSession() {
  const originUrl = getString("origin_url");

  if (!originUrl) {
    showToast("Origin URL is required.", "error");
    document.getElementById("origin_url").focus();
    return;
  }

  try {
    const parsed = new URL(originUrl);
    if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
  } catch {
    showToast("Enter a valid http:// or https:// URL.", "error");
    return;
  }

  const payload = {
    origin_url: originUrl,
    max_depth: getInt("max_depth"),
    max_urls: getInt("max_urls"),
    queue_capacity: getInt("queue_capacity"),
    num_workers: getInt("num_workers"),
    requests_per_sec: getFloat("requests_per_sec"),
  };

  if (isNaN(payload.max_depth) || payload.max_depth < 0) {
    showToast("Max depth must be >= 0.", "error");
    return;
  }

  if (isNaN(payload.max_urls) || payload.max_urls < 1) {
    showToast("Max URLs must be >= 1.", "error");
    return;
  }

  if (isNaN(payload.queue_capacity) || payload.queue_capacity < 1) {
    showToast("Queue capacity must be >= 1.", "error");
    return;
  }

  if (isNaN(payload.num_workers) || payload.num_workers < 1) {
    showToast("Workers must be >= 1.", "error");
    return;
  }

  if (isNaN(payload.requests_per_sec) || payload.requests_per_sec <= 0) {
    showToast("Requests/sec must be > 0.", "error");
    return;
  }

  setStartButtonLoading(true);

  try {
    const resp = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await resp.json();

    if (!resp.ok) {
      showToast(data.error || "Failed to start session.", "error");
      return;
    }

    showToast(`Session #${data.session_id} started.`, "success");
    showResult(data);

    if (typeof loadStats === "function") loadStats();
    if (typeof loadRecent === "function") loadRecent();
  } catch (err) {
    showToast("Network error — is the Flask server running?", "error");
  } finally {
    setStartButtonLoading(false);
  }
}

function showResult(session) {
  const panel = document.getElementById("result-panel");
  const content = document.getElementById("result-content");

  content.innerHTML = `
    <div class="stat-grid">
      <div class="stat-box">
        <div class="stat-label">Session ID</div>
        <div class="stat-value accent">#${session.session_id}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">Status</div>
        <div class="stat-value"><span class="badge badge-running">running</span></div>
      </div>
      <div class="stat-box">
        <div class="stat-label">Max Depth</div>
        <div class="stat-value">${session.max_depth}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">Max URLs</div>
        <div class="stat-value">${session.max_urls}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">Workers</div>
        <div class="stat-value">${session.active_workers ?? "—"}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">Queue Cap</div>
        <div class="stat-value">${session.queue_capacity}</div>
      </div>
    </div>
    <p class="text-mono text-sm text-muted mt-1">
      Origin: <span style="color:var(--accent)">${escHtml(session.origin_url)}</span>
    </p>
  `;

  panel.style.display = "block";
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.tagName === "INPUT") {
    startSession();
  }
});