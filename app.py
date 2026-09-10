import os
import re
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

app = Flask(__name__)
app.config["SECRET_KEY"] = "cinesync-secret-2024"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

app.register_blueprint(video_bp)
register_events(socketio)


@app.route("/")
def host_panel():
    tailscale_ip = get_tailscale_ip()
    watch_url    = get_watch_url(PORT)
    return render_template(
        "host.html",
        tailscale_ip=tailscale_ip,
        watch_url=watch_url,
        app_name=APP_NAME,
    )


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

    state.set_movie(path)
    state.party_active = True
    print(f"[MOVIE] Loaded: {path}")

    socketio.emit("movie_changed", {
        "movie_name":    state.movie_name,
        "has_subtitles": state.subtitle_path is not None,
    }, room="watch_party")

    return jsonify({"ok": True, "movie_name": state.movie_name})


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
    print(f"[SUBS]  Loaded: {path}")
    return jsonify({"ok": True})


@app.route("/api/browse_movie")
def browse_movie():
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", True)

    path = filedialog.askopenfilename(
        title="Select Movie File",
        filetypes=[
            ("Video files", "*.mp4 *.mkv *.avi *.mov *.webm"),
            ("All files", "*.*"),
        ]
    )
    root.destroy()

    if not path:
        return jsonify({"ok": False, "cancelled": True})

    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        return jsonify({
            "ok": False,
            "error": f"Unsupported format '{ext}'. Supported: {', '.join(SUPPORTED_FORMATS.keys())}"
        }), 400

    state.set_movie(path)
    state.party_active = True
    print(f"[MOVIE] Loaded: {path}")

    socketio.emit("movie_changed", {
        "movie_name":    state.movie_name,
        "has_subtitles": state.subtitle_path is not None,
    }, room="watch_party")

    return jsonify({"ok": True, "movie_name": state.movie_name, "path": path})


@app.route("/api/browse_subtitle")
def browse_subtitle():
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", True)

    path = filedialog.askopenfilename(
        title="Select Subtitle File",
        filetypes=[
            ("Subtitle files", "*.srt"),
            ("All files", "*.*"),
        ]
    )
    root.destroy()

    if not path:
        return jsonify({"ok": False, "cancelled": True})

    if not path.lower().endswith(".srt"):
        return jsonify({"ok": False, "error": "Only .srt files are supported."}), 400

    state.set_subtitle(path)
    print(f"[SUBS]  Loaded: {path}")
    return jsonify({"ok": True, "path": path})


@app.route("/api/folder_contents")
def folder_contents():
    """Return video files and subfolders in the current movie's directory."""
    if not state.movie_path:
        return jsonify({"ok": False, "error": "No movie loaded."}), 400

    # Allow navigating to a subfolder
    subfolder = request.args.get("path", "")
    base_dir  = os.path.dirname(state.movie_path)

    if subfolder:
        target = os.path.normpath(os.path.join(base_dir, subfolder))
        # Security: never allow navigating above the base directory
        if not target.startswith(base_dir):
            return jsonify({"ok": False, "error": "Access denied."}), 403
    else:
        target = base_dir

    try:
        entries = os.scandir(target)
        folders = []
        files   = []

        for entry in sorted(entries, key=lambda e: e.name.lower()):
            if entry.is_dir():
                folders.append({
                    "name":     entry.name,
                    "type":     "folder",
                    "rel_path": os.path.relpath(entry.path, base_dir),
                })
            elif entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in SUPPORTED_FORMATS:
                    files.append({
                        "name":      entry.name,
                        "type":      "file",
                        "full_path": entry.path,
                        "active":    entry.path == state.movie_path,
                    })

        # Show parent folder navigation if we're in a subfolder
        parent = None
        if target != base_dir:
            parent = os.path.relpath(os.path.dirname(target), base_dir)
            if parent == ".":
                parent = ""

        return jsonify({
            "ok":      True,
            "folders": folders,
            "files":   files,
            "current": os.path.basename(target),
            "parent":  parent,
        })

    except Exception as e:
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

    state.set_movie(path)
    state.party_active = True
    print(f"[EPISODE] Approved: {path}")

    socketio.emit("movie_changed", {
        "movie_name":    state.movie_name,
        "has_subtitles": state.subtitle_path is not None,
    }, room="watch_party")

    return jsonify({"ok": True, "movie_name": state.movie_name})


@app.route("/subtitles")
def serve_subtitles():
    if not state.subtitle_path or not os.path.isfile(state.subtitle_path):
        abort(404)

    with open(state.subtitle_path, "r", encoding="utf-8-sig") as f:
        srt_content = f.read()

    vtt = srt_to_vtt(srt_content)
    return Response(vtt, mimetype="text/vtt")


def srt_to_vtt(srt: str) -> str:
    vtt = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt)
    vtt = vtt.replace("\r\n", "\n").replace("\r", "\n")
    return "WEBVTT\n\n" + vtt.strip()


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