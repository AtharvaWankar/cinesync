const video   = document.getElementById("viewer-video");
const overlay = document.getElementById("sync-overlay");
const vTimeline    = document.getElementById("v-timeline");
const vCurrentTime = document.getElementById("v-current-time");
const vTotalTime   = document.getElementById("v-total-time");
const btnToggle    = document.getElementById("v-btn-toggle");

let viewerName  = "";
let myColour    = "#e8e8f0";
let isDragging  = false;
let clickTimer  = null;
let typingTimer = null;
let isTyping    = false;
const SYNC_TOLERANCE = 1.5;

// ── Volume ─────────────────────────────────────────────────────────────

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

// ── Click / double-click ───────────────────────────────────────────────

video.addEventListener("click", () => {
  if (clickTimer) return;
  clickTimer = setTimeout(() => { viewerToggle(); clickTimer = null; }, 220);
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

// ── Video metadata ─────────────────────────────────────────────────────

video.addEventListener("loadedmetadata", () => {
  vTimeline.max = Math.floor(video.duration);
  vTotalTime.textContent = formatTime(video.duration);
});

video.addEventListener("timeupdate", () => {
  if (isDragging) return;
  vTimeline.value = Math.floor(video.currentTime);
  vCurrentTime.textContent = formatTime(video.currentTime);
});

// ── Playback ───────────────────────────────────────────────────────────

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

// ── Progress reporting ─────────────────────────────────────────────────

setInterval(() => {
  if (viewerName && !video.paused && video.readyState >= 2) {
    socket.emit("viewer_progress", { timestamp: video.currentTime });
  }
}, 1000);

// ── Chat ───────────────────────────────────────────────────────────────

function sendChat() {
  const input = document.getElementById("chat-input");
  const text  = input.value.trim();
  if (!text || !viewerName) return;
  socket.emit("chat_message", { name: viewerName, text, time: nowTime(), colour: myColour });
  input.value = "";
  if (isTyping) { isTyping = false; socket.emit("typing_stop", { name: viewerName }); }
}

function onChatInput() {
  if (!viewerName) return;
  if (!isTyping) { isTyping = true; socket.emit("typing_start", { name: viewerName }); }
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

socket.on("chat_history", (data) => {
  const box = document.getElementById("chat-messages");
  box.innerHTML = "";
  data.messages.forEach(m => appendChat(m.name, m.text, m.time, m.colour));
});

// ── Typing indicator ───────────────────────────────────────────────────

const typingUsers = new Set();

socket.on("user_typing", (data) => { typingUsers.add(data.name); updateTypingIndicator(); });
socket.on("user_stopped_typing", (data) => { typingUsers.delete(data.name); updateTypingIndicator(); });

function updateTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (!el) return;
  if (typingUsers.size === 0) { el.textContent = ""; return; }
  const names = [...typingUsers].map(escHtml).join(", ");
  el.textContent = `${names} ${typingUsers.size === 1 ? "is" : "are"} typing...`;
}

// ── Sync helpers ───────────────────────────────────────────────────────

function showSyncOverlay() { overlay.style.display = "flex"; }
function hideSyncOverlay() { overlay.style.display = "none"; }

function seekIfNeeded(ts) {
  if (Math.abs(video.currentTime - ts) > SYNC_TOLERANCE)
    video.currentTime = ts;
}

// ── Socket: sync state on join ─────────────────────────────────────────

socket.on("sync_state", (data) => {
  video.currentTime = data.timestamp;
  setToggleBtn(data.is_playing);
  if (data.is_playing) {
    video.play().catch(() => showJoinOverlay(data.timestamp));
  }
});

function showJoinOverlay(timestamp) {
  const ov = document.getElementById("sync-overlay");
  ov.innerHTML = `
    <div class="join-start-box" onclick="onJoinClick()">
      <div style="font-size:36px">▶</div>
      <div style="font-size:14px; margin-top:8px">Click to join the party</div>
      <div style="font-size:11px; margin-top:4px; color: var(--text-dim)">
        Movie is at ${formatTime(timestamp)}
      </div>
    </div>
  `;
  ov.style.display = "flex";
}

function onJoinClick() {
  video.play().then(() => {
    const ov = document.getElementById("sync-overlay");
    ov.innerHTML = `<div class="spinner"></div><span>Syncing...</span>`;
    ov.style.display = "none";
    setToggleBtn(true);
  }).catch(e => console.error(e));
}

// ── Socket: play / pause / seek ────────────────────────────────────────

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

// ── Subtitles ──────────────────────────────────────────────────────────

socket.on("subtitles_updated", () => {
  subtitleDelay = 0;  // reset delay when host pushes new subtitles
  const existing = video.querySelector("track");
  if (existing) existing.remove();
  const track = document.createElement("track");
  track.kind = "subtitles"; track.src = "/subtitles?" + Date.now();
  track.srclang = "en"; track.label = "Subtitles"; track.default = true;
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
  if (!cues || cues.length === 0) { track.mode = "showing"; showSubtitleToast(); return; }
  for (let i = 0; i < cues.length; i++) { cues[i].startTime += delta; cues[i].endTime += delta; }
  track.mode = "showing";
  showSubtitleToast();
}

function showSubtitleToast() {
  const ms = Math.round(subtitleDelay * 1000);
  showToastMessage(`Subtitle delay: ${ms >= 0 ? "+" : ""}${ms}ms`);
}

// ── Movie changed ──────────────────────────────────────────────────────

socket.on("movie_changed", (data) => {
  subtitleDelay = 0;  // reset delay for new movie
  video.pause();
  video.src = "/video?" + Date.now();
  video.load();

  vTimeline.value = 0;
  vTimeline.max   = 100;
  vCurrentTime.textContent = "0:00";
  vTotalTime.textContent   = "0:00";

  setToggleBtn(false);

  const titleEl = document.getElementById("movie-title");
  if (titleEl) titleEl.textContent = data.movie_name;

  const existing = video.querySelector("track");
  if (existing) existing.remove();

  if (data.has_subtitles) {
    const track = document.createElement("track");
    track.kind = "subtitles"; track.src = "/subtitles?" + Date.now();
    track.srclang = "en"; track.label = "Subtitles"; track.default = true;
    video.appendChild(track);
  }

  showToastMessage(`▶ Now loading: ${data.movie_name}`);

  // Refresh file list if open
  const filesBody = document.getElementById("files-body");
  if (filesBody && filesBody.classList.contains("files-open")) {
    currentRelPath = "";
    loadFolderContents();
  }
});

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

// ── Viewer list ────────────────────────────────────────────────────────

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
  if (indicator) indicator.classList.toggle("visible", anyoneOutOfSync && !!document.fullscreenElement);
});

socket.on("chat_message", (data) => {
  appendChat(data.name, data.text, data.time, data.colour);
});

// ── Video buffering events ─────────────────────────────────────────────

video.addEventListener("waiting", () => showSyncOverlay());
video.addEventListener("playing", () => { setToggleBtn(true); hideSyncOverlay(); });
video.addEventListener("pause",   () => setToggleBtn(false));
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

// ── Scroll wheel volume ────────────────────────────────────────────────

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

// ── Files panel ────────────────────────────────────────────────────────

let currentRelPath = "";

function toggleFiles() {
  const body    = document.getElementById("files-body");
  const chevron = document.getElementById("files-chevron");
  const isOpen  = body.classList.toggle("files-open");
  chevron.textContent = isOpen ? "▼" : "▶";
  if (isOpen) {
    currentRelPath = "";  // always start from root on open
    loadFolderContents();
  }
}

async function loadFolderContents(relPath) {
  if (relPath !== undefined) currentRelPath = relPath;

  const list = document.getElementById("files-list");
  list.innerHTML = `<div class="files-empty">Loading...</div>`;

  try {
    const url = currentRelPath
      ? `/api/folder_contents?path=${encodeURIComponent(currentRelPath)}`
      : "/api/folder_contents";

    const res  = await fetch(url);
    const data = await res.json();

    if (!data.ok) {
      list.innerHTML = `<div class="files-empty">${escHtml(data.error)}</div>`;
      return;
    }

    list.innerHTML = "";

    // Back button if in subfolder
    if (data.parent !== null && data.parent !== undefined) {
      const back = document.createElement("div");
      back.className = "file-item file-folder";
      back.innerHTML = `<span class="file-icon">←</span><span class="file-name">.. Back</span>`;
      back.onclick = () => loadFolderContents(data.parent);
      list.appendChild(back);
    }

    // Folders
    data.folders.forEach(f => {
      const el = document.createElement("div");
      el.className = "file-item file-folder";
      el.innerHTML = `<span class="file-icon">📁</span><span class="file-name">${escHtml(f.name)}</span>`;
      el.onclick = () => loadFolderContents(f.rel_path);
      list.appendChild(el);
    });

    // Files
    data.files.forEach(f => {
      const el = document.createElement("div");
      el.className = `file-item file-video${f.active ? " file-active" : ""}`;
      el.innerHTML = `<span class="file-icon">${f.active ? "▶" : "🎬"}</span><span class="file-name">${escHtml(f.name)}</span>`;
      if (!f.active) {
        el.onclick = () => requestEpisode(f.full_path, f.name);
      }
      list.appendChild(el);
    });

    if (data.folders.length === 0 && data.files.length === 0) {
      list.innerHTML = `<div class="files-empty">No video files here</div>`;
    }

  } catch (e) {
    list.innerHTML = `<div class="files-empty">Failed to load files</div>`;
  }
}

async function requestEpisode(fullPath, fileName) {
  showToastMessage(`▶ Switching to: ${fileName}`);
  try {
    const res  = await fetch("/api/load_movie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: fullPath }),
    });
    const data = await res.json();
    if (!data.ok) showToastMessage(`✗ ${data.error}`);
    // success case is handled by the movie_changed broadcast every client receives
  } catch (e) {
    showToastMessage("✗ Couldn't switch — server unreachable.");
  }
}