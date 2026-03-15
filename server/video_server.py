import os
from flask import Blueprint, Response, request, abort
from server.state import state
from config import CHUNK_SIZE, SUPPORTED_FORMATS

video_bp = Blueprint("video", __name__)


def get_mime_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return SUPPORTED_FORMATS.get(ext, "video/mp4")


@video_bp.route("/video")
def stream_video():
    """
    Stream the movie file using HTTP Range Requests.
    This is how browsers natively stream video — they ask for byte ranges
    so they can seek, buffer ahead, and play without downloading the whole file.
    """
    if not state.movie_path or not os.path.exists(state.movie_path):
        abort(404, "No movie loaded or file not found.")

    file_size = os.path.getsize(state.movie_path)
    mime_type = get_mime_type(state.movie_path)

    range_header = request.headers.get("Range", None)

    # ── No Range header: send the whole file (rarely happens with video) ──
    if not range_header:
        def generate_full():
            with open(state.movie_path, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    yield chunk

        return Response(
            generate_full(),
            status=200,
            mimetype=mime_type,
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
            }
        )

    # ── Parse Range header: "bytes=START-END" ─────────────────────────
    try:
        range_val  = range_header.replace("bytes=", "")
        parts      = range_val.split("-")
        byte_start = int(parts[0])
        byte_end   = int(parts[1]) if parts[1] else file_size - 1
    except Exception:
        abort(400, "Invalid Range header.")

    byte_end    = min(byte_end, file_size - 1)
    byte_length = (byte_end - byte_start) + 1

    def generate_range():
        with open(state.movie_path, "rb") as f:
            f.seek(byte_start)
            remaining = byte_length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return Response(
        generate_range(),
        status=206,
        mimetype=mime_type,
        headers={
            "Content-Range":  f"bytes {byte_start}-{byte_end}/{file_size}",
            "Content-Length": str(byte_length),
            "Accept-Ranges":  "bytes",
        }
    )