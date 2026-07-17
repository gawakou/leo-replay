import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_calibrate_v1_event_profile(tmp_path):
    output = tmp_path / "calibrated.json"
    command = [
        sys.executable,
        str(ROOT / "scripts/replay/calibrate_event_delay.py"),
        "--events-json",
        str(ROOT / "examples/events-v1.example.json"),
        "--out-json",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    event = data["events"][0]
    assert event["calibration"]["calibrated_delay_ms"] == 45.0
    assert event["parameters"]["delay_ms"] == 45.0
