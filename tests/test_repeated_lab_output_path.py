from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.repeated_lab import main


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_execution(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "action": "timeseries_state",
            "event_id": None,
            "direction": "forward",
            "planned_sec": 0.0,
            "applied_sec": 0.001,
            "lateness_ms": 1.0,
        },
        {
            "action": "timeseries_state",
            "event_id": None,
            "direction": "reverse",
            "planned_sec": 0.0,
            "applied_sec": 0.003,
            "lateness_ms": 3.0,
        },
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_main_rejects_output_collision_with_fixed_input(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-001"
    fixed_path = run_dir / "fixed-summary.json"
    _write_json(
        fixed_path,
        {
            "status": "pass",
            "rtt_delta_ms": 50.0,
            "forward_throughput_mbps": 18.0,
            "reverse_throughput_mbps": 54.0,
            "configured_forward_rate_mbps": 20.0,
            "configured_reverse_rate_mbps": 60.0,
        },
    )
    _write_execution(run_dir / "profile-execution.jsonl")
    original = fixed_path.read_bytes()

    with pytest.raises(SystemExit) as excinfo:
        main(["--input", str(tmp_path), "--output", str(run_dir / "." / "fixed-summary.json")])

    assert excinfo.value.code == 2
    assert fixed_path.read_bytes() == original


def test_main_rejects_output_collision_with_execution_input(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-001"
    _write_json(
        run_dir / "fixed-summary.json",
        {
            "status": "pass",
            "rtt_delta_ms": 50.0,
            "forward_throughput_mbps": 18.0,
            "reverse_throughput_mbps": 54.0,
            "configured_forward_rate_mbps": 20.0,
            "configured_reverse_rate_mbps": 60.0,
        },
    )
    execution_path = run_dir / "profile-execution.jsonl"
    _write_execution(execution_path)
    original = execution_path.read_bytes()

    with pytest.raises(SystemExit) as excinfo:
        main(["--input", str(tmp_path), "--output", str(execution_path)])

    assert excinfo.value.code == 2
    assert execution_path.read_bytes() == original
