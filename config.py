import os

# Server
PORT = 5000
HOST = "0.0.0.0"  # Bind to all interfaces so Tailscale IP works

# Video
CHUNK_SIZE = 1024 * 1024 *8 # 8MB chunks
SUPPORTED_FORMATS = {
    ".mp4":  "video/mp4",
    ".mkv":  "video/x-matroska",
    ".avi":  "video/x-msvideo",
    ".mov":  "video/quicktime",
    ".webm": "video/webm",
}

# App
MAX_VIEWERS = 4
APP_NAME = "CineSync"
VERSION = "1.0.0"
