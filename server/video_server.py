import os
import subprocess
import json
import tempfile
import threading
import time
from flask import Blueprint, Response, request, abort
from server.state import state
from config import CHUNK_SIZE, SUPPORTED_FORMATS

video_bp = Blueprint("video", __name__)

BROWSER_SAFE_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac", "pcm_s16le", "pcm_s24le"}

# In-memory registry of active transcodes: path -> {"proc", "tmp_path", "done"}
_transcode_registry = {}
_transcode_lock = threading.Lock()


def get_mime_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return SUPPORTED_FORMATS.get(ext, "video/mp4")


def _probe_file(path: str) -> dict | None:
    try:
        from server.mediainfo import FFPROBE
        if not FFPROBE:
            return None
        result = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        return json.loads(result.stdout)
    except Exception:
        return None


def _get_audio_codec(probe_data: dict) -> str | None:
    for s in probe_data.get("streams", []):
        if s.get("codec_type") == "audio":
            return (s.get("codec_name") or "").lower()
    return None


def _needs_transcode(audio_codec: str | None) -> bool:
    if not audio_codec:
        return False
    return audio_codec not in BROWSER_SAFE_AUDIO


def _get_or_start_transcode(path: str) -> str | None:
    """
    Returns the path to the transcoded temp file for `path`.
    Starts a background ffmpeg transcode if one isn't already running.
    Blocks until the file has a valid moov atom (i.e. ffmpeg finished),
    then returns the path so it can be served with full range support.
    """
    from server.mediainfo import FFMPEG
    if not FFMPEG:
        return None

    cache_key = f"cinesync_{abs(hash(path))}.mp4"
    tmp_path  = os.path.join(tempfile.gettempdir(), cache_key)

    with _transcode_lock:
        entry = _transcode_registry.get(path)

        # Already fully transcoded and cached
        if entry and entry["done"] and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            return tmp_path

        # Already transcoding — wait below
        if entry and not entry["done"]:
            pass

        # Start a new transcode
        else:
            cmd = [
                FFMPEG, "-loglevel", "error",
                "-i", path,
                "-c:v", "copy",       # video: no re-encode
                "-c:a", "aac",        # audio: to AAC
                "-b:a", "192k",
                "-movflags", "+faststart",  # moov at front — makes it seekable
                "-y", tmp_path,
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _transcode_registry[path] = {"proc": proc, "tmp_path": tmp_path, "done": False}
            entry = _transcode_registry[path]

            # Background thread to mark done when ffmpeg exits
            def _watch(p, src):
                p["proc"].wait()
                p["done"] = True
                print(f"[VIDEO] Transcode complete: {src}")
            threading.Thread(target=_watch, args=(entry, path), daemon=True).start()

    # Wait for ffmpeg to finish (faststart requires full encode before moov is at front)
    print(f"[VIDEO] Waiting for transcode: {os.path.basename(path)}")
    timeout = 3600  # 1 hour max for very long movies
    elapsed = 0
    while elapsed < timeout:
        with _transcode_lock:
            e = _transcode_registry.get(path)
            if e and e["done"]:
                break
        time.sleep(1)
        elapsed += 1

    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
        return tmp_path
    return None


@video_bp.route("/video")
def stream_video():
    if not state.movie_path or not os.path.exists(state.movie_path):
        abort(404, "No movie loaded or file not found.")

    path        = state.movie_path
    file_size   = os.path.getsize(path)
    mime_type   = get_mime_type(path)
    range_hdr   = request.headers.get("Range", None)

    probe_data  = _probe_file(path)
    audio_codec = _get_audio_codec(probe_data) if probe_data else None

    if _needs_transcode(audio_codec):
        transcoded = _get_or_start_transcode(path)
        if transcoded:
            tc_size = os.path.getsize(transcoded)
            return _stream_raw(transcoded, tc_size, "video/mp4", range_hdr)
        # ffmpeg not available or failed — stream raw and let browser error
        return _stream_raw(path, file_size, mime_type, range_hdr)

    return _stream_raw(path, file_size, mime_type, range_hdr)


def _stream_raw(path: str, file_size: int, mime_type: str, range_header: str | None) -> Response:
    if not range_header:
        def generate_full():
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        yield chunk
            except OSError as e:
                print(f"[VIDEO] Read error: {e}")

        return Response(generate_full(), status=200, mimetype=mime_type, headers={
            "Content-Length": str(file_size),
            "Accept-Ranges":  "bytes",
            "Cache-Control":  "no-cache",
        })

    try:
        range_val  = range_header.replace("bytes=", "")
        parts      = range_val.split("-")
        byte_start = int(parts[0])
        byte_end   = int(parts[1]) if parts[1] else file_size - 1
    except Exception:
        abort(400, "Invalid Range header.")

    byte_end = min(byte_end, file_size - 1)
    if byte_start > byte_end:
        return Response(status=416, headers={"Content-Range": f"bytes */{file_size}"})

    byte_length = (byte_end - byte_start) + 1

    def generate_range():
        try:
            with open(path, "rb") as f:
                f.seek(byte_start)
                remaining = byte_length
                while remaining > 0:
                    chunk = f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        except OSError as e:
            print(f"[VIDEO] Read error: {e}")

    return Response(generate_range(), status=206, mimetype=mime_type, headers={
        "Content-Range":  f"bytes {byte_start}-{byte_end}/{file_size}",
        "Content-Length": str(byte_length),
        "Accept-Ranges":  "bytes",
        "Cache-Control":  "no-cache",
    })
