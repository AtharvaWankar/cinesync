import os
import subprocess
import json
from flask import Blueprint, Response, request, abort
from server.state import state
from config import CHUNK_SIZE, SUPPORTED_FORMATS

video_bp = Blueprint("video", __name__)

# Audio codecs browsers can decode natively — no transcoding needed
BROWSER_SAFE_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac", "pcm_s16le", "pcm_s24le"}


def get_mime_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return SUPPORTED_FORMATS.get(ext, "video/mp4")


def _probe_file(path: str) -> dict | None:
    """
    Run ffprobe on the file and return raw JSON.
    Returns None if ffprobe is unavailable or fails.
    """
    try:
        from server.mediainfo import FFPROBE
        if not FFPROBE:
            return None
        result = subprocess.run(
            [
                FFPROBE, "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        return json.loads(result.stdout)
    except Exception:
        return None


def _get_audio_codec(probe_data: dict) -> str | None:
    """Return the codec_name of the first audio stream."""
    for s in probe_data.get("streams", []):
        if s.get("codec_type") == "audio":
            return (s.get("codec_name") or "").lower()
    return None


def _get_duration(probe_data: dict) -> float | None:
    """Return total duration in seconds from format or video stream."""
    try:
        dur = probe_data.get("format", {}).get("duration")
        if dur:
            return float(dur)
    except Exception:
        pass
    for s in probe_data.get("streams", []):
        if s.get("codec_type") == "video":
            try:
                return float(s["duration"])
            except Exception:
                pass
    return None


def _needs_transcode(audio_codec: str | None) -> bool:
    if not audio_codec:
        return False
    return audio_codec not in BROWSER_SAFE_AUDIO


def _byte_offset_to_seconds(byte_offset: int, file_size: int, duration: float) -> float:
    """
    Convert a byte offset to an approximate timestamp in seconds.
    Uses linear interpolation based on file size and total duration.
    This is accurate enough for seeking — ffmpeg will align to the
    nearest keyframe anyway.
    """
    if file_size <= 0 or duration <= 0:
        return 0.0
    ratio = byte_offset / file_size
    return round(ratio * duration, 3)


@video_bp.route("/video")
def stream_video():
    """
    Stream the movie file using HTTP Range Requests.
    For browser-compatible audio: raw byte streaming (zero overhead).
    For incompatible audio (EAC3/AC3/DTS/TrueHD): on-the-fly ffmpeg
    transcode with seekable Range support via timestamp-based -ss seeking.
    """
    if not state.movie_path or not os.path.exists(state.movie_path):
        abort(404, "No movie loaded or file not found.")

    path         = state.movie_path
    file_size    = os.path.getsize(path)
    mime_type    = get_mime_type(path)
    range_header = request.headers.get("Range", None)

    # Probe the file once (mediainfo module caches this per path)
    probe_data   = _probe_file(path)
    audio_codec  = _get_audio_codec(probe_data) if probe_data else None
    needs_xcode  = _needs_transcode(audio_codec)

    if needs_xcode:
        duration = _get_duration(probe_data) if probe_data else None
        return _stream_transcoded(path, file_size, duration, range_header)

    return _stream_raw(path, file_size, mime_type, range_header)


# ── Transcoded streaming (EAC3 / AC3 / DTS / TrueHD → AAC) ───────────────────

def _stream_transcoded(path: str, file_size: int, duration: float | None, range_header: str | None) -> Response:
    """
    Transcode audio to AAC on the fly via ffmpeg.

    Seeking works by converting the browser's byte Range offset to a
    timestamp using linear interpolation, then passing it to ffmpeg's
    input-side -ss flag. ffmpeg snaps to the nearest keyframe — fast,
    no full decode from the start.

    The response uses fragmented MP4 (fMP4) so the browser can start
    playing immediately without a complete file being present.
    """
    from server.mediainfo import FFMPEG
    if not FFMPEG:
        # ffmpeg missing — fall back to raw stream
        mime_type = get_mime_type(path)
        return _stream_raw(path, file_size, mime_type, range_header)

    # Work out the seek timestamp from the Range header
    seek_seconds = 0.0
    byte_start   = 0

    if range_header and duration:
        try:
            range_val  = range_header.replace("bytes=", "")
            parts      = range_val.split("-")
            byte_start = int(parts[0])
            if byte_start > 0:
                seek_seconds = _byte_offset_to_seconds(byte_start, file_size, duration)
        except Exception:
            seek_seconds = 0.0
            byte_start   = 0

    def generate():
        cmd = [
            FFMPEG,
            "-loglevel", "error",
        ]

        # Input-side seek — fast keyframe seek before decoding starts.
        # This is the key to making random seeking work with transcoding.
        if seek_seconds > 0:
            cmd += ["-ss", str(seek_seconds)]

        cmd += [
            "-i", path,
            "-c:v", "copy",          # video: no re-encode, zero quality loss
            "-c:a", "aac",           # audio: transcode to AAC
            "-b:a", "192k",
            "-movflags", "frag_keyframe+empty_moov+faststart",  # fMP4 for streaming
            "-f", "mp4",
            "pipe:1",
        ]

        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
            while True:
                chunk = proc.stdout.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        except GeneratorExit:
            # Client disconnected (seek, tab close) — kill immediately
            if proc:
                proc.kill()
        except OSError as e:
            print(f"[VIDEO] Transcode read error: {e}")
        finally:
            if proc:
                try:
                    proc.stdout.close()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    # For transcoded streams we return 200 (not 206) because the byte
    # range no longer maps 1:1 to the output — the browser is fine with
    # this for fMP4 streams. The Accept-Ranges header is omitted
    # intentionally so the browser doesn't try to issue sub-range requests
    # that we can't honour byte-accurately.
    status = 206 if (range_header and byte_start > 0) else 200

    return Response(
        generate(),
        status=status,
        mimetype="video/mp4",
        headers={
            "Cache-Control": "no-cache",
            "X-Transcoded":  "1",
            # Tell the browser this is a valid partial response so it
            # treats it as seekable even though we're doing timestamp seeks
            **({"Content-Range": f"bytes {byte_start}-{file_size - 1}/{file_size}",
                "Content-Length": str(file_size - byte_start)}
               if (range_header and byte_start > 0) else
               {"Content-Length": str(file_size)}),
        }
    )


# ── Raw streaming (AAC / MP3 / Opus — browser-compatible, zero overhead) ──────

def _stream_raw(path: str, file_size: int, mime_type: str, range_header: str | None) -> Response:
    """Standard HTTP Range Request streaming for browser-compatible files."""

    if not range_header:
        def generate_full():
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        yield chunk
            except OSError as e:
                print(f"[VIDEO] Read error: {e}")

        return Response(
            generate_full(),
            status=200,
            mimetype=mime_type,
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges":  "bytes",
                "Cache-Control":  "no-cache",
            }
        )

    try:
        range_val  = range_header.replace("bytes=", "")
        parts      = range_val.split("-")
        byte_start = int(parts[0])
        byte_end   = int(parts[1]) if parts[1] else file_size - 1
    except Exception:
        abort(400, "Invalid Range header.")

    byte_end = min(byte_end, file_size - 1)

    if byte_start > byte_end:
        return Response(
            status=416,
            headers={"Content-Range": f"bytes */{file_size}"}
        )

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

    return Response(
        generate_range(),
        status=206,
        mimetype=mime_type,
        headers={
            "Content-Range":  f"bytes {byte_start}-{byte_end}/{file_size}",
            "Content-Length": str(byte_length),
            "Accept-Ranges":  "bytes",
            "Cache-Control":  "no-cache",
        }
    )
