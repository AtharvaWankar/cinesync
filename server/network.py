import socket
import subprocess
import platform

def get_tailscale_ip() -> str | None:
    """
    Try to find the Tailscale IP (always in the 100.x.x.x range).
    Works on Windows and Linux/Mac.
    """
    # Method 1: scan all network interfaces for a 100.x.x.x address
    try:
        import socket
        hostname = socket.gethostname()
        all_ips  = socket.getaddrinfo(hostname, None)
        for item in all_ips:
            ip = item[4][0]
            if ip.startswith("100."):
                return ip
    except Exception:
        pass

    # Method 2: parse `tailscale ip` CLI output (Windows / Linux / Mac)
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=3
        )
        ip = result.stdout.strip()
        if ip.startswith("100."):
            return ip
    except Exception:
        pass

    # Method 3: connect a UDP socket outward — returns the preferred local IP
    # (fallback: might be LAN IP, not Tailscale, but still useful for local testing)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip.startswith("100."):
            return ip
        return ip  # Return LAN IP as last resort
    except Exception:
        return None


def get_watch_url(port: int) -> str:
    ip = get_tailscale_ip()
    if ip:
        return f"http://{ip}:{port}/watch"
    return f"http://YOUR_TAILSCALE_IP:{port}/watch"
