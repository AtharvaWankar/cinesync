"""
Extracts real technical stats from the currently loaded media file using
ffprobe (part of the ffmpeg suite). Used to power the "Stats for Nerds"
panel on the viewer page.

Results are cached per file path (in state) since ffprobe takes a moment
on large MKVs and the info never changes for a given file.
"""

import json
import os
import platform
import shutil
import subprocess
import threading

def _find_ffprobe() -> str | None:
    """Look on PATH first, then common install locations ffmpeg installers
    use but sometimes forget to add to PATH (esp. on Windows)."""
    found = shutil.which("ffprobe")
    if found:
        return found

    candidates = []
    if platform.system() == "Windows":
        exe = "ffprobe.exe"
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            r"C:\ffmpeg\bin\ffprobe.exe",
            r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffprobe.exe",
            os.path.join(local, "Microsoft", "WinGet", "Packages"),  # scanned below
            os.path.expanduser(r"~\scoop\shims\ffprobe.exe"),
            os.path.expanduser(r"~\AppData\Local\Programs\ffmpeg\bin\ffprobe.exe"),
        ]
        # WinGet installs ffmpeg into a versioned subfolder — scan for it.
        winget_root = os.path.join(local, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget_root):
            for entry in os.listdir(winget_root):
                if "ffmpeg" in entry.lower():
                    for root, _dirs, files in os.walk(os.path.join(winget_root, entry)):
                        if exe in files:
                            candidates.append(os.path.join(root, exe))
    else:
        candidates = [
            "/usr/bin/ffprobe", "/usr/local/bin/ffprobe",
            "/opt/homebrew/bin/ffprobe", "/snap/bin/ffprobe",
        ]

    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


FFPROBE = _find_ffprobe()

_cache_lock = threading.Lock()
_cache = {}   # path -> parsed info dict


def _run_ffprobe(path: str) -> dict | None:
    """Run ffprobe -show_format -show_streams and return raw JSON, or None."""
    if not FFPROBE:
        return None
    try:
        result = subprocess.run(
            [
                FFPROBE, "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                path,
            ],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[MEDIAINFO] ffprobe failed: {e}")
        return None


def _fps_from_rate(rate_str: str | None) -> float | None:
    """ffprobe gives frame rate as 'num/den' (e.g. '24000/1001')."""
    if not rate_str or rate_str == "0/0":
        return None
    try:
        num, den = rate_str.split("/")
        num, den = float(num), float(den)
        return round(num / den, 3) if den else None
    except Exception:
        return None


def _friendly_fps(fps: float | None) -> str | None:
    if fps is None:
        return None
    common = {
        23.976: "23.976", 24.0: "24", 25.0: "25",
        29.97: "29.97", 30.0: "30", 50.0: "50",
        59.94: "59.94", 60.0: "60",
    }
    for val, label in common.items():
        if abs(fps - val) < 0.02:
            return label
    return str(round(fps, 3))


def _video_codec_name(codec: str | None) -> str:
    mapping = {
        "hevc": "HEVC (H.265)", "h264": "H.264 (AVC)", "av1": "AV1",
        "vp9": "VP9", "vp8": "VP8", "mpeg4": "MPEG-4",
        "mpeg2video": "MPEG-2",
    }
    return mapping.get((codec or "").lower(), (codec or "Unknown").upper())


def _audio_codec_name(codec: str | None) -> str:
    mapping = {
        "eac3": "E-AC-3 (Dolby Digital+)", "ac3": "AC-3 (Dolby Digital)",
        "truehd": "Dolby TrueHD", "dts": "DTS", "dca": "DTS",
        "aac": "AAC", "flac": "FLAC", "opus": "Opus",
        "mp3": "MP3", "pcm_s16le": "PCM", "pcm_s24le": "PCM",
    }
    return mapping.get((codec or "").lower(), (codec or "Unknown").upper())


def _chroma_from_pix_fmt(pix_fmt: str | None) -> tuple[str | None, str | None]:
    """Returns (chroma_subsampling, bit_depth) guessed from ffprobe pix_fmt."""
    if not pix_fmt:
        return None, None
    pf = pix_fmt.lower()
    bit_depth = "10-bit" if "10" in pf else ("12-bit" if "12" in pf else "8-bit")
    if "444" in pf:
        chroma = "4:4:4"
    elif "422" in pf:
        chroma = "4:2:2"
    elif "420" in pf or "nv12" in pf or "yuv" in pf:
        chroma = "4:2:0"
    else:
        chroma = None
    return chroma, bit_depth


def _detect_hdr(video_stream: dict) -> str:
    transfer = (video_stream.get("color_transfer") or "").lower()
    side_data = video_stream.get("side_data_list") or []

    has_dovi = any(
        "dolby vision" in str(sd.get("side_data_type", "")).lower()
        or "dovi" in str(sd.get("side_data_type", "")).lower()
        for sd in side_data
    )
    has_hdr10plus = any(
        "hdr10+" in str(sd.get("side_data_type", "")).lower()
        or "hdr_dynamic_metadata" in str(sd.get("side_data_type", "")).lower()
        for sd in side_data
    )

    if has_dovi:
        return "Dolby Vision"
    if has_hdr10plus:
        return "HDR10+"
    if transfer in ("smpte2084", "smpte-2084"):
        return "HDR10"
    if transfer in ("arib-std-b67", "arib-std-b67 (hlg)"):
        return "HLG"
    return "SDR"


def _color_space(video_stream: dict) -> str | None:
    cs = (video_stream.get("color_space") or video_stream.get("color_primaries") or "").lower()
    if "bt2020" in cs or "2020" in cs:
        return "BT.2020"
    if "bt709" in cs or "709" in cs:
        return "BT.709"
    if "smpte170" in cs or "bt601" in cs:
        return "BT.601"
    return None


def _bytes_to_bitrate_str(bits_per_sec) -> str | None:
    try:
        bits_per_sec = float(bits_per_sec)
    except (TypeError, ValueError):
        return None
    mbps = bits_per_sec / 1_000_000
    if mbps >= 1:
        return f"{mbps:.2f} Mbps"
    return f"{bits_per_sec / 1000:.0f} kbps"


def redetect() -> bool:
    """Re-scan for ffprobe without restarting the server (e.g. user just
    installed ffmpeg). Returns True if it's now available."""
    global FFPROBE
    FFPROBE = _find_ffprobe()
    return FFPROBE is not None


def probe(path: str, force: bool = False) -> dict:
    """
    Returns a dict of human-friendly media info for `path`.
    Cached — repeated calls for the same path are free. Pass force=True
    to bypass the cache (e.g. after installing ffmpeg mid-session).
    """
    with _cache_lock:
        cached = None if force else _cache.get(path)
    if cached is not None:
        return cached

    info = {
        "available": FFPROBE is not None,
        "file_name": os.path.basename(path) if path else None,
        "file_size_bytes": None,
        "container": None,
        "overall_bitrate": None,
        "video": None,
        "audio": [],
        "error": None,
    }

    if not FFPROBE:
        hint = {
            "Windows": "winget install ffmpeg  (or choco install ffmpeg)",
            "Darwin":  "brew install ffmpeg",
        }.get(platform.system(), "sudo apt install ffmpeg  (or your distro's package manager)")
        info["error"] = f"ffprobe not found on this system — install it with: {hint}"
        with _cache_lock:
            _cache[path] = info
        return info

    if not path or not os.path.isfile(path):
        info["error"] = "File not found."
        return info

    raw = _run_ffprobe(path)
    if raw is None:
        info["error"] = "Could not read media info for this file."
        with _cache_lock:
            _cache[path] = info
        return info

    fmt = raw.get("format", {}) or {}
    streams = raw.get("streams", []) or []

    info["file_size_bytes"] = int(fmt["size"]) if fmt.get("size") else os.path.getsize(path)
    info["container"] = (fmt.get("format_long_name") or fmt.get("format_name") or "").split(",")[0] or None
    info["overall_bitrate"] = _bytes_to_bitrate_str(fmt.get("bit_rate"))

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if video_stream:
        fps = _fps_from_rate(video_stream.get("avg_frame_rate")) or _fps_from_rate(video_stream.get("r_frame_rate"))
        chroma, bit_depth = _chroma_from_pix_fmt(video_stream.get("pix_fmt"))
        v_bitrate = video_stream.get("bit_rate") or fmt.get("bit_rate")

        info["video"] = {
            "codec": _video_codec_name(video_stream.get("codec_name")),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "resolution": f'{video_stream.get("width")}×{video_stream.get("height")}' if video_stream.get("width") else None,
            "fps": _friendly_fps(fps),
            "hdr": _detect_hdr(video_stream),
            "color_space": _color_space(video_stream),
            "bit_depth": bit_depth,
            "chroma_subsampling": chroma,
            "bitrate": _bytes_to_bitrate_str(v_bitrate),
            "pix_fmt": video_stream.get("pix_fmt"),
        }

    for a in audio_streams:
        info["audio"].append({
            "codec": _audio_codec_name(a.get("codec_name")),
            "channels": a.get("channels"),
            "channel_layout": a.get("channel_layout"),
            "sample_rate": f'{int(a["sample_rate"]) / 1000:g} kHz' if a.get("sample_rate") else None,
            "bit_depth": a.get("bits_per_raw_sample") and f'{a["bits_per_raw_sample"]}-bit',
            "bitrate": _bytes_to_bitrate_str(a.get("bit_rate")),
            "language": (a.get("tags") or {}).get("language"),
            "title": (a.get("tags") or {}).get("title"),
            "is_default": (a.get("disposition") or {}).get("default") == 1,
            "atmos": "atmos" in str((a.get("tags") or {}).get("title", "")).lower()
                     or "atmos" in str((a.get("profile") or "")).lower(),
        })

    with _cache_lock:
        _cache[path] = info
    return info


def clear_cache():
    with _cache_lock:
        _cache.clear()
