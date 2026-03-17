const video    = document.getElementById("host-video");
const timeline = document.getElementById("timeline");
const currentTimeEl = document.getElementById("current-time");
const totalTimeEl   = document.getElementById("total-time");
const btnPlay  = document.getElementById("btn-play");
const btnPause = document.getElementById("btn-pause");

const HOST_COLOUR = "#f0c040"; // gold — always host's colour

let isDragging  = false;
let movieLoaded = false;

// ── Utilities ──────────────────────────────────────────────────────────

function formatTime(secs) {
  const s = Math.floor(secs);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
  return `${m}:${String(sec).padStart(2,"0")}`;
}

function setStatus(id, msg, type = "ok") {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.className = `status-msg ${type}`;
}

function setBadge(text, active = false) {
  const el = document.getElementById("status-badge");
  el.textContent = text;
  el.className = active ? "badge active" : "badge";
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

// ── Native File Browser ────────────────────────────────────────────────

async function browseMovie() {
  setStatus("load-status", "Opening file browser...", "");
  try {
    const res  = await fetch("/api/browse_movie");
    const data = await res.json();

    if (data.cancelled) {
      setStatus("load-status", "", "");
      return;
    }
    if (data.ok) {
      document.getElementById("movie-path").value = data.path;
      setStatus("load-status", `✓ Loaded: ${data.movie_name}`, "ok");
      document.getElementById("movie-loaded-name").textContent = `🎬 ${data.movie_name}`;
      enableControls();
      movieLoaded = true;
      setBadge("● Party Active", true);
      video.src = "/video";
      video.load();
    } else {
      setStatus("load-status", `✗ ${data.error}`, "error");
    }
  } catch (e) {
    setStatus("load-status", "✗ Server error.", "error");
  }
}

async function browseSubtitle() {
  setStatus("subtitle-status", "Opening file browser...", "");
  try {
    const res  = await fetch("/api/browse_subtitle");
    const data = await res.json();

    if (data.cancelled) {
      setStatus("subtitle-status", "", "");
      return;
    }
    if (data.ok) {
      document.getElementById("subtitle-path").value = data.path;
      setStatus("subtitle-status", "✓ Subtitles loaded!", "ok");
      const track = document.getElementById("host-track");
      if (track) { track.src = "/subtitles?" + Date.now(); }
      socket.emit("subtitles_updated");
    } else {
      setStatus("subtitle-status", `✗ ${data.error}`, "error");
    }
  } catch (e) {
    setStatus("subtitle-status", "✗ Server error.", "error");
  }
}

// ── Load Movie (manual path) ───────────────────────────────────────────

async function loadMovie() {
  const path = document.getElementById("movie-path").value.trim();
  if (!path) { setStatus("load-status", "Please enter a file path.", "error"); return; }

  setStatus("load-status", "Loading...", "");
  try {
    const res  = await fetch("/api/load_movie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    if (data.ok) {
      setStatus("load-status", `✓ Loaded: ${data.movie_name}`, "ok");
      document.getElementById("movie-loaded-name").textContent = `🎬 ${data.movie_name}`;
      enableControls();
      movieLoaded = true;
      setBadge("● Party Active", true);
      video.src = "/video";
      video.load();
    } else {
      setStatus("load-status", `✗ ${data.error}`, "error");
    }
  } catch (e) {
    setStatus("load-status", "✗ Server error.", "error");
  }
}

function enableControls() {
  btnPlay.disabled   = false;
  btnPause.disabled  = false;
  timeline.disabled  = false;
}

// ── Load Subtitles (manual path) ───────────────────────────────────────

async function loadSubtitles() {
  const path = document.getElementById("subtitle-path").value.trim();
  if (!path) { setStatus("subtitle-status", "Please enter a subtitle path.", "error"); return; }

  setStatus("subtitle-status", "Loading...", "");
  try {
    const res  = await fetch("/api/load_subtitles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    if (data.ok) {
      setStatus("subtitle-status", "✓ Subtitles loaded!", "ok");
      const track = document.getElementById("host-track");
      if (track) { track.src = "/subtitles?" + Date.now(); }
      socket.emit("subtitles_updated");
    } else {
      setStatus("subtitle-status", `✗ ${data.error}`, "error");
    }
  } catch (e) {
    setStatus("subtitle-status", "✗ Server error.", "error");
  }
}

async function clearSubtitles() {
  try {
    await fetch("/api/load_subtitles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: "" }),
    });
    document.getElementById("subtitle-path").value = "";
    setStatus("subtitle-status", "Subtitles cleared.", "ok");
    const track = document.getElementById("host-track");
    if (track) { track.src = ""; }
    socket.emit("subtitles_updated");
  } catch (e) {
    setStatus("subtitle-status", "✗ Server error.", "error");
  }
}

// ── Video metadata ─────────────────────────────────────────────────────

function onVideoLoaded() {
  timeline.max = Math.floor(video.duration);
  totalTimeEl.textContent = formatTime(video.duration);
}

function onTimeUpdate() {
  if (isDragging) return;
  timeline.value = Math.floor(video.currentTime);
  currentTimeEl.textContent = formatTime(video.currentTime);
}

// ── Timeline ───────────────────────────────────────────────────────────

function onTimelineDrag(val) {
  isDragging = true;
  currentTimeEl.textContent = formatTime(Number(val));
}

function onTimelineSeek(val) {
  isDragging = false;
  const ts = Number(val);
  video.currentTime = ts;
  socket.emit("host_seek", { timestamp: ts, name: "Host 👑" });
}

// ── Play / Pause ───────────────────────────────────────────────────────

function hostPlay() {
  if (!movieLoaded) return;
  video.play();
  socket.emit("host_play", { timestamp: video.currentTime });
}

function hostPause() {
  if (!movieLoaded) return;
  video.pause();
  socket.emit("host_pause", { timestamp: video.currentTime });
}

// ── Receive sync events from viewers ──────────────────────────────────

socket.on("sync_play", (data) => {
  if (Math.abs(video.currentTime - data.timestamp) > 1.5) {
    video.currentTime = data.timestamp;
  }
  video.play();
});

socket.on("sync_pause", (data) => {
  video.pause();
  if (Math.abs(video.currentTime - data.timestamp) > 1.5) {
    video.currentTime = data.timestamp;
  }
});

socket.on("sync_seek", (data) => {
  video.currentTime = data.timestamp;
});

// ── Chat ───────────────────────────────────────────────────────────────

function sendChat() {
  const input = document.getElementById("chat-input");
  const text  = input.value.trim();
  if (!text) return;
  socket.emit("chat_message", {
    name:   "Host 👑",
    text:   text,
    time:   nowTime(),
    colour: HOST_COLOUR,
  });
  input.value = "";
}

function appendChat(name, text, time, colour) {
  const box = document.getElementById("chat-messages");
  const msg = document.createElement("div");
  msg.className = "chat-msg";
  msg.innerHTML = `
    <div class="chat-msg-header">
      <span class="sender" style="color:${colour || HOST_COLOUR}">${escHtml(name)}</span>
      <span class="chat-time">${escHtml(time || "")}</span>
    </div>
    <span class="text">${escHtml(text)}</span>
  `;
  box.appendChild(msg);
  box.scrollTop = box.scrollHeight;
}

// ── Copy URL ───────────────────────────────────────────────────────────

function copyURL() {
  const url = document.getElementById("watch-url").value;
  navigator.clipboard.writeText(url).then(() => {
    setStatus("copy-status", "✓ Copied to clipboard!", "ok");
    setTimeout(() => setStatus("copy-status", "", ""), 2500);
  });
}

// ── Socket: viewer list + chat ─────────────────────────────────────────

socket.on("viewer_update", (data) => {
  document.getElementById("viewer-count").textContent = data.count;
  const list = document.getElementById("viewer-list");
  list.innerHTML = data.viewers.map(v =>
    `<div class="viewer-chip" style="border-color:${v.colour}40">
      <span style="color:${v.colour}">${escHtml(v.name)}</span>
      <span class="viewer-ts">${formatTime(v.timestamp)}</span>
    </div>`
  ).join("");
});

socket.on("chat_message", (data) => {
  appendChat(data.name, data.text, data.time, data.colour);
});