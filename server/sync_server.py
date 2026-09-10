from flask_socketio import SocketIO, emit, join_room
from server.state import state

ROOM = "watch_party"

def register_events(socketio: SocketIO):

    @socketio.on("connect")
    def on_connect():
        pass  # Room join deferred to viewer_join after capacity check

    @socketio.on("viewer_join")
    def on_viewer_join(data):
        from flask import request as req
        from config import MAX_VIEWERS

        if state.viewer_count() >= MAX_VIEWERS:
            emit("join_rejected", {"reason": f"Party is full (max {MAX_VIEWERS} viewers)."})
            return

        join_room(ROOM)  # Only join AFTER passing capacity check

        name = (data.get("name", "") or "Friend").strip()[:30]
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
        from flask import request as req
        ts = float(data.get("timestamp", 0))
        state.play(ts)
        # skip_sid so the sender doesn't receive their own echo
        socketio.emit("sync_play", {"timestamp": ts}, room=ROOM, skip_sid=req.sid)
        print(f"[PLAY]  timestamp={ts:.2f}s")

    @socketio.on("host_pause")
    def on_pause(data):
        from flask import request as req
        ts = float(data.get("timestamp", 0))
        state.pause(ts)
        socketio.emit("sync_pause", {"timestamp": ts}, room=ROOM, skip_sid=req.sid)
        print(f"[PAUSE] timestamp={ts:.2f}s")

    @socketio.on("host_seek")
    def on_seek(data):
        from flask import request as req
        ts = float(data.get("timestamp", 0))
        name = (data.get("name", "Someone") or "Someone").strip()[:30]
        state.seek(ts)
        socketio.emit("sync_seek", {"timestamp": ts, "name": name}, room=ROOM, skip_sid=req.sid)
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

    # NOTE: on_movie_changed handler removed — app.py emits movie_changed
    # directly, so a socket handler here would cause a double broadcast.

    @socketio.on("episode_request")
    def on_episode_request(data):
        from flask import request as req
        viewer_name = (data.get("viewer_name", "Someone") or "Someone").strip()[:30]
        file_name   = data.get("file_name", "")
        full_path   = data.get("full_path", "")
        print(f"[EPISODE] {viewer_name} requested: {file_name}")
        socketio.emit("episode_request", {
            "viewer_name": viewer_name,
            "file_name":   file_name,
            "full_path":   full_path,
        }, room=ROOM)

    @socketio.on("chat_message")
    def on_chat(data):
        name   = (data.get("name", "?") or "?").strip()[:30]
        text   = (data.get("text", "") or "").strip()[:300]
        time   = data.get("time", "")
        colour = data.get("colour", "#e8e8f0")

        if not text:
            return

        state.add_chat_message(name, text, time, colour)
        socketio.emit("chat_message", {
            "name": name, "text": text,
            "time": time, "colour": colour,
        }, room=ROOM)

    @socketio.on("typing_start")
    def on_typing_start(data):
        from flask import request as req
        name = (data.get("name", "Someone") or "Someone").strip()[:30]
        socketio.emit("user_typing", {"name": name}, room=ROOM, skip_sid=req.sid)

    @socketio.on("typing_stop")
    def on_typing_stop(data):
        from flask import request as req
        name = (data.get("name", "Someone") or "Someone").strip()[:30]
        socketio.emit("user_stopped_typing", {"name": name}, room=ROOM, skip_sid=req.sid)

    @socketio.on("ping_alive")
    def on_ping():
        emit("pong_alive")

    @socketio.on("subtitles_updated")
    def on_subtitles_updated():
        socketio.emit("subtitles_updated", room=ROOM)
