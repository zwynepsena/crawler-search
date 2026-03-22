"use strict";

let autoRefreshTimer = null;

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function badgeClass(status) {
  return {
    running: "badge-running",
    stopping: "badge-stopping",
    paused: "badge-paused",
    completed: "badge-done",
    done: "badge-done",
    error: "badge-error",
  }[status] || "badge-done";
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${Math.round(Number(value) * 100)}%`;
}

function formatHitRate(s) {
  if (!s || Number(s.urls_seen || 0) <= 0) return "—";
  return `${(Number(s.hit_rate || 0) * 100).toFixed(1)}%`;
}

function renderSessionRow(s) {
  const status = s.status || "unknown";
  const queuePct = Math.round(Number(s.queue_utilization || 0) * 100);

  return `
    <div class="session-row">
      <div class="session-row-left">
        <div class="session-row-url">
          <span class="session-row-id">#${escapeHtml(s.session_id)}</span>
          ${escapeHtml(s.origin_url || "—")}
        </div>
        <div class="session-row-meta">
          <span>indexed <b>${escapeHtml(s.pages_indexed ?? 0)}</b></span>
          <span>seen <b>${escapeHtml(s.urls_seen ?? 0)}</b></span>
          <span>skipped <b>${escapeHtml(s.urls_skipped ?? 0)}</b></span>
          <span>depth <b>${escapeHtml(s.max_depth ?? 0)}</b></span>
          <span>workers <b>${escapeHtml(s.active_workers ?? 0)}</b></span>
          <span>queue <b>${queuePct}%</b></span>
          <span>hit rate <b>${escapeHtml(formatHitRate(s))}</b></span>
        </div>
      </div>

      <div class="session-row-right">
        <span class="status-badge ${badgeClass(status)}">${escapeHtml(status)}</span>
        <a class="btn btn-primary btn-sm" href="/status/${encodeURIComponent(s.session_id)}">
          Details
        </a>
      </div>
    </div>
  `;
}

function populateStrip(sessions) {
  const running = sessions.filter(s => s.status === "running").length;
  const paused = sessions.filter(s => s.status === "paused").length;
  const stopping = sessions.filter(s => s.status === "stopping").length;
  const completed = sessions.filter(s => s.status === "completed" || s.status === "done").length;
  const error = sessions.filter(s => s.status === "error").length;

  const active = sessions.reduce((a, s) => a + Number(s.active_workers || 0), 0);
  const pages = sessions.reduce((a, s) => a + Number(s.pages_indexed || 0), 0);
  const urls = sessions.reduce((a, s) => a + Number(s.urls_seen || 0), 0);
  const skipped = sessions.reduce((a, s) => a + Number(s.urls_skipped || 0), 0);
  const workers = sessions.reduce((a, s) => a + Number(s.num_workers || 0), 0);

  const avgHitRate = sessions.length
    ? sessions.reduce((a, s) => a + Number(s.hit_rate || 0), 0) / sessions.length
    : 0;

  const avgQueueUtil = sessions.length
    ? sessions.reduce((a, s) => a + Number(s.queue_utilization || 0), 0) / sessions.length
    : 0;

  let pressureLabel = "normal";
  if (sessions.some(s => s.back_pressure_status === "full")) {
    pressureLabel = "full";
  } else if (sessions.some(s => s.back_pressure_status === "high")) {
    pressureLabel = "high";
  } else if (sessions.some(s => s.back_pressure_status === "moderate")) {
    pressureLabel = "moderate";
  }

  setText("pill-running", running);
  setText("pill-paused", paused);
  setText("pill-stopping", stopping);
  setText("pill-completed", completed);
  setText("pill-error", error);

  setText("st-total", sessions.length);
  setText("st-active", active);
  setText("st-pages", pages);
  setText("st-urls", urls);
  setText("st-skipped", skipped);
  setText("st-hitrate", sessions.length ? `${(avgHitRate * 100).toFixed(1)}%` : "—");
  setText("st-words", "—");
  setText("st-workers", workers);
  setText("st-queue-util", sessions.length ? `${Math.round(avgQueueUtil * 100)}%` : "—");
  setText("st-pressure", pressureLabel);
  setText("session-count", `${sessions.length} session${sessions.length === 1 ? "" : "s"}`);
  setText("last-updated", `Updated ${new Date().toLocaleTimeString()}`);
}

function renderSessions(sessions) {
  const container = document.getElementById("sessions-container");
  if (!container) return;

  if (!sessions || sessions.length === 0) {
    container.innerHTML = `<div class="empty-state">No sessions found.</div>`;
    return;
  }

  container.innerHTML = `<div class="session-list">${sessions.map(renderSessionRow).join("")}</div>`;
}

async function loadSessions() {
  try {
    const res = await fetch("/api/sessions");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const sessions = await res.json();
    populateStrip(sessions);
    renderSessions(sessions);
  } catch (err) {
    console.error("Failed to load sessions:", err);
    const container = document.getElementById("sessions-container");
    if (container) {
      container.innerHTML = `<div class="empty-state">Could not load sessions.</div>`;
    }
  }
}

function goToDetail() {
  const input = document.getElementById("lookup-input");
  const value = (input?.value || "").trim();
  if (!value) return;
  window.location.href = `/status/${value}`;
}

function clearLookup() {
  const input = document.getElementById("lookup-input");
  if (input) input.value = "";
}

function toggleAutoRefresh(enabled) {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
  if (enabled) {
    autoRefreshTimer = setInterval(loadSessions, 2000);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadSessions();
  const checkbox = document.getElementById("auto-refresh");
  toggleAutoRefresh(checkbox ? checkbox.checked : true);
});