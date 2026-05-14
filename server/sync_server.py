from flask_socketio import SocketIO, emit, join_room
from server.state import state

ROOM = "watch_party"

def register_events(socketio: SocketIO):

    @socketio.on("connect")
    def on_connect():
        join_room(ROOM)

    @socketio.on("viewer_join")
    def on_viewer_join(data):
        from flask import request as req
        from config import MAX_VIEWERS

        if state.viewer_count() >= MAX_VIEWERS:
            emit("join_rejected", {"reason": f"Party is full (max {MAX_VIEWERS} viewers)."})
            return

        name = data.get("name", "Friend")
        state.add_viewer(req.sid, name)
        colour = state.get_viewer_colour(req.sid)

        emit("sync_state", state.snapshot())
        emit("chat_history", {"messages": state.get_chat_history()})
        emit("your_colour", {"colour": colour})

        socketio.emit("viewer_update", {
            "count":   state.viewer_count(),
            "viewers": state.viewers_with_timestamp(),
        }, room=ROOM)

        print(f"[JOIN]  {name} joined. Total: {state.viewer_count()}")

    @socketio.on("disconnect")
    def on_disconnect():
        from flask import request as req
        state.remove_viewer(req.sid)
        socketio.emit("viewer_update", {
            "count":   state.viewer_count(),
            "viewers": state.viewers_with_timestamp(),
        }, room=ROOM)
        print(f"[LEAVE] A viewer disconnected. Total: {state.viewer_count()}")

    @socketio.on("host_play")
    def on_play(data):
        ts = float(data.get("timestamp", 0))
        state.play(ts)
        socketio.emit("sync_play", {"timestamp": ts}, room=ROOM)
        print(f"[PLAY]  timestamp={ts:.2f}s")

    @socketio.on("host_pause")
    def on_pause(data):
        ts = float(data.get("timestamp", 0))
        state.pause(ts)
        socketio.emit("sync_pause", {"timestamp": ts}, room=ROOM)
        print(f"[PAUSE] timestamp={ts:.2f}s")

    @socketio.on("host_seek")
    def on_seek(data):
        ts = float(data.get("timestamp", 0))
        name = data.get("name", "Someone")
        state.seek(ts)
        socketio.emit("sync_seek", {"timestamp": ts, "name": name}, room=ROOM)
        print(f"[SEEK]  {name} → {ts:.2f}s")

    @socketio.on("viewer_progress")
    def on_viewer_progress(data):
        from flask import request as req
        ts = float(data.get("timestamp", 0))
        state.update_viewer_timestamp(req.sid, ts)
        socketio.emit("viewer_update", {
            "count":   state.viewer_count(),
            "viewers": state.viewers_with_timestamp(),
        }, room=ROOM)

    # ── Movie changed — broadcast to all viewers ────────────────────────
    @socketio.on("movie_changed")
    def on_movie_changed(data):
        socketio.emit("movie_changed", {
            "movie_name":    data.get("movie_name"),
            "has_subtitles": data.get("has_subtitles", False),
        }, room=ROOM)
        print(f"[MOVIE] Changed to: {data.get('movie_name')}")

    @socketio.on("chat_message")
    def on_chat(data):
        name   = data.get("name", "?")
        text   = data.get("text", "").strip()[:300]
        time   = data.get("time", "")
        colour = data.get("colour", "#e8e8f0")

        if text:
            state.add_chat_message(name, text, time, colour)
            socketio.emit("chat_message", {
                "name": name, "text": text,
                "time": time, "colour": colour,
            }, room=ROOM)

    @socketio.on("typing_start")
    def on_typing_start(data):
        from flask import request as req
        name = data.get("name", "Someone")
        socketio.emit("user_typing", {"name": name}, room=ROOM, skip_sid=req.sid)

    @socketio.on("typing_stop")
    def on_typing_stop(data):
        from flask import request as req
        name = data.get("name", "Someone")
        socketio.emit("user_stopped_typing", {"name": name}, room=ROOM, skip_sid=req.sid)

    @socketio.on("ping_alive")
    def on_ping():
        emit("pong_alive")

    @socketio.on("subtitles_updated")
    def on_subtitles_updated():
        socketio.emit("subtitles_updated", room=ROOM)