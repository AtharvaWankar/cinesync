const video   = document.getElementById("viewer-video");
const overlay = document.getElementById("sync-overlay");
const vTimeline    = document.getElementById("v-timeline");
const vCurrentTime = document.getElementById("v-current-time");
const vTotalTime   = document.getElementById("v-total-time");
const btnToggle    = document.getElementById("v-btn-toggle");

let viewerName  = "";
let myColour    = "#e8e8f0"; // assigned by server on join
let isDragging  = false;
let clickTimer  = null;
let typingTimer = null;
let isTyping    = false;
const SYNC_TOLERANCE = 1.5;

// ── Volume (local only, no sync) ───────────────────────────────────────

let lastVolume = 1;

function onVolumeChange(val) {
  const vol = Number(val) / 100;
  video.volume = vol;
  video.muted = vol === 0;
  updateVolIcon(vol);
  if (vol > 0) lastVolume = vol;
  showVolToast(vol);
}

function toggleMute() {
  if (video.muted || video.volume === 0) {
    video.muted  = false;
    video.volume = lastVolume;
    document.getElementById("v-volume").value = lastVolume * 100;
    updateVolIcon(lastVolume);
  } else {
    lastVolume   = video.volume;
    video.muted  = true;
    document.getElementById("v-volume").value = 0;
    updateVolIcon(0);
  }
}

function updateVolIcon(vol) {
  const icon = document.querySelector(".vol-icon");
  if (!icon) return;
  if (vol === 0 || video.muted) icon.textContent = "🔇";
  else if (vol < 0.5)           icon.textContent = "🔉";
  else                          icon.textContent = "🔊";
}

// ── Click to play/pause, double click to fullscreen ────────────────────

video.addEventListener("click", () => {
  if (clickTimer) return;
  clickTimer = setTimeout(() => {
    viewerToggle();
    clickTimer = null;
  }, 220);
});

video.addEventListener("dblclick", () => {
  clearTimeout(clickTimer);
  clickTimer = null;
  toggleFullscreen();
});

// ── Fullscreen ─────────────────────────────────────────────────────────

function toggleFullscreen() {
  const wrap = document.getElementById("watch-container");
  if (!document.fullscreenElement) {
    wrap.requestFullscreen().catch(e => console.error("Fullscreen failed:", e));
  } else {
    document.exitFullscreen();
  }
}

// ── Auto-hide controls in fullscreen ──────────────────────────────────

let controlsTimer = null;

function showControls() {
  const controls = document.querySelector(".viewer-controls");
  controls.classList.remove("controls-hidden");
  document.body.style.cursor = "";
  clearTimeout(controlsTimer);
  controlsTimer = setTimeout(() => {
    if (document.fullscreenElement) {
      controls.classList.add("controls-hidden");
      document.body.style.cursor = "none";
    }
  }, 4000);
}

document.addEventListener("fullscreenchange", () => {
  if (document.fullscreenElement) {
    showControls();
  } else {
    clearTimeout(controlsTimer);
    document.querySelector(".viewer-controls").classList.remove("controls-hidden");
    document.body.style.cursor = "";
  }
});

document.addEventListener("mousemove", () => {
  if (document.fullscreenElement) showControls();
});

// ── Toggle button state ────────────────────────────────────────────────

function setToggleBtn(playing) {
  btnToggle.textContent = playing ? "⏸" : "▶";
  btnToggle.classList.toggle("is-playing", playing);
}

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

// ── Colour assigned by server ──────────────────────────────────────────

socket.on("your_colour", (data) => {
  myColour = data.colour;
});

// ── Utilities ──────────────────────────────────────────────────────────

function formatTime(secs) {
  const s = Math.floor(secs);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
  return `${m}:${String(sec).padStart(2,"0")}`;
}

function nowTime() {
  const d = new Date();
  const h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, "0");
  const ampm = h >= 12 ? "PM" : "AM";
  return `${h % 12 || 12}:${m} ${ampm}`;
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

// ── Single toggle — emits same events host uses ────────────────────────

function viewerToggle() {
  if (video.paused) {
    video.play();
    socket.emit("host_play", { timestamp: video.currentTime });
  } else {
    video.pause();
    socket.emit("host_pause", { timestamp: video.currentTime });
  }
}

function onViewerTimelineDrag(val) {
  isDragging = true;
  vCurrentTime.textContent = formatTime(Number(val));
}

function onViewerTimelineSeek(val) {
  isDragging = false;
  const ts = Number(val);
  video.currentTime = ts;
  socket.emit("host_seek", { timestamp: ts, name: viewerName || "Someone" });
}

// ── Progress reporting — every 1 second ───────────────────────────────

setInterval(() => {
  if (viewerName && !video.paused) {
    socket.emit("viewer_progress", { timestamp: video.currentTime });
  }
}, 1000);

// ── Chat ───────────────────────────────────────────────────────────────

function sendChat() {
  const input = document.getElementById("chat-input");
  const text  = input.value.trim();
  if (!text || !viewerName) return;

  socket.emit("chat_message", {
    name:   viewerName,
    text:   text,
    time:   nowTime(),
    colour: myColour,
  });
  input.value = "";

  if (isTyping) {
    isTyping = false;
    socket.emit("typing_stop", { name: viewerName });
  }
}

function onChatInput() {
  if (!viewerName) return;

  if (!isTyping) {
    isTyping = true;
    socket.emit("typing_start", { name: viewerName });
  }

  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => {
    isTyping = false;
    socket.emit("typing_stop", { name: viewerName });
  }, 2000);
}

function appendChat(name, text, time, colour) {
  const box = document.getElementById("chat-messages");
  const msg = document.createElement("div");
  msg.className = "chat-msg";
  msg.innerHTML = `
    <div class="chat-msg-header">
      <span class="sender" style="color:${colour || "var(--accent)"}">${escHtml(name)}</span>
      <span class="chat-time">${escHtml(time || "")}</span>
    </div>
    <span class="text">${escHtml(text)}</span>
  `;
  box.appendChild(msg);
  box.scrollTop = box.scrollHeight;
}

// ── Chat history on join ───────────────────────────────────────────────

socket.on("chat_history", (data) => {
  const box = document.getElementById("chat-messages");
  box.innerHTML = ""; // clear first
  data.messages.forEach(m => appendChat(m.name, m.text, m.time, m.colour));
});

// ── Typing indicator ───────────────────────────────────────────────────

const typingUsers = new Set();

socket.on("user_typing", (data) => {
  typingUsers.add(data.name);
  updateTypingIndicator();
});

socket.on("user_stopped_typing", (data) => {
  typingUsers.delete(data.name);
  updateTypingIndicator();
});

function updateTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (!el) return;
  if (typingUsers.size === 0) {
    el.textContent = "";
  } else {
    const names = [...typingUsers].map(escHtml).join(", ");
    el.textContent = `${names} ${typingUsers.size === 1 ? "is" : "are"} typing...`;
  }
}

// ── Sync helpers ───────────────────────────────────────────────────────

function showSyncOverlay() { overlay.style.display = "flex"; }
function hideSyncOverlay() { overlay.style.display = "none"; }

function seekIfNeeded(ts) {
  if (Math.abs(video.currentTime - ts) > SYNC_TOLERANCE) {
    video.currentTime = ts;
  }
}

// ── Socket: initial state on join ─────────────────────────────────────

socket.on("sync_state", (data) => {
  video.currentTime = data.timestamp;
  setToggleBtn(data.is_playing);

  if (data.is_playing) {
    video.play().catch(() => {
      showJoinOverlay(data.timestamp);
    });
  }
});

function showJoinOverlay(timestamp) {
  const overlay = document.getElementById("sync-overlay");
  overlay.innerHTML = `
    <div class="join-start-box" onclick="onJoinClick()">
      <div style="font-size:36px">▶</div>
      <div style="font-size:14px; margin-top:8px">Click to join the party</div>
      <div style="font-size:11px; margin-top:4px; color: var(--text-dim)">
        Movie is at ${formatTime(timestamp)}
      </div>
    </div>
  `;
  overlay.style.display = "flex";
}

function onJoinClick() {
  video.play().then(() => {
    const overlay = document.getElementById("sync-overlay");
    overlay.innerHTML = `<div class="spinner"></div><span>Syncing...</span>`;
    overlay.style.display = "none";
    setToggleBtn(true);
  }).catch((e) => console.error("Play failed:", e));
}

// ── Socket: play / pause / seek from anyone ────────────────────────────

socket.on("sync_play", (data) => {
  seekIfNeeded(data.timestamp);
  video.play().then(() => {
    setToggleBtn(true);
    hideSyncOverlay();
  }).catch(() => showSyncOverlay());
});

socket.on("sync_pause", (data) => {
  video.pause();
  seekIfNeeded(data.timestamp);
  setToggleBtn(false);
  hideSyncOverlay();
});

socket.on("sync_seek", (data) => {
  video.currentTime = data.timestamp;
  showSeekToast(data.name, data.timestamp);
});

// ── Socket: subtitles updated by host ─────────────────────────────────

socket.on("subtitles_updated", () => {
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

// ── Subtitle delay ─────────────────────────────────────────────────────

let subtitleDelay = 0;

function applySubtitleDelay(delta) {
  subtitleDelay += delta;

  const trackEl = video.querySelector("track");
  if (!trackEl || !trackEl.track) return;

  const track = trackEl.track;
  track.mode = "hidden";

  const cues = track.cues;
  if (!cues || cues.length === 0) {
    track.mode = "showing";
    showSubtitleToast();
    return;
  }

  for (let i = 0; i < cues.length; i++) {
    cues[i].startTime += delta;
    cues[i].endTime   += delta;
  }

  track.mode = "showing";
  showSubtitleToast();
}

function showSubtitleToast() {
  const ms   = Math.round(subtitleDelay * 1000);
  const sign = ms >= 0 ? "+" : "";
  showToastMessage(`Subtitle delay: ${sign}${ms}ms`);
}

// ── Toast helper ───────────────────────────────────────────────────────

let toastTimer = null;

function showToastMessage(msg) {
  const toast = document.getElementById("seek-toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add("visible");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2000);
}

function showSeekToast(name, timestamp) {
  showToastMessage(`${name} jumped to ${formatTime(timestamp)}`);
}

// ── Socket: viewer list + chat ─────────────────────────────────────────

socket.on("viewer_update", (data) => {
  document.getElementById("viewer-count-badge").textContent = `${data.count} watching`;
  const list = document.getElementById("viewer-list");

  let anyoneOutOfSync = false;

  list.innerHTML = data.viewers.map(v => {
    const diff      = Math.abs(v.timestamp - video.currentTime);
    const outOfSync = diff > 1.5 && video.currentTime > 0;
    if (outOfSync) anyoneOutOfSync = true;
    const tsColor   = outOfSync ? "var(--red)" : "var(--text-dim)";
    return `<div class="viewer-item">
      <span style="color:${v.colour}">${escHtml(v.name)}</span>
      <span class="viewer-ts" style="color:${tsColor}">${formatTime(v.timestamp)}</span>
    </div>`;
  }).join("");

  const indicator = document.getElementById("sync-indicator");
  if (indicator) {
    const show = anyoneOutOfSync && document.fullscreenElement;
    indicator.classList.toggle("visible", show);
  }
});

socket.on("chat_message", (data) => {
  appendChat(data.name, data.text, data.time, data.colour);
});

// ── Video buffering events ─────────────────────────────────────────────

video.addEventListener("waiting", () => showSyncOverlay());
video.addEventListener("playing", () => {
  setToggleBtn(true);
  hideSyncOverlay();
});
video.addEventListener("pause", () => setToggleBtn(false));
video.addEventListener("canplay", () => hideSyncOverlay());

// ── Heartbeat ──────────────────────────────────────────────────────────
setInterval(() => socket.emit("ping_alive"), 30000);

// ── Keyboard shortcuts ─────────────────────────────────────────────────
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;

  if (e.key === " " || e.code === "Space") {
    e.preventDefault();
    viewerToggle();
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    const ts = Math.min(video.currentTime + 10, video.duration);
    video.currentTime = ts;
    socket.emit("host_seek", { timestamp: ts, name: viewerName || "Someone" });
  } else if (e.key === "ArrowLeft") {
    e.preventDefault();
    const ts = Math.max(video.currentTime - 10, 0);
    video.currentTime = ts;
    socket.emit("host_seek", { timestamp: ts, name: viewerName || "Someone" });
  } else if (e.key === "f" || e.key === "F") {
    e.preventDefault();
    toggleFullscreen();
  } else if (e.key === "o" || e.key === "O") {
    e.preventDefault();
    applySubtitleDelay(-0.05);
  } else if (e.key === "p" || e.key === "P") {
    e.preventDefault();
    applySubtitleDelay(0.05);
  }
});

// ── Join rejected ──────────────────────────────────────────────────────

socket.on("join_rejected", (data) => {
  const box = document.querySelector(".overlay-box");
  box.innerHTML = `
    <div class="logo">🎬 CineSync</div>
    <h2>Party Full</h2>
    <p>${escHtml(data.reason)}</p>
  `;
});

// ── Scroll wheel volume control ────────────────────────────────────────
video.addEventListener("wheel", (e) => {
  e.preventDefault();
  const step = 0.05;
  const newVol = Math.min(1, Math.max(0, video.volume + (e.deltaY < 0 ? step : -step)));
  video.volume = newVol;
  video.muted  = newVol === 0;
  document.getElementById("v-volume").value = newVol * 100;
  updateVolIcon(newVol);
  if (newVol > 0) lastVolume = newVol;
  showVolToast(newVol);
}, { passive: false });

// ── Volume toast ───────────────────────────────────────────────────────
let volToastTimer = null;

function showVolToast(vol) {
  const toast = document.getElementById("vol-toast");
  if (!toast) return;
  const pct  = Math.round(vol * 100);
  const icon = vol === 0 ? "🔇" : vol < 0.5 ? "🔉" : "🔊";
  toast.textContent = `${icon} ${pct}%`;
  toast.classList.add("visible");
  if (volToastTimer) clearTimeout(volToastTimer);
  volToastTimer = setTimeout(() => toast.classList.remove("visible"), 1500);
}