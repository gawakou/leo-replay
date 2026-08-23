from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.repeated_lab import RepeatedLabError, _load_execution


@pytest.mark.parametrize(
    "event_id",
    [
        "",
        "   ",
        123,
        True,
        [],
        {},
    ],
)
def test_load_execution_rejects_invalid_event_id(tmp_path: Path, event_id: object) -> None:
    record = {
        "action": "event_start",
        "event_id": event_id,
        "direction": "forward",
        "planned_sec": 1.0,
        "applied_sec": 1.001,
        "lateness_ms": 1.0,
    }
    path = tmp_path / "invalid-event-id.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(RepeatedLabError, match="event_id"):
        _load_execution(path)


def test_load_execution_accepts_none_and_nonempty_string_event_ids(tmp_path: Path) -> None:
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
            "action": "event_start",
            "event_id": "event-001",
            "direction": "reverse",
            "planned_sec": 1.0,
            "applied_sec": 1.002,
            "lateness_ms": 2.0,
        },
    ]
    path = tmp_path / "valid-event-id.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    loaded = _load_execution(path)

    assert loaded[0]["event_id"] is None
    assert loaded[1]["event_id"] == "event-001"
