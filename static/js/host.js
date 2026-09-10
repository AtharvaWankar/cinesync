const video    = document.getElementById("host-video");
const timeline = document.getElementById("timeline");
const currentTimeEl = document.getElementById("current-time");
const totalTimeEl   = document.getElementById("total-time");
const btnPlay  = document.getElementById("btn-play");
const btnPause = document.getElementById("btn-pause");

const HOST_COLOUR = "#f0c040";

let isDragging        = false;
let movieLoaded       = false;
let pendingEpisodePath = null;

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

// ── Episode request popup ──────────────────────────────────────────────

socket.on("episode_request", (data) => {
  pendingEpisodePath = data.full_path;
  document.getElementById("episode-popup-msg").textContent =
    `${data.viewer_name} wants to watch "${data.file_name}"`;
  document.getElementById("episode-popup").style.display = "flex";
});

async function approveEpisode() {
  if (!pendingEpisodePath) return;
  document.getElementById("episode-popup").style.display = "none";

  try {
    const res  = await fetch("/api/approve_episode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: pendingEpisodePath }),
    });
    const data = await res.json();
    if (data.ok) {
      onMovieLoaded(data.movie_name);
    }
  } catch (e) {
    console.error("approve_episode failed:", e);
  }

  pendingEpisodePath = null;
}

function rejectEpisode() {
  document.getElementById("episode-popup").style.display = "none";
  pendingEpisodePath = null;
}

// ── After movie loads ──────────────────────────────────────────────────

function onMovieLoaded(movie_name) {
  document.getElementById("movie-loaded-name").textContent = `🎬 ${movie_name}`;
  enableControls();
  movieLoaded = true;
  setBadge("● Party Active", true);

  video.pause();
  video.src = "/video?" + Date.now();
  video.load();

  timeline.value = 0;
  currentTimeEl.textContent = "0:00";
  totalTimeEl.textContent   = "0:00";
}

// ── Library (folder-based movie picker) ─────────────────────────────────

let libraryRoot   = null;
let libraryPath   = "";   // relative path within the root, "" = top level

function libIcon(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  return "🎬";
}

function renderLibrary(data) {
  const grid  = document.getElementById("library-grid");
  const empty = document.getElementById("library-empty");
  const crumbWrap = document.getElementById("library-breadcrumb");
  const crumbCurrent = document.getElementById("crumb-current");

  const hasContent = (data.folders && data.folders.length) || (data.files && data.files.length);
  grid.style.display = hasContent ? "grid" : "none";
  empty.style.display = hasContent ? "none" : "block";
  empty.textContent = "This folder has no video files or subfolders.";

  crumbWrap.style.display = libraryRoot ? "flex" : "none";
  crumbCurrent.textContent = data.current || "";
  document.getElementById("crumb-back").disabled = !data.parent && data.parent !== "";
  document.getElementById("crumb-back").style.visibility =
    (libraryPath === "" ) ? "hidden" : "visible";

  const tiles = [];

  (data.folders || []).forEach((f, i) => {
    tiles.push(`
      <div class="tile tile-folder" style="--i:${i}" onclick="libraryOpenFolder('${escAttr(f.rel_path)}')">
        <div class="tile-art tile-art-folder">📁</div>
        <div class="tile-label">${escHtml(f.name)}</div>
      </div>
    `);
  });

  (data.files || []).forEach((f, i) => {
    const activeClass = f.active ? " tile-active" : "";
    tiles.push(`
      <div class="tile tile-movie${activeClass}" style="--i:${(data.folders||[]).length + i}" onclick="librarySelectMovie('${escAttr(f.full_path)}')">
        <div class="tile-art tile-art-movie">
          <span class="tile-play">▶</span>
          <span class="tile-glow"></span>
        </div>
        <div class="tile-label">${escHtml(f.name)}</div>
        ${f.active ? '<div class="tile-now">Now Playing</div>' : ""}
      </div>
    `);
  });

  grid.innerHTML = tiles.join("");
}

function escAttr(str) {
  return String(str).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

async function browseFolder() {
  setStatus("library-status", "Opening folder browser...", "");
  try {
    const res  = await fetch("/api/browse_folder");
    const data = await res.json();

    if (data.cancelled) { setStatus("library-status", "", ""); return; }
    if (data.ok) {
      libraryRoot = data.root;
      libraryPath = "";
      document.getElementById("library-path-input").value = data.root;
      setStatus("library-status", `✓ Library: ${data.root}`, "ok");
      renderLibrary(data);
    } else {
      setStatus("library-status", `✗ ${data.error}`, "error");
    }
  } catch (e) {
    setStatus("library-status", "✗ Server error.", "error");
  }
}

async function setLibraryPathManual() {
  const path = document.getElementById("library-path-input").value.trim();
  if (!path) { setStatus("library-status", "Please enter a folder path.", "error"); return; }

  setStatus("library-status", "Opening…", "");
  try {
    const res  = await fetch("/api/set_library_path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    if (data.ok) {
      libraryRoot = data.root;
      libraryPath = "";
      setStatus("library-status", `✓ Library: ${data.root}`, "ok");
      renderLibrary(data);
    } else {
      setStatus("library-status", `✗ ${data.error}`, "error");
    }
  } catch (e) {
    setStatus("library-status", "✗ Server error.", "error");
  }
}

async function libraryFetch(relPath) {
  const url = relPath
    ? `/api/folder_contents?path=${encodeURIComponent(relPath)}`
    : "/api/folder_contents";
  const res  = await fetch(url);
  const data = await res.json();
  if (data.ok) {
    libraryPath = relPath;
    renderLibrary(data);
  } else {
    setStatus("library-status", `✗ ${data.error}`, "error");
  }
}

function libraryOpenFolder(relPath) {
  libraryFetch(relPath);
}

function libraryGoUp() {
  if (libraryPath === "") return;
  const parent = libraryPath.includes("/") || libraryPath.includes("\\")
    ? libraryPath.replace(/[\\/][^\\/]*$/, "")
    : "";
  libraryFetch(parent === libraryPath ? "" : parent);
}

async function librarySelectMovie(fullPath) {
  setStatus("library-status", "Loading…", "");
  try {
    const res  = await fetch("/api/load_movie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: fullPath }),
    });
    const data = await res.json();
    if (data.ok) {
      setStatus("library-status", `✓ Now playing: ${data.movie_name}`, "ok");
      onMovieLoaded(data.movie_name);
      libraryFetch(libraryPath); // refresh grid so the active tile updates
    } else {
      setStatus("library-status", `✗ ${data.error}`, "error");
    }
  } catch (e) {
    setStatus("library-status", "✗ Server error.", "error");
  }
}

// ── Native File Browser (subtitles) ─────────────────────────────────────

async function browseSubtitle() {
  setStatus("subtitle-status", "Opening file browser...", "");
  try {
    const res  = await fetch("/api/browse_subtitle");
    const data = await res.json();

    if (data.cancelled) { setStatus("subtitle-status", "", ""); return; }
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

function enableControls() {
  btnPlay.disabled   = false;
  btnPause.disabled  = false;
  timeline.disabled  = false;
}

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

function onVideoLoaded() {
  timeline.max = Math.floor(video.duration);
  totalTimeEl.textContent = formatTime(video.duration);
}

function onTimeUpdate() {
  if (isDragging) return;
  timeline.value = Math.floor(video.currentTime);
  currentTimeEl.textContent = formatTime(video.currentTime);
}

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

socket.on("sync_play", (data) => {
  if (Math.abs(video.currentTime - data.timestamp) > 1.5)
    video.currentTime = data.timestamp;
  video.play();
});

socket.on("sync_pause", (data) => {
  video.pause();
  if (Math.abs(video.currentTime - data.timestamp) > 1.5)
    video.currentTime = data.timestamp;
});

socket.on("sync_seek", (data) => {
  video.currentTime = data.timestamp;
});

function sendChat() {
  const input = document.getElementById("chat-input");
  const text  = input.value.trim();
  if (!text) return;
  socket.emit("chat_message", { name: "Host 👑", text, time: nowTime(), colour: HOST_COLOUR });
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

function copyURL() {
  const url = document.getElementById("watch-url").value;
  navigator.clipboard.writeText(url).then(() => {
    setStatus("copy-status", "✓ Copied to clipboard!", "ok");
    setTimeout(() => setStatus("copy-status", "", ""), 2500);
  });
}

async function retryTailscaleDetect() {
  setStatus("tailscale-status", "Detecting…", "ok");
  try {
    const res = await fetch("/api/redetect_tailscale");
    const data = await res.json();
    if (data.effective_ip) {
      document.getElementById("watch-url").value = data.watch_url;
      setStatus("tailscale-status", `✓ Found it: ${data.effective_ip} — reload the page to clear the warning.`, "ok");
    } else {
      setStatus("tailscale-status", "Still nothing found. Make sure Tailscale is running, or enter the IP manually below.", "error");
    }
  } catch (e) {
    setStatus("tailscale-status", "Couldn't reach the server to retry.", "error");
  }
}

async function saveManualIp() {
  const ip = document.getElementById("manual-ip-input").value.trim();
  try {
    const res = await fetch("/api/set_watch_ip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ip }),
    });
    const data = await res.json();
    if (data.ok) {
      document.getElementById("watch-url").value = data.watch_url;
      setStatus("tailscale-status", "✓ Watch URL updated.", "ok");
    } else {
      setStatus("tailscale-status", data.error || "Couldn't save that IP.", "error");
    }
  } catch (e) {
    setStatus("tailscale-status", "Couldn't reach the server.", "error");
  }
}

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