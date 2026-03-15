import threading

class PartyState:
    """
    Single source of truth for the watch party.
    All values are updated by sync_server and read by templates/clients.
    """
    def __init__(self):
        self._lock         = threading.Lock()
        self.movie_path    = None
        self.movie_name    = None
        self.subtitle_path = None
        self.is_playing    = False
        self.timestamp     = 0.0
        self.viewers       = {}     # { sid: { "name": str, "timestamp": float } }
        self.party_active  = False

    # ── Movie ──────────────────────────────────────────────────────────
    def set_movie(self, path: str):
        with self._lock:
            self.movie_path = path
            self.movie_name = path.split("\\")[-1].split("/")[-1]

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
    def add_viewer(self, sid: str, name: str):
        with self._lock:
            self.viewers[sid] = {"name": name, "timestamp": 0.0}

    def remove_viewer(self, sid: str):
        with self._lock:
            self.viewers.pop(sid, None)

    def update_viewer_timestamp(self, sid: str, timestamp: float):
        with self._lock:
            if sid in self.viewers:
                self.viewers[sid]["timestamp"] = timestamp

    def viewer_count(self) -> int:
        return len(self.viewers)

    def viewer_names(self) -> list:
        return [v["name"] for v in self.viewers.values()]

    def viewers_with_timestamp(self) -> list:
        return [
            {"name": v["name"], "timestamp": v["timestamp"]}
            for v in self.viewers.values()
        ]

    # ── Snapshot for new joiners ───────────────────────────────────────
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "timestamp":     self.timestamp,
                "is_playing":    self.is_playing,
                "movie_name":    self.movie_name,
                "has_subtitles": self.subtitle_path is not None,
            }


# Global singleton — imported everywhere
state = PartyState()