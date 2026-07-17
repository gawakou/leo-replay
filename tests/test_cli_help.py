from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLI_SCRIPTS = [
    ROOT / "scripts/profile/iperf_ping_grpc_to_event_profile.py",
    ROOT / "scripts/profile/starlink_merge_realdata_to_profile.py",
    ROOT / "scripts/replay/tc_csv_replay.py",
    ROOT / "scripts/replay/tc_event_replay_calibrated.py",
    ROOT / "scripts/evaluation/compare_measure_vs_replay.py",
    ROOT / "scripts/orchestration/run_remote_measurement.py",
]


def test_cli_help(tmp_path):
    env = dict(os.environ)
    env["MPLCONFIGDIR"] = str(tmp_path / "mpl")
    for script in CLI_SCRIPTS:
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )
        assert result.returncode == 0, f"{script}: {result.stderr}"
        assert "usage:" in result.stdout.lower()
