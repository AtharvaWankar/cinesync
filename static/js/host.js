/**
 * host.js — Host control panel logic
 * Drives the hidden <video> element and emits sync events to all viewers.
 */

const video = document.getElementById("host-video");
const timeline = document.getElementById("timeline");
const currentTimeEl = document.getElementById("current-time");
const totalTimeEl = document.getElementById("total-time");
const btnPlay = document.getElementById("btn-play");
const btnPause = document.getElementById("btn-pause");

let isDragging = false;
let movieLoaded = false;

// ── Utilities ──────────────────────────────────────────────────────────

function formatTime(secs) {
  const s = Math.floor(secs);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function setStatus(msg, type = "ok") {
  const el = document.getElementById("load-status");
  el.textContent = msg;
  el.className = `status-msg ${type}`;
}

function setBadge(text, active = false) {
  const el = document.getElementById("status-badge");
  el.textContent = text;
  el.className = active ? "badge active" : "badge";
}

// ── Load Movie ─────────────────────────────────────────────────────────

async function loadMovie() {
  const path = document.getElementById("movie-path").value.trim();
  if (!path) { setStatus("Please enter a file path.", "error"); return; }

  setStatus("Loading...", "");
  try {
    const res  = await fetch("/api/load_movie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    if (data.ok) {
      setStatus(`✓ Loaded: ${data.movie_name}`, "ok");
      document.getElementById("movie-loaded-name").textContent = `🎬 ${data.movie_name}`;
      enableControls();
      movieLoaded = true;
      setBadge("● Party Active", true);
      // Load the video metadata so we get duration
      video.src = "/video";
      video.load();
    } else {
      setStatus(`✗ ${data.error}`, "error");
    }
  } catch (e) {
    setStatus("✗ Server error. Is the app running?", "error");
  }
}

function enableControls() {
  btnPlay.disabled  = false;
  btnPause.disabled = false;
  timeline.disabled = false;
}

// ── Video metadata loaded ──────────────────────────────────────────────

function onVideoLoaded() {
  timeline.max = Math.floor(video.duration);
  totalTimeEl.textContent = formatTime(video.duration);
}

// ── Timeline update while playing ─────────────────────────────────────

function onTimeUpdate() {
  if (isDragging) return;
  timeline.value     = Math.floor(video.currentTime);
  currentTimeEl.textContent = formatTime(video.currentTime);
}

// ── Timeline drag (just update display, don't seek yet) ───────────────

function onTimelineDrag(val) {
  isDragging = true;
  currentTimeEl.textContent = formatTime(Number(val));
}

// ── Timeline release → seek ────────────────────────────────────────────

function onTimelineSeek(val) {
  isDragging = false;
  const ts = Number(val);
  video.currentTime = ts;
  socket.emit("host_seek", { timestamp: ts });
}

// ── Play ───────────────────────────────────────────────────────────────

function hostPlay() {
  if (!movieLoaded) return;
  video.play();
  socket.emit("host_play", { timestamp: video.currentTime });
}

// ── Pause ──────────────────────────────────────────────────────────────

function hostPause() {
  if (!movieLoaded) return;
  video.pause();
  socket.emit("host_pause", { timestamp: video.currentTime });
}

// ── Chat ───────────────────────────────────────────────────────────────

function sendChat() {
  const input = document.getElementById("chat-input");
  const text  = input.value.trim();
  if (!text) return;
  socket.emit("chat_message", { name: "Host 👑", text });
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

// ── Copy URL ───────────────────────────────────────────────────────────

function copyURL() {
  const url = document.getElementById("watch-url").value;
  navigator.clipboard.writeText(url).then(() => {
    const el = document.getElementById("copy-status");
    el.textContent = "✓ Copied to clipboard!";
    el.className = "status-msg ok";
    setTimeout(() => { el.textContent = ""; }, 2500);
  });
}

// ── Socket events from server ──────────────────────────────────────────

socket.on("viewer_update", (data) => {
  document.getElementById("viewer-count").textContent = data.count;
  const list = document.getElementById("viewer-list");
  list.innerHTML = data.viewers.map(n =>
    `<div class="viewer-chip">${escHtml(n)}</div>`
  ).join("");
});

socket.on("chat_message", (data) => {
  appendChat(data.name, data.text);
});
