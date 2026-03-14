from flask_socketio import SocketIO, emit, join_room, disconnect
from server.state import state

ROOM = "watch_party"

def register_events(socketio: SocketIO):
    """
    Register all WebSocket events on the SocketIO instance.
    All clients (host + viewers) join the same ROOM.
    """

    # ── Connection ─────────────────────────────────────────────────────
    @socketio.on("connect")
    def on_connect():
        join_room(ROOM)

    # ── Viewer joins ───────────────────────────────────────────────────
    @socketio.on("viewer_join")
    def on_viewer_join(data):
        from flask import request as req
        name = data.get("name", "Friend")
        state.add_viewer(req.sid, name)

        # Send current playback state to the new joiner so they sync up instantly
        emit("sync_state", state.snapshot())

        # Tell everyone a new viewer arrived
        socketio.emit("viewer_update", {
            "count":   state.viewer_count(),
            "viewers": state.viewer_names(),
        }, room=ROOM)

        print(f"[JOIN]  {name} joined. Total viewers: {state.viewer_count()}")

    # ── Disconnect ─────────────────────────────────────────────────────
    @socketio.on("disconnect")
    def on_disconnect():
        from flask import request as req
        state.remove_viewer(req.sid)
        socketio.emit("viewer_update", {
            "count":   state.viewer_count(),
            "viewers": state.viewer_names(),
        }, room=ROOM)
        print(f"[LEAVE] A viewer disconnected. Total: {state.viewer_count()}")

    # ── Play ───────────────────────────────────────────────────────────
    @socketio.on("host_play")
    def on_play(data):
        ts = float(data.get("timestamp", 0))
        state.play(ts)
        # Broadcast to ALL clients including host so everyone's player syncs
        socketio.emit("sync_play", {"timestamp": ts}, room=ROOM)
        print(f"[PLAY]  timestamp={ts:.2f}s")

    # ── Pause ──────────────────────────────────────────────────────────
    @socketio.on("host_pause")
    def on_pause(data):
        ts = float(data.get("timestamp", 0))
        state.pause(ts)
        socketio.emit("sync_pause", {"timestamp": ts}, room=ROOM)
        print(f"[PAUSE] timestamp={ts:.2f}s")

    # ── Seek ───────────────────────────────────────────────────────────
    @socketio.on("host_seek")
    def on_seek(data):
        ts = float(data.get("timestamp", 0))
        state.seek(ts)
        socketio.emit("sync_seek", {"timestamp": ts}, room=ROOM)
        print(f"[SEEK]  timestamp={ts:.2f}s")

    # ── Chat ───────────────────────────────────────────────────────────
    @socketio.on("chat_message")
    def on_chat(data):
        name = data.get("name", "?")
        text = data.get("text", "").strip()[:300]  # cap at 300 chars
        if text:
            socketio.emit("chat_message", {"name": name, "text": text}, room=ROOM)

    # ── Ping (heartbeat so server knows viewer is still alive) ─────────
    @socketio.on("ping_alive")
    def on_ping():
        emit("pong_alive")

    @socketio.on("subtitles_updated")
    def on_subtitles_updated():
        socketio.emit("subtitles_updated", room=ROOM)