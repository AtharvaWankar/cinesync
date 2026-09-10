/* ── Stats for Nerds ──────────────────────────────────────────────────
 * Pulls real file/codec info from /api/media_info (ffprobe on the
 * server) and combines it with live numbers read straight off the
 * <video> element and the Performance/Network APIs in the browser.
 * Only runs while the panel is open, to avoid wasting cycles.
 * ──────────────────────────────────────────────────────────────────── */

let statsOpen        = false;
let statsInterval     = null;
let mediaInfoCache    = null;
let statsLoadStart    = null;   // performance.now() when <video> started loading
let statsTimeToStart  = null;   // ms from loadstart -> first playing
let statsRebufferCount = 0;
let statsWasWaiting   = false;
let statsFrameCount   = 0;
let statsMeasuredFps  = null;
let statsRvfcHandle   = null;
let statsLastBytes    = 0;
let statsLastByteTime = null;
let statsThroughputMbps = null;
let statsPeakThroughputMbps = 0;

// ── Wire up lifecycle listeners once, immediately ───────────────────────

video.addEventListener("loadstart", () => {
  statsLoadStart   = performance.now();
  statsTimeToStart = null;
});

video.addEventListener("playing", () => {
  if (statsTimeToStart === null && statsLoadStart !== null) {
    statsTimeToStart = Math.round(performance.now() - statsLoadStart);
  }
});

video.addEventListener("waiting", () => {
  if (!statsWasWaiting) {
    statsRebufferCount++;
    statsWasWaiting = true;
  }
});
video.addEventListener("playing", () => { statsWasWaiting = false; });
video.addEventListener("canplay", () => { statsWasWaiting = false; });

// requestVideoFrameCallback gives a real "frames actually rendered per second"
// count. Falls back gracefully to "N/A" on browsers without it (e.g. old Safari/Firefox).
function startFrameCounter() {
  if (!("requestVideoFrameCallback" in HTMLVideoElement.prototype)) return;
  let windowStart = performance.now();
  let count = 0;
  const tick = () => {
    count++;
    const now = performance.now();
    if (now - windowStart >= 1000) {
      statsMeasuredFps = Math.round((count * 1000) / (now - windowStart));
      count = 0;
      windowStart = now;
    }
    statsRvfcHandle = video.requestVideoFrameCallback(tick);
  };
  statsRvfcHandle = video.requestVideoFrameCallback(tick);
}

function stopFrameCounter() {
  if (statsRvfcHandle !== null && "cancelVideoFrameCallback" in video) {
    try { video.cancelVideoFrameCallback(statsRvfcHandle); } catch (e) {}
  }
  statsRvfcHandle = null;
}

// ── Throughput, estimated from bytes actually transferred for /video ────

function updateThroughput() {
  const entries = performance.getEntriesByType("resource")
    .filter(e => e.name.includes("/video"));
  if (!entries.length) return;

  const totalBytes = entries.reduce((sum, e) => sum + (e.transferSize || 0), 0);
  const now = performance.now();

  if (statsLastByteTime !== null) {
    const deltaBytes = totalBytes - statsLastBytes;
    const deltaSec   = (now - statsLastByteTime) / 1000;
    if (deltaSec > 0 && deltaBytes >= 0) {
      const mbps = (deltaBytes * 8) / deltaSec / 1_000_000;
      statsThroughputMbps = mbps;
      if (mbps > statsPeakThroughputMbps) statsPeakThroughputMbps = mbps;
    }
  }
  statsLastBytes    = totalBytes;
  statsLastByteTime = now;
}

// ── Ping ──────────────────────────────────────────────────────────────

let statsLastPingMs = null;

async function measurePing() {
  const start = performance.now();
  try {
    await fetch(`/api/ping?t=${start}`, { cache: "no-store" });
    statsLastPingMs = Math.round(performance.now() - start);
  } catch (e) {
    statsLastPingMs = null;
  }
}

// ── Formatting helpers ───────────────────────────────────────────────

function fmtBytes(b) {
  if (!b && b !== 0) return "—";
  const mb = b / (1024 * 1024);
  if (mb > 1024) return (mb / 1024).toFixed(2) + " GB";
  return mb.toFixed(1) + " MB";
}
function fmtMbps(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return v.toFixed(2) + " Mbps";
}
function fmtSec(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return v.toFixed(1) + "s";
}
function row(label, value) {
  return `<div class="stats-row"><span class="stats-label">${label}</span><span class="stats-value">${value ?? "—"}</span></div>`;
}
function section(title) {
  return `<div class="stats-section-title">${title}</div>`;
}

// ── Main render ───────────────────────────────────────────────────────

function connectionType() {
  const c = navigator.connection || navigator.webkitConnection || navigator.mozConnection;
  if (!c) return "Unknown";
  if (c.type && c.type !== "unknown") return c.type;
  if (c.effectiveType) return c.effectiveType.toUpperCase();
  return "Unknown";
}

function renderStats() {
  const body = document.getElementById("stats-panel-body");
  if (!body) return;

  updateThroughput();

  const mi = mediaInfoCache;
  const v  = mi && mi.video;
  const a  = (mi && mi.audio && mi.audio[0]) || null;

  const quality = (video.getVideoPlaybackQuality && video.getVideoPlaybackQuality()) || null;
  const buffered = video.buffered;
  let bufferAheadSec = null, bufferTotalSec = 0;
  if (buffered && buffered.length) {
    for (let i = 0; i < buffered.length; i++) {
      bufferTotalSec += (buffered.end(i) - buffered.start(i));
      if (video.currentTime >= buffered.start(i) && video.currentTime <= buffered.end(i)) {
        bufferAheadSec = buffered.end(i) - video.currentTime;
      }
    }
  }

  let html = "";

  // ── Playback ──
  html += section("🎞️ Playback");
  html += row("Movie / Episode", mi ? mi.movie_name : "—");
  html += row("Container resolution", v ? v.resolution : "—");
  html += row("Actual render resolution", `${video.videoWidth || "—"}×${video.videoHeight || "—"}`);
  html += row("Source FPS", v ? v.fps : "—");
  html += row("Rendered FPS (measured)", statsMeasuredFps !== null ? statsMeasuredFps : ("requestVideoFrameCallback" in HTMLVideoElement.prototype ? "measuring…" : "N/A (unsupported by browser)"));
  html += row("Video codec", v ? v.codec : "—");
  html += row("HDR", v ? v.hdr : "—");
  html += row("Color space", v ? (v.color_space || "Unknown") : "—");
  html += row("Bit depth", v ? (v.bit_depth || "Unknown") : "—");
  html += row("Chroma subsampling", v ? (v.chroma_subsampling || "Unknown") : "—");
  html += row("Container", mi ? (mi.container || "—") : "—");
  html += row("Average bitrate (source file)", mi ? (mi.overall_bitrate || "—") : "—");
  html += row("Video stream bitrate (source)", v ? (v.bitrate || "—") : "—");
  html += row("Dropped frames", quality ? `${quality.droppedVideoFrames} / ${quality.totalVideoFrames}` : "N/A");

  // ── Audio ──
  html += section("🔊 Audio");
  html += row("Audio codec", a ? a.codec : "—");
  html += row("Channels", a ? (a.channel_layout || a.channels || "—") : "—");
  html += row("Sample rate", a ? (a.sample_rate || "—") : "—");
  html += row("Bit depth", a ? (a.bit_depth || "Unknown") : "—");
  html += row("Audio bitrate (source)", a ? (a.bitrate || "—") : "—");
  html += row("Current track / language", a ? (a.language ? a.language.toUpperCase() : (a.title || "Default")) : "—");
  html += row("Dolby Atmos", a ? (a.atmos ? "Yes" : "No") : "—");
  html += row("Passthrough", "No (browser-decoded)");

  // ── Network ──
  html += section("📡 Network");
  html += row("Connection type", connectionType());
  html += row("Server", window.location.host);
  html += row("CDN", "None (direct LAN / Tailscale stream)");
  html += row("Ping / latency", statsLastPingMs !== null ? `${statsLastPingMs} ms` : "measuring…");
  html += row("Current throughput", fmtMbps(statsThroughputMbps));
  html += row("Peak throughput (session)", fmtMbps(statsPeakThroughputMbps));
  html += row("Buffer ahead", bufferAheadSec !== null ? fmtSec(bufferAheadSec) : "0.0s");
  html += row("Total buffered", fmtSec(bufferTotalSec));
  html += row("Rebuffer count (session)", statsRebufferCount);
  html += row("Time to start", statsTimeToStart !== null ? `${statsTimeToStart} ms` : "—");
  html += row("Total data transferred", fmtBytes(
    performance.getEntriesByType("resource")
      .filter(e => e.name.includes("/video"))
      .reduce((s, e) => s + (e.transferSize || 0), 0)
  ));
  html += row("Packets dropped", "N/A (not exposed by browsers)");

  if (mi && mi.error) {
    html += `<div class="stats-warning">⚠️ ${mi.error}<br/><span class="stats-recheck" onclick="recheckMediaInfo()">↻ Recheck now</span></div>`;
  }

  body.innerHTML = html;
}

// ── Panel open/close ─────────────────────────────────────────────────

async function fetchMediaInfo() {
  try {
    const res = await fetch("/api/media_info");
    mediaInfoCache = await res.json();
  } catch (e) {
    mediaInfoCache = { error: "Could not reach server for media info." };
  }
}

async function recheckMediaInfo() {
  try {
    const res = await fetch("/api/media_info/recheck");
    mediaInfoCache = await res.json();
  } catch (e) {
    mediaInfoCache = { error: "Could not reach server for media info." };
  }
  renderStats();
}

function toggleStatsPanel() {
  const panel = document.getElementById("stats-panel");
  if (!panel) return;

  statsOpen = !statsOpen;
  panel.style.display = statsOpen ? "flex" : "none";

  if (statsOpen) {
    fetchMediaInfo().then(renderStats);
    measurePing();
    startFrameCounter();
    renderStats();
    statsInterval = setInterval(() => {
      renderStats();
      measurePing();
    }, 1000);
  } else {
    stopFrameCounter();
    if (statsInterval) clearInterval(statsInterval);
    statsInterval = null;
  }
}
