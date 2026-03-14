import os
import re
import webbrowser
import threading
from flask import Flask, render_template, request, jsonify, Response, abort
from flask_socketio import SocketIO

from config import PORT, HOST, SUPPORTED_FORMATS, APP_NAME
from server.state import state
from server.video_server import video_bp
from server.sync_server import register_events
from server.network import get_tailscale_ip, get_watch_url

# ── App setup ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "cinesync-secret-2024"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

# ── Register blueprints & socket events ───────────────────────────────
app.register_blueprint(video_bp)
register_events(socketio)


# ── Routes ─────────────────────────────────────────────────────────────

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
    return jsonify({"ok": True, "movie_name": state.movie_name})


@app.route("/api/load_subtitles", methods=["POST"])
def load_subtitles():
    """Host loads an .srt subtitle file."""
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


@app.route("/subtitles")
def serve_subtitles():
    """
    Convert .srt to .vtt on the fly and serve it.
    Browsers only understand .vtt — we convert in memory, no temp files needed.
    """
    if not state.subtitle_path or not os.path.isfile(state.subtitle_path):
        abort(404)

    with open(state.subtitle_path, "r", encoding="utf-8-sig") as f:
        srt_content = f.read()

    vtt = srt_to_vtt(srt_content)

    return Response(vtt, mimetype="text/vtt")


def srt_to_vtt(srt: str) -> str:
    """Convert SRT subtitle format to WebVTT format in memory."""
    # Replace SRT timestamp separator , → .
    vtt = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt)
    # Strip Windows line endings
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


# ── Boot ───────────────────────────────────────────────────────────────

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

    