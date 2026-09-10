import os
import re
import secrets
import logging
import webbrowser
import threading
import tkinter as tk
from tkinter import filedialog
from flask import Flask, render_template, request, jsonify, Response, abort
from flask_socketio import SocketIO

from config import PORT, HOST, SUPPORTED_FORMATS, APP_NAME
from server.state import state
from server.video_server import video_bp
from server.sync_server import register_events
from server.network import get_tailscale_ip, get_watch_url
from server import mediainfo

# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── App setup ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

app.register_blueprint(video_bp)
register_events(socketio)


# ── Helpers ────────────────────────────────────────────────────────────

def _pick_file(title: str, filetypes: list) -> str | None:
    """Open a native OS file dialog. Returns the chosen path or None."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        return path or None
    except Exception as e:
        log.warning(f"File dialog error: {e}")
        return None


def _pick_folder(title: str) -> str | None:
    """Open a native OS folder picker dialog. Returns the chosen path or None."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        path = filedialog.askdirectory(title=title, mustexist=True)
        root.destroy()
        return path or None
    except Exception as e:
        log.warning(f"Folder dialog error: {e}")
        return None


def _scan_library(base_dir: str, target: str) -> dict:
    """List video files, subtitle files, and subfolders in `target`,
    relative to `base_dir`."""
    with os.scandir(target) as entries:
        entry_list = list(entries)
    folders, files, subtitles = [], [], []

    for entry in sorted(entry_list, key=lambda e: e.name.lower()):
        # A single bad entry (broken symlink, a Windows junction, a
        # not-yet-downloaded OneDrive/cloud placeholder, a permission-denied
        # network mount, etc.) used to raise here and blow up the *entire*
        # listing — which is why folders that happened to contain nested
        # subfolders with one bad entry somewhere in the tree would just
        # stop working, while flat folders were fine. Skip the offending
        # entry instead of failing the whole scan.
        try:
            is_dir  = entry.is_dir()
            is_file = entry.is_file()
        except OSError as e:
            log.warning(f"Skipping unreadable entry '{entry.path}': {e}")
            continue

        if is_dir:
            folders.append({
                "name":     entry.name,
                "type":     "folder",
                "rel_path": os.path.relpath(entry.path, base_dir),
            })
        elif is_file:
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in SUPPORTED_FORMATS:
                files.append({
                    "name":      entry.name,
                    "type":      "file",
                    "full_path": entry.path,
                    "active":    entry.path == state.movie_path,
                })
            elif ext == ".srt":
                subtitles.append({
                    "name":      entry.name,
                    "type":      "subtitle",
                    "full_path": entry.path,
                    "active":    entry.path == state.subtitle_path,
                })

    parent = None
    if target != base_dir:
        parent = os.path.relpath(os.path.dirname(target), base_dir)
        if parent == ".":
            parent = ""

    return {
        "ok":        True,
        "folders":   folders,
        "files":     files,
        "subtitles": subtitles,
        "current":   os.path.basename(target) or os.path.basename(base_dir),
        "parent":    parent,
    }


def _load_and_broadcast_movie(path: str) -> dict:
    """Load a movie into state and broadcast the change to all viewers."""
    state.set_movie(path)
    state.party_active = True
    log.info(f"[MOVIE] Loaded: {path}")
    socketio.emit("movie_changed", {
        "movie_name":    state.movie_name,
        "has_subtitles": state.subtitle_path is not None,
    }, room="watch_party")
    return {"ok": True, "movie_name": state.movie_name}


def srt_to_vtt(srt: str) -> str:
    """Convert SRT subtitle format to WebVTT."""
    srt = srt.replace("\r\n", "\n").replace("\r", "\n")
    vtt = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt)
    return "WEBVTT\n\n" + vtt.strip() + "\n"


# ── Routes ─────────────────────────────────────────────────────────────

@app.route("/")
def host_panel():
    tailscale_ip = get_tailscale_ip()
    effective_ip = state.manual_tailscale_ip or tailscale_ip
    watch_url    = get_watch_url(PORT, override_ip=effective_ip)
    return render_template(
        "host.html",
        tailscale_ip=effective_ip,
        watch_url=watch_url,
        app_name=APP_NAME,
        manual_ip=state.manual_tailscale_ip or "",
    )


@app.route("/api/redetect_tailscale")
def redetect_tailscale():
    """Re-run auto-detection without restarting the server."""
    ip = get_tailscale_ip()
    effective_ip = state.manual_tailscale_ip or ip
    return jsonify({
        "ok": True,
        "detected_ip": ip,
        "effective_ip": effective_ip,
        "watch_url": get_watch_url(PORT, override_ip=effective_ip),
    })


@app.route("/api/set_watch_ip", methods=["POST"])
def set_watch_ip():
    """Let the host manually pin the IP used in the shareable watch URL,
    for the (rare) case where auto-detection can't find it — e.g. the
    tailscale CLI isn't on PATH, or a firewall blocks the local queries
    detection relies on. Find your IP with `tailscale ip -4` yourself."""
    data = request.get_json() or {}
    ip = (data.get("ip") or "").strip()

    if ip:
        ip_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        if not re.match(ip_pattern, ip):
            return jsonify({"ok": False, "error": "That doesn't look like a valid IP address."}), 400

    state.set_manual_ip(ip)
    return jsonify({"ok": True, "watch_url": get_watch_url(PORT, override_ip=ip or get_tailscale_ip())})


@app.route("/watch")
def watch_page():
    if not state.movie_path:
        return render_template("waiting.html", app_name=APP_NAME)
    return render_template(
        "watch.html",
        app_name=APP_NAME,
        movie_name=state.movie_name,
        has_subtitles=state.subtitle_path is not None,
    )


@app.route("/api/load_movie", methods=["POST"])
def load_movie():
    data = request.get_json()
    path = data.get("path", "").strip()

    if not path:
        return jsonify({"ok": False, "error": "No path provided."}), 400
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": f"File not found: {path}"}), 400

    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        return jsonify({
            "ok": False,
            "error": f"Unsupported format '{ext}'. Supported: {', '.join(SUPPORTED_FORMATS.keys())}"
        }), 400

    return jsonify(_load_and_broadcast_movie(path))


@app.route("/api/load_subtitles", methods=["POST"])
def load_subtitles():
    data = request.get_json()
    path = data.get("path", "").strip()

    if not path:
        state.clear_subtitle()
        return jsonify({"ok": True, "cleared": True})

    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": f"File not found: {path}"}), 400

    if not path.lower().endswith(".srt"):
        return jsonify({"ok": False, "error": "Only .srt files are supported."}), 400

    state.set_subtitle(path)
    log.info(f"[SUBS]  Loaded: {path}")
    return jsonify({"ok": True})


@app.route("/api/browse_movie")
def browse_movie():
    path = _pick_file(
        "Select Movie File",
        [("Video files", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All files", "*.*")],
    )
    if not path:
        return jsonify({"ok": False, "cancelled": True})

    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        return jsonify({
            "ok": False,
            "error": f"Unsupported format '{ext}'. Supported: {', '.join(SUPPORTED_FORMATS.keys())}"
        }), 400

    result = _load_and_broadcast_movie(path)
    result["path"] = path
    return jsonify(result)


@app.route("/api/browse_subtitle")
def browse_subtitle():
    path = _pick_file(
        "Select Subtitle File",
        [("Subtitle files", "*.srt"), ("All files", "*.*")],
    )
    if not path:
        return jsonify({"ok": False, "cancelled": True})

    if not path.lower().endswith(".srt"):
        return jsonify({"ok": False, "error": "Only .srt files are supported."}), 400

    state.set_subtitle(path)
    log.info(f"[SUBS]  Loaded: {path}")
    return jsonify({"ok": True, "path": path})


@app.route("/api/browse_folder")
def browse_folder():
    """Open a native folder picker, set it as the library root, and return
    its contents so the host can pick a movie from inside it."""
    path = _pick_folder("Select Movie Folder")
    if not path:
        return jsonify({"ok": False, "cancelled": True})

    state.set_library_root(path)
    try:
        result = _scan_library(path, path)
        result["root"] = path
        return jsonify(result)
    except Exception as e:
        log.error(f"browse_folder error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/set_library_path", methods=["POST"])
def set_library_path():
    """Set the library root from a manually-typed folder path."""
    data = request.get_json() or {}
    path = (data.get("path") or "").strip()

    if not path or not os.path.isdir(path):
        return jsonify({"ok": False, "error": "That folder doesn't exist."}), 400

    state.set_library_root(path)
    try:
        result = _scan_library(path, path)
        result["root"] = path
        return jsonify(result)
    except Exception as e:
        log.error(f"set_library_path error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/folder_contents")
def folder_contents():
    """Return video files and subfolders under the current library root
    (falls back to the loaded movie's directory for older sessions)."""
    base_dir = state.library_root or (
        os.path.dirname(state.movie_path) if state.movie_path else None
    )
    if not base_dir:
        return jsonify({"ok": False, "error": "No library selected."}), 400

    subfolder = request.args.get("path", "")

    if subfolder:
        # Folder names come back from the browser with "/" regardless of the
        # host OS, so normalise separators before joining on Windows.
        subfolder = subfolder.replace("/", os.sep).replace("\\", os.sep)
        target = os.path.normpath(os.path.join(base_dir, subfolder))
        # Use commonpath for safe traversal check (startswith is not
        # reliable). Compare with normcase so this doesn't spuriously fail
        # on Windows' case-insensitive, drive-letter-cased paths.
        if os.path.normcase(os.path.commonpath([target, base_dir])) != os.path.normcase(base_dir):
            return jsonify({"ok": False, "error": "Access denied."}), 403
    else:
        target = base_dir

    try:
        return jsonify(_scan_library(base_dir, target))
    except Exception as e:
        log.error(f"folder_contents error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/approve_episode", methods=["POST"])
def approve_episode():
    """Host approves a viewer's episode request — loads and broadcasts."""
    data = request.get_json()
    path = data.get("path", "").strip()

    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "error": "File not found."}), 400

    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        return jsonify({"ok": False, "error": "Unsupported format."}), 400

    log.info(f"[EPISODE] Approved: {path}")
    return jsonify(_load_and_broadcast_movie(path))


@app.route("/subtitles")
def serve_subtitles():
    if not state.subtitle_path or not os.path.isfile(state.subtitle_path):
        abort(404)

    with open(state.subtitle_path, "r", encoding="utf-8-sig") as f:
        srt_content = f.read()

    vtt = srt_to_vtt(srt_content)
    return Response(vtt, mimetype="text/vtt")


@app.route("/api/media_info")
def api_media_info():
    """Real technical stats for the currently loaded file (Stats for Nerds)."""
    if not state.movie_path:
        return jsonify({"ok": False, "error": "No movie loaded."}), 400
    info = mediainfo.probe(state.movie_path)
    info["ok"] = info.get("error") is None
    info["movie_name"] = state.movie_name
    return jsonify(info)


@app.route("/api/media_info/recheck")
def api_media_info_recheck():
    """Re-scan for ffprobe and re-probe the current file — lets the host
    install ffmpeg mid-session and pick it up without restarting."""
    found = mediainfo.redetect()
    if not state.movie_path:
        return jsonify({"ok": False, "available": found, "error": "No movie loaded."}), 400
    info = mediainfo.probe(state.movie_path, force=True)
    info["ok"] = info.get("error") is None
    info["movie_name"] = state.movie_name
    return jsonify(info)


@app.route("/api/ping")
def api_ping():
    """Cheap round-trip endpoint the viewer pings to measure latency."""
    return jsonify({"ok": True, "t": request.args.get("t", "")})


@app.route("/api/status")
def api_status():
    return jsonify({
        "movie_name":    state.movie_name,
        "is_playing":    state.is_playing,
        "timestamp":     state.timestamp,
        "viewer_count":  state.viewer_count(),
        "viewers":       state.viewer_names(),
        "party_active":  state.party_active,
        "watch_url":     get_watch_url(PORT),
        "has_subtitles": state.subtitle_path is not None,
    })


def open_host_browser():
    import time
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{PORT}/")


if __name__ == "__main__":
    tailscale_ip = get_tailscale_ip()

    print(f"""
╔══════════════════════════════════════════════╗
║           🎬  CineSync  v1.0                 ║
╠══════════════════════════════════════════════╣
║  Host panel  →  http://localhost:{PORT}        ║
║  Tailscale   →  {(tailscale_ip or 'Not detected'):<30} ║
║  Watch URL   →  {get_watch_url(PORT):<30} ║
╚══════════════════════════════════════════════╝
    """)

    if tailscale_ip is None:
        print("⚠️  Tailscale IP not detected. Make sure Tailscale is running.")
        print("   Friends can still connect via your LAN IP for local testing.\n")

    threading.Thread(target=open_host_browser, daemon=True).start()
    socketio.run(app, host=HOST, port=PORT, debug=False)
