from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_shell_syntax():
    scripts = sorted((ROOT / "scripts").rglob("*.sh")) + sorted((ROOT / "labs").rglob("*.sh"))
    assert scripts
    for script in scripts:
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, f"{script}: {result.stderr}"
