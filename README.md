# 🎬 CineSync — Watch Party App

Watch movies together with friends in real time. Host streams from their PC, friends watch in their browser.

## Requirements

- Python 3.10+
- [Tailscale](https://tailscale.com) installed on **all machines** (host + all viewers)
- All friends added to the host's Tailscale network

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Make sure Tailscale is running on your machine

# 3. Start the app
python app.py
```

The host panel opens automatically at `http://localhost:5000`

## How to use

1. **Host:** Click "Load Movie" → paste the full path to your movie file
2. **Host:** Copy the Watch URL shown (e.g. `http://100.x.x.x:5000/watch`)
3. **Host:** Send that URL to your friends on WhatsApp / Discord
4. **Friends:** Make sure Tailscale is running → open the URL in browser → enter name
5. **Host:** Wait for everyone to join → press Play → enjoy!

## Supported Formats

`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`

> **Tip:** `.mp4` has the best browser compatibility. If friends can't play `.mkv`, convert with HandBrake (free).

## Architecture

```
Host PC (Flask + SocketIO)
  ├── /video          → HTTP Range Request streaming
  ├── /watch          → Viewer watch page
  ├── /               → Host control panel
  └── WebSocket       → Play / Pause / Seek sync

Tailscale VPN
  └── Connects all devices on a private 100.x.x.x network
      No bandwidth limits. Fully encrypted. Free for up to 3 users.
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Friends can't open the URL | Make sure Tailscale is running on their machine and they're in your network |
| "File not found" error | Use the full absolute path, e.g. `C:\Movies\film.mp4` |
| Video won't play in browser | Convert `.mkv` to `.mp4` using HandBrake |
| Tailscale IP not detected | Run `tailscale up` in terminal, then restart the app |
