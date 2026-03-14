const video   = document.getElementById("viewer-video");
const overlay = document.getElementById("sync-overlay");
const vTimeline    = document.getElementById("v-timeline");
const vCurrentTime = document.getElementById("v-current-time");
const vTotalTime   = document.getElementById("v-total-time");

let viewerName  = "";
let isDragging  = false;
let isSyncing   = false;
const SYNC_TOLERANCE = 1.5;

// ── Join party ─────────────────────────────────────────────────────────

function joinParty() {
  const input = document.getElementById("viewer-name-input");
  const name  = input.value.trim();
  if (!name) { input.placeholder = "Please enter your name!"; return; }

  viewerName = name;
  socket.emit("viewer_join", { name });

  document.getElementById("name-overlay").style.display   = "none";
  document.getElementById("watch-container").style.display = "grid";
}

// ── Utilities ──────────────────────────────────────────────────────────

function formatTime(secs) {
  const s = Math.floor(secs);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
  return `${m}:${String(sec).padStart(2,"0")}`;
}

function escHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ── Video metadata loaded ──────────────────────────────────────────────

video.addEventListener("loadedmetadata", () => {
  vTimeline.max = Math.floor(video.duration);
  vTotalTime.textContent = formatTime(video.duration);
});

// ── Timeline update while playing ─────────────────────────────────────

video.addEventListener("timeupdate", () => {
  if (isDragging) return;
  vTimeline.value = Math.floor(video.currentTime);
  vCurrentTime.textContent = formatTime(video.currentTime);
});

// ── Viewer controls — emit to server, server broadcasts to everyone ────

function viewerPlay() {
  video.play();
  socket.emit("host_play", { timestamp: video.currentTime });
}

function viewerPause() {
  video.pause();
  socket.emit("host_pause", { timestamp: video.currentTime });
}

function onViewerTimelineDrag(val) {
  isDragging = true;
  vCurrentTime.textContent = formatTime(Number(val));
}

function onViewerTimelineSeek(val) {
  isDragging = false;
  const ts = Number(val);
  video.currentTime = ts;
  socket.emit("host_seek", { timestamp: ts });
}

// ── Sync helpers ───────────────────────────────────────────────────────

function showSyncOverlay() { overlay.style.display = "flex"; isSyncing = true; }
function hideSyncOverlay() { overlay.style.display = "none";  isSyncing = false; }

function seekIfNeeded(ts) {
  if (Math.abs(video.currentTime - ts) > SYNC_TOLERANCE) {
    video.currentTime = ts;
  }
}

// ── Socket: initial state on join ─────────────────────────────────────

socket.on("sync_state", (data) => {
  video.currentTime = data.timestamp;
  if (data.is_playing) {
    video.play().catch(() => showSyncOverlay());
  }
});

// ── Socket: play / pause / seek from anyone ────────────────────────────

socket.on("sync_play", (data) => {
  seekIfNeeded(data.timestamp);
  video.play().then(() => hideSyncOverlay()).catch(() => showSyncOverlay());
});

socket.on("sync_pause", (data) => {
  video.pause();
  seekIfNeeded(data.timestamp);
  hideSyncOverlay();
});

socket.on("sync_seek", (data) => {
  showSyncOverlay();
  video.currentTime = data.timestamp;
});

// ── Socket: subtitles updated by host ─────────────────────────────────

socket.on("subtitles_updated", () => {
  // Remove old track and add fresh one so browser reloads it
  const existing = video.querySelector("track");
  if (existing) existing.remove();

  const track = document.createElement("track");
  track.kind    = "subtitles";
  track.src     = "/subtitles?" + Date.now();
  track.srclang = "en";
  track.label   = "Subtitles";
  track.default = true;
  video.appendChild(track);
});

// ── Socket: viewer list + chat ─────────────────────────────────────────

socket.on("viewer_update", (data) => {
  document.getElementById("viewer-count-badge").textContent = `${data.count} watching`;
  const list = document.getElementById("viewer-list");
  list.innerHTML = data.viewers.map(n =>
    `<div class="viewer-item">${escHtml(n)}</div>`
  ).join("");
});

socket.on("chat_message", (data) => {
  appendChat(data.name, data.text);
});

function appendChat(name, text) {
  const box = document.getElementById("chat-messages");
  const msg = document.createElement("div");
  msg.className = "chat-msg";
  msg.innerHTML = `<span class="sender">${escHtml(name)}</span><span class="text">${escHtml(text)}</span>`;
  box.appendChild(msg);
  box.scrollTop = box.scrollHeight;
}

// ── Video buffering events ─────────────────────────────────────────────

video.addEventListener("waiting", () => showSyncOverlay());
video.addEventListener("playing", () => hideSyncOverlay());
video.addEventListener("canplay", () => { if (!isSyncing) hideSyncOverlay(); });

// ── Heartbeat ──────────────────────────────────────────────────────────
setInterval(() => socket.emit("ping_alive"), 30000);