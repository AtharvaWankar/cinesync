import threading

class PartyState:
    """
    Single source of truth for the watch party.
    All values are updated by sync_server and read by templates/clients.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.movie_path   = None   # Absolute path to movie file on host disk
        self.movie_name   = None   # Just the filename for display
        self.is_playing   = False
        self.timestamp    = 0.0    # Current playback position in seconds
        self.viewers      = {}     # { sid: { "name": str } }
        self.party_active = False

    # ── Movie ──────────────────────────────────────────────────────────
    def set_movie(self, path: str):
        with self._lock:
            self.movie_path = path
            self.movie_name = path.split("\\")[-1].split("/")[-1]

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
            self.viewers[sid] = {"name": name}

    def remove_viewer(self, sid: str):
        with self._lock:
            self.viewers.pop(sid, None)

    def viewer_count(self) -> int:
        return len(self.viewers)

    def viewer_names(self) -> list:
        return [v["name"] for v in self.viewers.values()]

    # ── Snapshot for new joiners ───────────────────────────────────────
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "timestamp":  self.timestamp,
                "is_playing": self.is_playing,
                "movie_name": self.movie_name,
            }


# Global singleton — imported everywhere
state = PartyState()
