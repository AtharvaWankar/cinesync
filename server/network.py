import json
import os
import re
import shutil
import socket
import subprocess
import platform

# Tailscale hands out addresses from the CGNAT range 100.64.0.0/10
# (100.64.x.x – 100.127.x.x). Matching the full range instead of a bare
# "100." prefix avoids false positives from other 100.x networks while
# still catching every real Tailscale IP.
_TAILSCALE_RE = re.compile(r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b")


def _is_tailscale_ip(ip: str) -> bool:
    return bool(_TAILSCALE_RE.fullmatch(ip))


def _find_tailscale_binary() -> str | None:
    """Locate the tailscale CLI, including common install paths that
    aren't always on PATH (this is the #1 reason detection used to fail)."""
    found = shutil.which("tailscale")
    if found:
        return found

    candidates = []
    system = platform.system()
    if system == "Windows":
        candidates += [
            os.path.expandvars(r"%ProgramFiles%\Tailscale\tailscale.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Tailscale\tailscale.exe"),
        ]
    elif system == "Darwin":
        candidates += [
            "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
            "/usr/local/bin/tailscale",
            "/opt/homebrew/bin/tailscale",
        ]
    else:  # Linux
        candidates += ["/usr/bin/tailscale", "/usr/local/bin/tailscale"]

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _via_cli() -> str | None:
    """Ask the tailscale CLI directly — most reliable when it works."""
    binary = _find_tailscale_binary()
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "ip", "-4"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if _is_tailscale_ip(line):
                return line
    except Exception:
        pass

    # Fall back to `tailscale status --json`, which works even in setups
    # where `tailscale ip` is restricted.
    try:
        result = subprocess.run(
            [binary, "status", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        data = json.loads(result.stdout)
        for ip in (data.get("Self", {}).get("TailscaleIPs") or []):
            if _is_tailscale_ip(ip):
                return ip
    except Exception:
        pass
    return None


def _via_interface_listing() -> str | None:
    """Scan the machine's actual network interfaces for a 100.64.0.0/10
    address. This is OS-native and doesn't depend on the tailscale CLI
    being installed, on PATH, or reachable — it just reads the adapter
    Tailscale creates, the same way `ipconfig`/`ifconfig`/`ip addr` would
    show it to a human."""
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5).stdout
        elif system == "Darwin":
            out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5).stdout
        else:
            out = subprocess.run(["ip", "addr"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None

    for match in _TAILSCALE_RE.finditer(out):
        return match.group(0)
    return None


def _via_socket_scan() -> str | None:
    """Last resort: ask the OS resolver for every address tied to this
    hostname. Weaker than the methods above (often misses virtual
    adapters) but cheap and occasionally catches what they don't."""
    try:
        hostname = socket.gethostname()
        for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            ip = sockaddr[0]
            if _is_tailscale_ip(ip):
                return ip
    except Exception:
        pass
    return None


def get_tailscale_ip() -> str | None:
    """
    Try, in order of reliability: the tailscale CLI, then reading the
    OS's own interface list (works even if the CLI isn't on PATH), then
    a socket-based scan as a last resort. Returns None if none find one
    — the host can still set the watch URL manually in that case.
    """
    for method in (_via_cli, _via_interface_listing, _via_socket_scan):
        ip = method()
        if ip:
            return ip
    return None


def get_watch_url(port: int, override_ip: str | None = None) -> str:
    ip = override_ip or get_tailscale_ip()
    if ip:
        return f"http://{ip}:{port}/watch"
    return f"http://<your-tailscale-ip>:{port}/watch"
