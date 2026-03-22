"use strict";

let autoRefreshTimer = null;
let sessionId = null;

// Keep last known session detail so queue UI can stay consistent
let lastSessionDetail = null;

document.addEventListener("DOMContentLoaded", () => {
  const parts = window.location.pathname.split("/").filter(Boolean);
  sessionId = parseInt(parts[parts.length - 1], 10);

  if (!sessionId || Number.isNaN(sessionId)) {
    showError("Invalid session ID in URL.");
    return;
  }

  loadAll();
  startAutoRefresh();
});

function startAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  autoRefreshTimer = setInterval(loadAll, 4000);
}

function stopAutoRefresh() {
  clearInterval(autoRefreshTimer);
  autoRefreshTimer = null;
}

async function loadAll() {
  await loadDetail();
  await Promise.all([loadQueue(), loadLog()]);
}

// ── Detail ────────────────────────────────────────────────

async function loadDetail() {
  const icon = document.getElementById("refresh-icon");
  if (icon) {
    icon.className = "spinner";
    icon.textContent = "";
  }

  try {
    const resp = await fetch(`/api/sessions/${sessionId}`);
    if (resp.status === 404) {
      showError(`Session #${sessionId} not found.`);
      stopAutoRefresh();
      return;
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const s = await resp.json();
    lastSessionDetail = s;

    populateHero(s);
    populateStats(s);
    populateProgress(s);
    populateTimestamps(s);
    populateActions();

    if (s.status === "done" || s.status === "error") {
      stopAutoRefresh();
    }
  } catch {
    showToast("Could not load session.", "error");
  } finally {
    const refreshIcon = document.getElementById("refresh-icon");
    if (refreshIcon) {
      refreshIcon.className = "";
      refreshIcon.textContent = "↻";
    }
  }
}

function populateHero(s) {
  setText("back-title", `Session #${s.session_id}`);
  setText("hero-session-id", `Session #${s.session_id}`);
  setText("hero-session-url", s.origin_url);
  document.title = `MiniCrawler — Session #${s.session_id}`;
}

function populateStats(s) {
  const hitPct = s.urls_seen > 0
    ? (s.hit_rate * 100).toFixed(1) + "%"
    : "—";

  setText("cfg-status", s.status);
  setText("cfg-depth", s.max_depth);
  setText("cfg-maxurls", s.max_urls);
  setText("cfg-workers", s.active_workers);
  setText("cfg-qcap", s.queue_capacity);
  setText("cfg-hitrate", hitPct);

  const statusEl = document.getElementById("cfg-status");
  if (statusEl) {
    statusEl.className = "config-value";
    const col = {
      running: "green",
      stopping: "amber",
      stopped: "amber",
      paused: "amber",
      error: "red",
    }[s.status];
    if (col) statusEl.classList.add(col);
  }

  setText("stat-pages", s.pages_indexed);
  setText("stat-urls", s.urls_seen);
  setText("stat-skipped", s.urls_skipped);
  setText("stat-workers", s.active_workers);
  setText("stat-qdepth", s.queue_depth ?? 0);
  setText("stat-qcap", s.queue_capacity ?? 0);
}

function populateProgress(s) {
  const urlsSeen = Number(s.urls_seen || 0);
  const maxUrls = Number(s.max_urls || 0);
  const queueDepth = Number(s.queue_depth || 0);
  const queueCapacity = Number(s.queue_capacity || 0);

  const urlsPct = maxUrls > 0
    ? Math.min(100, Math.round((urlsSeen / maxUrls) * 100))
    : 0;

  setText("prog-urls-val", `${urlsSeen} / ${maxUrls}`);
  setText("prog-urls-pct", `${urlsPct}%`);
  setBar("prog-urls-fill", urlsPct, barColor(urlsPct));

  const qPct = queueCapacity > 0
    ? Math.min(100, Math.round((queueDepth / queueCapacity) * 100))
    : 0;

  setText("prog-queue-val", `${queueDepth} / ${queueCapacity}`);
  setText("prog-queue-pct", `${qPct}%`);
  setBar("prog-queue-fill", qPct, barColor(qPct));
}

function updateQueueMetricsFromCount(queueCount) {
  const qdepth = Number(queueCount || 0);
  const qcap = Number(lastSessionDetail?.queue_capacity || 0);

  setText("stat-qdepth", qdepth);

  const qPct = qcap > 0
    ? Math.min(100, Math.round((qdepth / qcap) * 100))
    : 0;

  setText("prog-queue-val", `${qdepth} / ${qcap}`);
  setText("prog-queue-pct", `${qPct}%`);
  setBar("prog-queue-fill", qPct, barColor(qPct));
}

function barColor(pct) {
  if (pct > 80) return "var(--red)";
  if (pct > 50) return "var(--amber)";
  return "var(--purple-mid)";
}

function populateTimestamps(s) {
  setText("ts-created", s.created_at ? fmtDatetime(s.created_at) : "—");
  setText("ts-updated", s.updated_at ? fmtDatetime(s.updated_at) : "—");
}

function populateActions() {
  const area = document.getElementById("hero-actions");
  if (!area) return;

  area.innerHTML = `
    <button class="btn btn-ghost btn-sm" onclick="loadAll()">
      <span id="refresh-icon">↻</span> Refresh
    </button>
  `;
}

// ── Queue ─────────────────────────────────────────────────

async function loadQueue() {
  const container = document.getElementById("queue-container");
  const countEl = document.getElementById("queue-count");
  if (!container) return;

  try {
    const resp = await fetch(`/api/sessions/${sessionId}/queue?limit=50`);
    if (!resp.ok) throw new Error();

    const data = await resp.json();
    const items = Array.isArray(data.items) ? data.items : [];
    const totalCount = Number.isFinite(data.count) ? data.count : items.length;

    updateQueueMetricsFromCount(totalCount);

    if (items.length === 0) {
      if (countEl) countEl.textContent = "0 items pending";
      container.innerHTML = `
        <div class="empty-state" style="padding:1.5rem 0">
          Queue is empty.
        </div>`;
      return;
    }

    if (countEl) {
      countEl.textContent = `${totalCount} item${totalCount !== 1 ? "s" : ""} pending`;
    }

    const html = items.map((item) => `
      <div class="queue-item">
        <span class="queue-item-depth">D${item.depth}</span>
        <span class="queue-item-url" title="${esc(item.url)}">
          ${esc(item.url)}
        </span>
      </div>
    `).join("");

    container.innerHTML = `<div class="queue-list">${html}</div>`;
  } catch {
    container.innerHTML = `
      <div class="empty-state" style="padding:1.5rem 0">
        Could not load queue data.
      </div>`;
  }
}

// ── Log ───────────────────────────────────────────────────

async function loadLog() {
  const container = document.getElementById("log-container");
  const countEl = document.getElementById("log-count");
  if (!container) return;

  try {
    const resp = await fetch(`/api/sessions/${sessionId}/pages?limit=50`);
    if (!resp.ok) throw new Error();

    const data = await resp.json();
    const pages = Array.isArray(data.pages) ? data.pages : [];
    const totalCount = Number.isFinite(data.count) ? data.count : pages.length;

    if (pages.length === 0) {
      if (countEl) countEl.textContent = "";
      container.innerHTML = `
        <div class="empty-state" style="padding:1.5rem 0">
          No pages indexed yet.
        </div>`;
      return;
    }

    if (countEl) {
      countEl.textContent = `${totalCount} page${totalCount !== 1 ? "s" : ""} indexed`;
    }

    const html = pages.map((p) => `
      <div class="log-item">
        <div class="log-item-top">
          <a href="${escAttr(p.url)}" target="_blank" rel="noopener noreferrer"
             class="log-item-url" title="${esc(p.url)}">
            ${esc(p.url)}
          </a>
          <span class="log-item-depth">D${p.depth ?? "—"}</span>
        </div>
      </div>
    `).join("");

    container.innerHTML = `<div class="log-list">${html}</div>`;
  } catch {
    container.innerHTML = `
      <div class="empty-state" style="padding:1.5rem 0">
        Could not load indexed pages.
      </div>`;
  }
}

// ── Helpers ───────────────────────────────────────────────

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setBar(id, pct, color) {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.width = `${pct}%`;
  el.style.background = color;
}

function showToast(message, type = "info") {
  const container = document.getElementById("toasts");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => toast.remove(), 3500);
}

function showError(message) {
  const banner = document.getElementById("error-banner");
  if (!banner) return;
  banner.textContent = message;
  banner.style.display = "block";
}

function fmtDatetime(value) {
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return value ?? "—";
  }
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escAttr(str) {
  return esc(str).replace(/'/g, "&#39;");
}