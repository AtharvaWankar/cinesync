import os
import subprocess
from flask import Blueprint, Response, request, abort
from server.state import state
from config import CHUNK_SIZE, SUPPORTED_FORMATS

video_bp = Blueprint("video", __name__)

# Audio codecs browsers can decode natively — no transcoding needed.
# EAC3, AC3, TrueHD, DTS are all unsupported across Chrome/Firefox/Edge.
BROWSER_SAFE_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac", "pcm_s16le", "pcm_s24le"}


def get_mime_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return SUPPORTED_FORMATS.get(ext, "video/mp4")


def _probe_audio_codec(path: str) -> str | None:
    """Return the codec_name of the first audio stream, or None."""
    try:
        from server.mediainfo import FFPROBE
        if not FFPROBE:
            return None
        result = subprocess.run(
            [
                FFPROBE, "-v", "quiet",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name",
                "-print_format", "json",
                path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        import json
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if streams:
            return streams[0].get("codec_name", "").lower()
    except Exception:
        pass
    return None


def _needs_transcode(path: str) -> bool:
    """True if the file's audio codec is not natively supported by browsers."""
    codec = _probe_audio_codec(path)
    if not codec:
        return False  # can't determine — attempt raw stream, browser will tell us
    return codec not in BROWSER_SAFE_AUDIO


@video_bp.route("/video")
def stream_video():
    """
    Stream the movie file using HTTP Range Requests.
    If the file has an unsupported audio codec (e.g. EAC3, AC3, TrueHD,
    DTS), the audio is transcoded to AAC on-the-fly via ffmpeg. Video is
    always copied directly without re-encoding — no quality loss, minimal
    CPU overhead. Raw streaming is used when the audio is already
    browser-compatible.
    """
    if not state.movie_path or not os.path.exists(state.movie_path):
        abort(404, "No movie loaded or file not found.")

    # ── Transcoded path (EAC3 / AC3 / DTS / TrueHD → AAC) ────────────
    if _needs_transcode(state.movie_path):
        return _stream_transcoded(state.movie_path)

    # ── Raw streaming path (AAC / MP3 / Opus etc — no transcode) ──────
    return _stream_raw(state.movie_path)


def _stream_transcoded(path: str) -> Response:
    """
    Pipe the file through ffmpeg, copying video and transcoding audio to
    AAC. Streams the output as video/mp4 using fragmented MP4 (fMP4) so
    the browser can play it as a progressive stream without needing a
    complete file first.

    Range seeking is not supported in this mode — the browser will play
    from the beginning. Seeking still works because the browser sends a
    seek event and the video element updates currentTime client-side;
    precise byte-level seeking into a live transcode stream is not
    possible without pre-processing the file.
    """
    from server.mediainfo import FFMPEG
    if not FFMPEG:
        # ffmpeg not available — fall back to raw stream and let the
        # browser fail gracefully with its own codec error
        return _stream_raw(path)

    def generate():
        cmd = [
            FFMPEG,
            "-loglevel", "error",
            "-i", path,
            "-c:v", "copy",       # video: no re-encode, zero quality loss
            "-c:a", "aac",        # audio: transcode to AAC (universally supported)
            "-b:a", "192k",       # audio bitrate — transparent quality
            "-movflags", "frag_keyframe+empty_moov+faststart",  # fMP4 for streaming
            "-f", "mp4",
            "pipe:1",             # write to stdout
        ]
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
            # Client disconnected (seek, tab close, etc.) — kill the process
            proc.kill()
        except OSError as e:
            print(f"[VIDEO] Transcode read error: {e}")
        finally:
            try:
                proc.stdout.close()
                proc.wait(timeout=2)
            except Exception:
                pass

    return Response(
        generate(),
        status=200,
        mimetype="video/mp4",
        headers={
            "Cache-Control":  "no-cache",
            "X-Transcoded":   "1",  # useful for debugging in browser devtools
        }
    )


def _stream_raw(path: str) -> Response:
    """Standard HTTP Range Request streaming for browser-compatible files."""
    file_size    = os.path.getsize(path)
    mime_type    = get_mime_type(path)
    range_header = request.headers.get("Range", None)

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
