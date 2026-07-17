from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLI_SCRIPTS = [
    *sorted((ROOT / "scripts/profile").glob("*.py")),
    *sorted((ROOT / "scripts/replay").glob("*.py")),
    *sorted((ROOT / "scripts/evaluation").glob("*.py")),
    *sorted((ROOT / "scripts/orchestration").glob("*.py")),
]


def test_cli_help():
    for script in CLI_SCRIPTS:
        result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
        assert result.returncode == 0, f"{script}: {result.stderr}"
        assert "usage:" in result.stdout.lower()
