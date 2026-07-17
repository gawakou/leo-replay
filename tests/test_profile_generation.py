from pathlib import Path
import csv
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_profile_generation(tmp_path):
    output = tmp_path / "profile.csv"
    cmd = [
        sys.executable, str(ROOT / "scripts/profile/starlink_merge_realdata_to_profile.py"),
        "--ping", str(ROOT / "examples/raw/ping.csv"),
        "--iperf", str(ROOT / "examples/raw/iperf.json"),
        "--grpc", str(ROOT / "examples/raw/grpc.csv"),
        "--output", str(output), "--resample-sec", "0.5",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert set(["sec", "delay_ms", "jitter_ms", "loss_pct", "rate_mbit"]).issubset(rows[0])
    assert any(float(row["loss_pct"]) > 0 for row in rows)
