from pathlib import Path
import json
import os
import subprocess
import sys

from leo_replay.orbit.visibility import write_visibility_csv

ROOT = Path(__file__).resolve().parents[1]
ORBIT = ROOT / "examples/orbit"


def visibility_row(timestamp, cat_id, name, elevation):
    return {
        "timestamp_utc": timestamp,
        "site_id": "test-site",
        "satellite_name": name,
        "norad_cat_id": cat_id,
        "object_id": "",
        "elevation_deg": elevation,
        "azimuth_deg": 180.0,
        "slant_range_km": 700.0,
        "visible": True,
        "element_epoch_utc": "2024-05-06T00:00:00Z",
        "epoch_distance_sec": 10.0,
        "stale_element": False,
        "propagation_error": "",
    }


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


def test_orbit_help_lists_core_commands():
    result = run_cli("orbit", "--help")
    assert result.returncode == 0, result.stderr
    assert "fetch" in result.stdout
    assert "verify-snapshot" in result.stdout
    assert "select-elements" in result.stdout
    assert "import" in result.stdout
    assert "visibility" in result.stdout
    assert "annotate-events" in result.stdout


def test_orbit_import_and_visibility_cli(tmp_path):
    manifest = tmp_path / "manifest.json"
    result = run_cli(
        "orbit", "import",
        "--input", ORBIT / "iss-omm.example.json",
        "--output", manifest,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(manifest.read_text(encoding="utf-8"))
    assert value["satellite_count"] == 1

    visibility = tmp_path / "visibility.csv"
    result = run_cli(
        "orbit", "visibility",
        "--orbit", ORBIT / "iss-omm.example.json",
        "--site", ORBIT / "observer-hiroshima.example.json",
        "--start", "2024-05-06T19:53:05Z",
        "--duration-sec", "1",
        "--step-sec", "1",
        "--minimum-elevation-deg", "-90",
        "--all-satellites",
        "--output", visibility,
    )
    assert result.returncode == 0, result.stderr
    assert visibility.is_file()
    metadata = json.loads(Path(str(visibility) + ".meta.json").read_text(encoding="utf-8"))
    assert metadata["sample_count"] == 2


def test_annotate_events_cli(tmp_path):
    visibility = tmp_path / "visibility.csv"
    write_visibility_csv(
        visibility,
        [visibility_row("2024-05-06T00:00:02.000000Z", "A", "SAT-A", 35.0)],
    )
    output = tmp_path / "annotations.json"
    result = run_cli(
        "orbit", "annotate-events",
        "--events", ROOT / "examples/events-directional-v1.example.json",
        "--visibility", visibility,
        "--observation-start-utc", "2024-05-06T00:00:00Z",
        "--output", output,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["annotation_type"] == "event_orbit_context"
    assert len(value["annotations"]) == 1
