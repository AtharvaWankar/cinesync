# 🎬 CineSync

A self-hosted watch party application. Host a movie from your PC and watch it in perfect sync with friends over the internet — no subscriptions, no cloud, no uploads.

---

## How it works

The host's PC acts as a private streaming server. Friends connect via [Tailscale](https://tailscale.com) (a free private VPN) and stream the movie directly from the host's machine in their browser. Playback is kept in sync via WebSockets — play, pause, and seek events are broadcast to all peers in real time.

```
Host PC (Flask server)
    │
    ├── You        →  http://localhost:5000         (host panel)
    ├── Friend A   →  http://100.x.x.x:5000/watch   (via Tailscale)
    └── Friend B   →  http://100.x.x.x:5000/watch   (via Tailscale)
```

Only the host needs the movie file. Friends just need a browser and Tailscale.

---

## Features

### Library & file management
- Folder-based movie library — point CineSync at a folder and everything inside shows up as a browsable tile grid
- Native OS folder picker (Browse button) — no path typing needed
- Navigate subfolders directly from the host panel
- "Now Playing" tile highlights the currently active movie
- Viewers can browse the same folder from the watch page and request an episode switch — host gets a popup to accept or reject

### Playback
- HTTP range request video streaming directly from the host's disk — no upload
- Real-time sync — play, pause, seek broadcast to all peers instantly
- Both peers have equal control — anyone can play, pause, or seek
- Seek toast notification shown to all: `"Aditya jumped to 1:23:45"`
- Auto-resync on join: new joiners get a click-to-start overlay showing the current timestamp
- Socket reconnect recovery: if a peer's connection briefly drops, they automatically re-join and receive a fresh sync snapshot

### Audio transcoding
- Files with browser-incompatible audio (EAC3 / Dolby Digital+, AC3 / Dolby Digital, DTS, TrueHD) are transparently transcoded to AAC on the fly via ffmpeg
- Video is never re-encoded — zero quality loss, minimal CPU overhead
- Transcoding activates automatically only when needed; AAC / MP3 / Opus files stream raw with zero overhead
- Requires ffmpeg installed on the host machine (see [Requirements](#requirements))

### Subtitles
- Load `.srt` subtitle files — converted to WebVTT in memory (no temp files)
- Live reload for all viewers when host updates or clears subtitles
- Subtitle delay adjustment with `O` / `P` keys (±50ms per press)
- Toast shows current delay: `Subtitle delay: +350ms`
- Delay resets automatically when a new movie or subtitle file is loaded

### Chat
- Real-time chat sidebar for all peers
- Each participant gets a unique colour assigned on join
- Chat history replayed on rejoin (up to 100 messages)
- Typing indicator: `"Atharva is typing..."`
- Collapsible sidebar — video goes full width when collapsed

### Viewer awareness
- Viewer list shows each person's current playback timestamp, updated every 250ms
- Timestamps turn red if someone is more than 1.5 seconds out of sync
- Small red dot in the corner during fullscreen if anyone is out of sync

### Stats for Nerds
- Overlay panel (ⓘ button) with live stats:
  - **Network:** ping, throughput, buffer ahead, rebuffer count, data transferred
  - **Video:** resolution, codec, FPS, HDR type, color space, bit depth, dropped frames
  - **Audio:** codec, channels, sample rate, bitrate, Dolby Atmos detection
- Powered by `ffprobe` — real values from the file, not guesses
- Graceful fallback with install hint if ffprobe is not found
- **↻ Recheck now** button if you install ffmpeg mid-session

### Controls (viewer)
- Play/pause toggle, timeline scrubber, volume slider
- Controls bar auto-hides after 3 seconds of inactivity
- Keyboard shortcuts — see [Keyboard shortcuts](#keyboard-shortcuts-viewer)

---

## Requirements

- **Python 3.10+**
- **ffmpeg** (includes ffprobe) — required for Stats for Nerds and automatic audio transcoding
- **Tailscale** — installed and running on all machines
- Windows recommended for the native folder/file picker. Linux/macOS works but falls back to manual path entry.

### Installing ffmpeg

| Platform | Command |
|----------|---------|
| Windows | `winget install ffmpeg` or `choco install ffmpeg` |
| macOS | `brew install ffmpeg` |
| Ubuntu / Debian | `sudo apt install ffmpeg` |

After installing, restart CineSync. If you install mid-session, use the **↻ Recheck now** link in the Stats for Nerds panel to pick it up without restarting.

---

## Installation

**1. Clone the repo**
```bash
git clone https://github.com/AtharvaWankar/cinesync.git
cd cinesync
```

**2. Install Python dependencies**
```bash
pip install -r requirements.txt
```

**3. Install ffmpeg** *(see above)*

**4. Install and connect Tailscale**

Download from [tailscale.com/download](https://tailscale.com/download), sign in, and make sure all machines are on the same Tailscale network.

---

## Running CineSync

**Host (you):**
```bash
python app.py
```

The host panel opens automatically at `http://localhost:5000`.

1. Click **Select Folder** to open your movie library
2. Click a movie tile to load it
3. Optionally load a `.srt` subtitle file
4. Copy the Watch URL and send it to your friends
5. Hit **▶ Play** when everyone is ready

**Friends (viewers):**
1. Install Tailscale and join your network
2. Open the Watch URL in any modern browser
3. Enter your name and click **Join Party**

---

## Supported formats

| Format | Notes |
|--------|-------|
| `.mp4` | Best browser support — recommended |
| `.mkv` | Works if video is H.264. H.265/HEVC won't play in Chrome |
| `.avi` | Limited browser support |
| `.mov` | Works on most browsers |
| `.webm` | Full browser support |

### Audio codec support

| Codec | Browser support | CineSync behaviour |
|-------|----------------|--------------------|
| AAC | ✅ All browsers | Streamed raw |
| MP3 | ✅ All browsers | Streamed raw |
| Opus | ✅ All browsers | Streamed raw |
| EAC3 (Dolby Digital+) | ❌ Not supported | Auto-transcoded to AAC via ffmpeg |
| AC3 (Dolby Digital) | ❌ Not supported | Auto-transcoded to AAC via ffmpeg |
| DTS | ❌ Not supported | Auto-transcoded to AAC via ffmpeg |
| TrueHD | ❌ Not supported | Auto-transcoded to AAC via ffmpeg |

> **Seeking with transcoded audio:** when transcoding is active, the stream is a live ffmpeg pipe so seeks buffer forward from the current position rather than jumping instantly. For instant seeking, pre-convert the audio track to AAC using [HandBrake](https://handbrake.fr) (free).

> **H.265 / 4K:** Chrome cannot decode H.265 natively. Use Edge on Windows or pre-convert with HandBrake.

---

## Keyboard shortcuts (viewer)

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `←` | Seek back 10 seconds |
| `→` | Seek forward 10 seconds |
| `F` | Toggle fullscreen |
| `O` | Subtitle delay −50ms |
| `P` | Subtitle delay +50ms |
| Double-click video | Toggle fullscreen |
| Scroll on video | Adjust volume |

---

## Configuration

Edit `config.py` to change defaults:

```python
PORT        = 5000              # Server port
MAX_VIEWERS = 4                 # Maximum simultaneous viewers
CHUNK_SIZE  = 16 * 1024 * 1024  # Video chunk size (16 MB)
```

---

## File structure

```
cinesync/
├── app.py                   ← Entry point + all REST API routes
├── config.py                ← Port, chunk size, supported formats
├── requirements.txt
├── server/
│   ├── state.py             ← Party state (movie, viewers, chat, colours)
│   ├── video_server.py      ← HTTP range streaming + EAC3/AC3 transcoding
│   ├── sync_server.py       ← WebSocket events (play/pause/seek/chat/typing)
│   ├── mediainfo.py         ← ffprobe wrapper for Stats for Nerds
│   └── network.py           ← Tailscale IP detection
├── templates/
│   ├── host.html            ← Host control panel
│   ├── watch.html           ← Viewer watch page
│   └── waiting.html         ← Shown before host loads a movie
└── static/
    ├── css/style.css
    └── js/
        ├── host.js          ← Host-side logic
        ├── viewer.js        ← Viewer-side logic
        ├── stats.js         ← Stats for Nerds panel
        └── socket-client.js ← Shared Socket.IO connection setup
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, Flask 3.0 |
| Real-time sync | Flask-SocketIO + WebSockets (polling fallback) |
| Video streaming | HTTP range requests |
| Audio transcoding | ffmpeg (on-the-fly, audio only, video copied) |
| Media inspection | ffprobe |
| Networking | Tailscale |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| File / folder picker | Python tkinter (native OS dialog) |

---

## Known limitations

- H.265 / HEVC files won't play in Chrome (browser limitation)
- Seeks on transcoded streams buffer forward rather than jumping instantly — pre-convert to AAC audio for instant seeking
- Host's upload speed is the bottleneck — 1080p needs ~3–5 MB/s per viewer
- Subtitle support is `.srt` only
- Party state resets when `app.py` is restarted
- Native file picker requires Windows; Linux/macOS falls back to manual path entry

---

## Built by

Aditya Deuskar & Atharva Wankar