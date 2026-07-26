from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "leo_replay", *map(str, args)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_select_elements_cli_compare(tmp_path):
    output = tmp_path / "selection.json"
    result = run_cli(
        "orbit",
        "select-elements",
        "--input",
        ROOT / "examples/orbit/iss-history.example.json",
        "--mode",
        "compare",
        "--time",
        "2024-05-06T19:55:00Z",
        "--output",
        output,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "pass"
    assert summary["causal_selected"] == 1
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["selection_type"] == "historical_orbit_element_selection"
    satellite = document["observations"][0]["satellites"][0]
    assert satellite["causal"]["gp_id"] == 1002
    assert satellite["retrospective"]["gp_id"] == 1003


def test_select_elements_cli_requires_observation_time(tmp_path):
    result = run_cli(
        "orbit",
        "select-elements",
        "--input",
        ROOT / "examples/orbit/iss-history.example.json",
        "--output",
        tmp_path / "selection.json",
    )
    assert result.returncode != 0
    assert "observation time" in result.stderr
