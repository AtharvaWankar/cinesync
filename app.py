import os
import sys
import webbrowser
import threading
from flask import Flask, render_template, request, jsonify, abort
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
    """Host control panel — only accessible locally."""
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
    """Viewer watch page — accessible via Tailscale IP."""
    if not state.movie_path:
        return render_template("waiting.html", app_name=APP_NAME)
    return render_template(
        "watch.html",
        app_name=APP_NAME,
        movie_name=state.movie_name,
    )


@app.route("/api/load_movie", methods=["POST"])
def load_movie():
    """Host selects a movie file. Validates it exists and is a supported format."""
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


@app.route("/api/status")
def api_status():
    """Quick status endpoint — used by host UI to poll viewer count."""
    return jsonify({
        "movie_name":    state.movie_name,
        "is_playing":    state.is_playing,
        "timestamp":     state.timestamp,
        "viewer_count":  state.viewer_count(),
        "viewers":       state.viewer_names(),
        "party_active":  state.party_active,
        "watch_url":     get_watch_url(PORT),
    })


# ── Boot ───────────────────────────────────────────────────────────────

def open_host_browser():
    """Open the host panel in default browser after a short delay."""
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

    # Open host control panel in browser automatically
    threading.Thread(target=open_host_browser, daemon=True).start()

    socketio.run(app, host=HOST, port=PORT, debug=False)
