# 🎬 CineSync

A self-hosted watch party application for Windows. Host a movie from your PC and watch it in perfect sync with friends over the internet — no subscriptions, no cloud, no bullshit.

---

## How it works

The host's PC acts as a private streaming server. Friends connect via [Tailscale](https://tailscale.com) (a free private VPN) and stream the movie directly from the host's machine in their browser. Playback is kept in sync via WebSockets — play, pause, and seek events are broadcast to everyone in real time.

```
Host PC (Flask server)
    │
    ├── You        →  http://localhost:5000        (host panel)
    ├── Friend A   →  http://100.x.x.x:5000/watch  (via Tailscale)
    └── Friend B   →  http://100.x.x.x:5000/watch  (via Tailscale)
```

Only the host needs the movie file. Friends just need a browser and Tailscale.

---

## Features

### Playback
- HTTP range request video streaming directly from host's disk
- Real-time sync — play, pause, seek broadcast to all viewers instantly
- Everyone can control playback (not just the host)
- Seek toast notification — `"Aditya jumped to 1:23:45"` shown to all
- Auto-resync when joining mid-movie with a click-to-start overlay

### Controls (viewer)
- Single play/pause toggle button
- Click video to play/pause
- Double-click video for fullscreen
- Keyboard shortcuts:
  - `Space` — play/pause
  - `←` / `→` — seek ±10 seconds
  - `F` — toggle fullscreen
  - `O` / `P` — subtitle delay ±50ms
- Auto-hide controls bar + cursor in fullscreen (reappears on mouse move)

### Volume
- Local volume control (doesn't sync to others)
- Vertical popup slider on hover above 🔊 icon
- Click icon to mute/unmute — icon changes between 🔊 🔉 🔇
- Scroll wheel on video to adjust volume
- Volume toast showing percentage on change

### Subtitles
- Load `.srt` subtitle files — converted to `.vtt` in memory (no temp files)
- Live reload for all viewers when host updates or clears subtitles
- Subtitle delay adjustment with `O` / `P` keys (±50ms per press)
- Toast shows current delay e.g. `Subtitle delay: +350ms`

### Chat
- Real-time chat sidebar for all viewers and host
- Each participant gets a unique colour assigned on join
- Chat history persists — rejoining restores all previous messages (up to 100)
- Message timestamps (12-hour format)
- Typing indicator — `"Atharva is typing..."`
- Collapsible sidebar with a translucent floating toggle button
- Video goes full width when sidebar is collapsed

### Viewer awareness
- Viewer list shows each person's current playback timestamp
- Timestamps update every second while playing
- Timestamps turn red if someone is more than 1.5 seconds out of sync
- Small red dot appears in top-right corner during fullscreen if anyone is out of sync

### Host panel
- Native Windows file picker (Browse button) — no path typing needed
- Same for subtitle file selection
- No temp files created — movie streams directly from its original location
- Manual path input still available as fallback
- Copy watch URL to clipboard with one click
- Live viewer count and names with coloured borders

### Networking
- Uses [Tailscale](https://tailscale.com) for private peer-to-peer connectivity
- Auto-detects Tailscale IP and displays the watch URL on startup
- Max 4 viewers enforced — rejected viewers see a "Party Full" message

---

## Requirements

- **Python 3.10+**
- **Windows** (for the native file picker — Linux/Mac will fall back to manual path entry)
- **Tailscale** installed and running on all machines

---

## Installation

**1. Clone the repo**
```bash
git clone https://github.com/AtharvaWankar/cinesync.git
cd cinesync
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Install Tailscale**

Download from [tailscale.com/download](https://tailscale.com/download), sign in with Google or GitHub, and connect your machine.

---

## Running CineSync

**Host (you):**
```bash
python app.py
```

The host panel opens automatically at `http://localhost:5000`.

1. Click **Browse** to select a movie file (`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`)
2. Optionally load a `.srt` subtitle file
3. Copy the Watch URL and send it to your friends
4. Hit **▶ Play** when everyone is ready

**Friends (viewers):**
1. Install Tailscale and accept your invite
2. Open the Watch URL in any modern browser
3. Enter their name and click **Join Party**

---

## File structure

```
cinesync/
├── app.py                  ← Entry point — run this
├── config.py               ← Port, chunk size, supported formats
├── requirements.txt
├── server/
│   ├── state.py            ← Party state (movie, viewers, chat history, colours)
│   ├── video_server.py     ← HTTP range request video streaming
│   ├── sync_server.py      ← WebSocket events (play/pause/seek/chat/typing)
│   └── network.py          ← Tailscale IP detection
├── templates/
│   ├── host.html           ← Host control panel
│   ├── watch.html          ← Viewer watch page
│   └── waiting.html        ← Shown if viewer arrives before movie is loaded
└── static/
    ├── css/style.css
    └── js/
        ├── host.js
        └── viewer.js
```

---

## Supported formats

| Format | Notes |
|--------|-------|
| `.mp4` | Best browser support — recommended |
| `.mkv` | Works if encoded in H.264. H.265/HEVC will not play in Chrome |
| `.avi` | Limited browser support |
| `.mov` | Works on most browsers |
| `.webm` | Full browser support |

> **Note on 4K / H.265:** Chrome cannot decode H.265 (HEVC) natively. If your 4K file uses H.265, it won't play in the browser. Convert it to H.264 using [HandBrake](https://handbrake.fr) (free) or use Microsoft Edge which has limited H.265 support on Windows.

---

## Keyboard shortcuts (viewer)

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `←` | Seek back 10 seconds |
| `→` | Seek forward 10 seconds |
| `F` | Toggle fullscreen |
| `O` | Subtitle delay −50ms (earlier) |
| `P` | Subtitle delay +50ms (later) |
| Double-click video | Toggle fullscreen |
| Scroll on video | Adjust volume |

---

## Configuration

Edit `config.py` to change defaults:

```python
PORT = 5000          # Server port
MAX_VIEWERS = 4      # Maximum viewers allowed in a party
CHUNK_SIZE = 1024 * 1024 * 8 # Video chunk size (8MB)
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask, Flask-SocketIO |
| Video streaming | HTTP range requests |
| Real-time sync | WebSockets (Socket.IO) |
| Networking | Tailscale |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| File picker | Python tkinter (native Windows dialog) |

---

## Known limitations

- H.265/HEVC 4K files won't play in Chrome (browser limitation, not fixable without Electron)
- Host's upload speed is the bottleneck — 1080p needs ~3-5 MB/s per viewer
- Tailscale free tier supports up to 3 devices (host + 2 friends)
- Subtitle support is `.srt` only — `.ass`/`.ssa` not supported
- Chat history resets when `app.py` is restarted

---

## Built by

Aditya Deuskar & Atharva Wankar
