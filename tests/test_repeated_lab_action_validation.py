from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.repeated_lab import RepeatedLabError, _load_execution


def _write_record(path: Path, action: object = "timeseries_state") -> None:
    record = {
        "action": action,
        "event_id": None,
        "direction": "forward",
        "planned_sec": 0.0,
        "applied_sec": 0.001,
        "lateness_ms": 1.0,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


@pytest.mark.parametrize("action", [None, "", "   ", 1, True, []])
def test_load_execution_rejects_invalid_action(tmp_path: Path, action: object) -> None:
    path = tmp_path / "profile-execution.jsonl"
    _write_record(path, action)

    with pytest.raises(RepeatedLabError, match="invalid action"):
        _load_execution(path)


def test_load_execution_preserves_valid_action(tmp_path: Path) -> None:
    path = tmp_path / "profile-execution.jsonl"
    _write_record(path, "timeseries_state")

    records = _load_execution(path)

    assert records[0]["action"] == "timeseries_state"
