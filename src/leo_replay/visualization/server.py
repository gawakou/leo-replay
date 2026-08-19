from __future__ import annotations

import ipaddress
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .bundle import VisualizationError


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve_visualization_bundle(
    input_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    allow_remote: bool = False,
) -> None:
    root = input_dir.resolve()
    if not (root / "index.html").is_file():
        raise VisualizationError(f"visualization bundle has no index.html: {root}")
    if not 0 <= port <= 65535:
        raise VisualizationError("port must be between 0 and 65535")
    if not allow_remote and not _is_loopback(host):
        raise VisualizationError(
            "refusing a non-loopback host without --allow-remote; the server has no authentication"
        )

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer((host, port), handler)
    actual_port = int(server.server_address[1])
    url_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{url_host}:{actual_port}/"
    print(f"Serving {root} at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
