import os
import random
import threading
from collections import deque

COLOUR_PALETTE = [
    "#7c6ff7",
    "#4caf6e",
    "#e05252",
    "#f0a500",
    "#29b6f6",
    "#f06292",
    "#80cbc4",
    "#ffb74d",
    "#ce93d8",
    "#80deea",
]

class PartyState:
    def __init__(self):
        self._lock         = threading.Lock()
        self.movie_path    = None
        self.movie_name    = None
        self.subtitle_path = None
        self.is_playing    = False
        self.timestamp     = 0.0
        self.viewers       = {}
        self.party_active  = False
        self.chat_history  = deque(maxlen=100)
        self._used_colours = []
        self.manual_tailscale_ip = None
        self.library_root  = None

    # ── Network override ──────────────────────────────────────────────
    def set_manual_ip(self, ip: str | None):
        with self._lock:
            self.manual_tailscale_ip = ip or None

    # ── Library ────────────────────────────────────────────────────────
    def set_library_root(self, path: str):
        with self._lock:
            self.library_root = path

    # ── Movie ──────────────────────────────────────────────────────────
    def set_movie(self, path: str):
        with self._lock:
            self.movie_path = path
            self.movie_name = os.path.basename(path)  # cross-platform filename
            self.timestamp  = 0.0
            self.is_playing = False
            for sid in self.viewers:
                self.viewers[sid]["timestamp"] = 0.0

    # ── Subtitles ──────────────────────────────────────────────────────
    def set_subtitle(self, path: str):
        with self._lock:
            self.subtitle_path = path

    def clear_subtitle(self):
        with self._lock:
            self.subtitle_path = None

    # ── Playback ───────────────────────────────────────────────────────
    def play(self, timestamp: float):
        with self._lock:
            self.is_playing = True
            self.timestamp  = timestamp

    def pause(self, timestamp: float):
        with self._lock:
            self.is_playing = False
            self.timestamp  = timestamp

    def seek(self, timestamp: float):
        with self._lock:
            self.timestamp = timestamp

    # ── Viewers ────────────────────────────────────────────────────────
    def _assign_colour(self) -> str:
        available = [c for c in COLOUR_PALETTE if c not in self._used_colours]
        if not available:
            available = list(COLOUR_PALETTE)  # all used — reset pool
        colour = random.choice(available)
        self._used_colours.append(colour)
        return colour

    def add_viewer(self, sid: str, name: str):
        with self._lock:
            colour = self._assign_colour()
            self.viewers[sid] = {"name": name, "timestamp": 0.0, "colour": colour}

    def remove_viewer(self, sid: str):
        with self._lock:
            viewer = self.viewers.pop(sid, None)
            if viewer and viewer["colour"] in self._used_colours:
                self._used_colours.remove(viewer["colour"])

    def update_viewer_timestamp(self, sid: str, timestamp: float):
        with self._lock:
            if sid in self.viewers:
                self.viewers[sid]["timestamp"] = timestamp

    def get_viewer_colour(self, sid: str) -> str:
        with self._lock:
            return self.viewers.get(sid, {}).get("colour", "#e8e8f0")

    def viewer_count(self) -> int:
        with self._lock:
            return len(self.viewers)

    def viewer_names(self) -> list:
        with self._lock:
            return [v["name"] for v in self.viewers.values()]

    def viewers_with_timestamp(self) -> list:
        with self._lock:
            return [
                {"name": v["name"], "timestamp": v["timestamp"], "colour": v["colour"]}
                for v in self.viewers.values()
            ]

    # ── Chat history ───────────────────────────────────────────────────
    def add_chat_message(self, name: str, text: str, time: str, colour: str):
        with self._lock:
            self.chat_history.append({
                "name": name, "text": text,
                "time": time, "colour": colour,
            })
            # deque(maxlen=100) automatically drops oldest — no manual trim needed

    def get_chat_history(self) -> list:
        with self._lock:
            return list(self.chat_history)

    # ── Snapshot for new joiners ───────────────────────────────────────
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "timestamp":     self.timestamp,
                "is_playing":    self.is_playing,
                "movie_name":    self.movie_name,
                "has_subtitles": self.subtitle_path is not None,
            }


state = PartyState()
