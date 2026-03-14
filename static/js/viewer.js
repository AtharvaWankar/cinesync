/**
 * viewer.js — Viewer watch page logic
 * Receives sync events from host and keeps the video in lockstep.
 */

const video    = document.getElementById("viewer-video");
const overlay  = document.getElementById("sync-overlay");
let viewerName = "";
let isSyncing  = false;

// ── Tolerance: if we're within this many seconds, don't re-seek ───────
const SYNC_TOLERANCE = 1.5; // seconds

// ── Join party ─────────────────────────────────────────────────────────

function joinParty() {
  const input = document.getElementById("viewer-name-input");
  const name  = input.value.trim();
  if (!name) { input.placeholder = "Please enter your name!"; return; }

  viewerName = name;
  socket.emit("viewer_join", { name });

  // Show main UI
  document.getElementById("name-overlay").style.display  = "none";
  document.getElementById("watch-container").style.display = "grid";
}

// ── Sync helpers ───────────────────────────────────────────────────────

function showSyncOverlay() {
  overlay.style.display = "flex";
  isSyncing = true;
}

function hideSyncOverlay() {
  overlay.style.display = "none";
  isSyncing = false;
}

function seekIfNeeded(ts) {
  if (Math.abs(video.currentTime - ts) > SYNC_TOLERANCE) {
    video.currentTime = ts;
  }
}

// ── Socket: initial state when joining mid-movie ───────────────────────

socket.on("sync_state", (data) => {
  video.currentTime = data.timestamp;
  if (data.is_playing) {
    video.play().catch(() => {
      // Browser blocked autoplay — user hasn't interacted yet
      // The name-overlay click should have unlocked it, but just in case:
      showSyncOverlay();
    });
  }
});

// ── Socket: host pressed Play ──────────────────────────────────────────

socket.on("sync_play", (data) => {
  seekIfNeeded(data.timestamp);
  video.play().then(() => {
    hideSyncOverlay();
  }).catch(() => {
    showSyncOverlay();
  });
});

// ── Socket: host pressed Pause ────────────────────────────────────────

socket.on("sync_pause", (data) => {
  video.pause();
  seekIfNeeded(data.timestamp);
  hideSyncOverlay();
});

// ── Socket: host seeked ────────────────────────────────────────────────

socket.on("sync_seek", (data) => {
  showSyncOverlay();
  video.currentTime = data.timestamp;
});

// ── Socket: viewer list updated ────────────────────────────────────────

socket.on("viewer_update", (data) => {
  document.getElementById("viewer-count-badge").textContent =
    `${data.count} watching`;

  const list = document.getElementById("viewer-list");
  list.innerHTML = data.viewers.map(n =>
    `<div class="viewer-item">${escHtml(n)}</div>`
  ).join("");
});

// ── Socket: chat ───────────────────────────────────────────────────────

socket.on("chat_message", (data) => {
  appendChat(data.name, data.text);
});

// ── Video events ───────────────────────────────────────────────────────

video.addEventListener("waiting", () => {
  // Browser is buffering — show overlay
  showSyncOverlay();
});

video.addEventListener("playing", () => {
  hideSyncOverlay();
});

video.addEventListener("canplay", () => {
  if (!isSyncing) hideSyncOverlay();
});

// ── Chat ───────────────────────────────────────────────────────────────

function sendChat() {
  const input = document.getElementById("chat-input");
  const text  = input.value.trim();
  if (!text || !viewerName) return;
  socket.emit("chat_message", { name: viewerName, text });
  input.value = "";
}

function appendChat(name, text) {
  const box = document.getElementById("chat-messages");
  const msg = document.createElement("div");
  msg.className = "chat-msg";
  msg.innerHTML = `<span class="sender">${escHtml(name)}</span><span class="text">${escHtml(text)}</span>`;
  box.appendChild(msg);
  box.scrollTop = box.scrollHeight;
}

function escHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ── Heartbeat ──────────────────────────────────────────────────────────
// Lets the server know this viewer is still alive every 30s

setInterval(() => {
  socket.emit("ping_alive");
}, 30000);
