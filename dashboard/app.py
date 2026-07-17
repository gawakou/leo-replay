\
#!/usr/bin/env python3
from __future__ import annotations

import math
import os
import threading
import time

from flask import Flask, jsonify, send_from_directory

app = Flask(__name__, static_folder="static")
state_lock = threading.Lock()
running = False
start_time: float | None = None


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/start", methods=["POST"])
def start():
    global running, start_time
    with state_lock:
        running = True
        start_time = time.time()
    return jsonify({"ok": True, "status": "running"})


@app.route("/api/stop", methods=["POST"])
def stop():
    global running
    with state_lock:
        running = False
    return jsonify({"ok": True, "status": "stopped"})


@app.route("/api/status")
def status():
    with state_lock:
        is_running = running
        st = start_time

    if not is_running or st is None:
        return jsonify({"running": False, "target": "-", "protocol": "UDP",
                        "time_sec": 0.0, "duration_sec": 300.0, "rate_mbps": 0.0,
                        "delay_ms": 0.0, "loss_pct": 0.0, "state": "IDLE"})

    t = (time.time() - st) % 300.0
    # Prototype only: replace with profile/event state in a future version.
    delay = 20.0 + 35.0 * (0.5 + 0.5 * math.sin(t / 18.0))
    rate = 10.0 + 5.0 * (0.5 + 0.5 * math.sin(t / 9.0))
    if delay >= 50.0:
        loss, net_state = 1.2, "CONGESTED"
    elif delay >= 35.0:
        loss, net_state = 0.3, "DEGRADED"
    else:
        loss, net_state = 0.0, "NORMAL"

    return jsonify({"running": True, "target": "demo_profile_10M", "protocol": "UDP",
                    "time_sec": round(t, 1), "duration_sec": 300.0,
                    "rate_mbps": round(rate, 2), "delay_ms": round(delay, 1),
                    "loss_pct": round(loss, 2), "state": net_state})


if __name__ == "__main__":
    host = os.getenv("LEO_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("LEO_DASHBOARD_PORT", "5000"))
    debug = os.getenv("LEO_DASHBOARD_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)
