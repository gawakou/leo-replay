from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.repeated_lab import RepeatedLabError, _load_execution, _pair_skews


def _write_records(path: Path, forward_device: object, reverse_device: object) -> None:
    records = [
        {
            "action": "timeseries_state",
            "event_id": None,
            "direction": "forward",
            "device": forward_device,
            "planned_sec": 0.0,
            "applied_sec": 0.001,
            "lateness_ms": 1.0,
        },
        {
            "action": "timeseries_state",
            "event_id": None,
            "direction": "reverse",
            "device": reverse_device,
            "planned_sec": 0.0,
            "applied_sec": 0.003,
            "lateness_ms": 3.0,
        },
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_pair_skews_accepts_distinct_bidirectional_devices(tmp_path: Path) -> None:
    path = tmp_path / "profile-execution.jsonl"
    _write_records(path, "veth-forward", "veth-reverse")

    records = _load_execution(path)

    assert _pair_skews(path, records) == pytest.approx([2.0])


def test_pair_skews_rejects_same_device_for_both_directions(tmp_path: Path) -> None:
    path = tmp_path / "profile-execution.jsonl"
    _write_records(path, "veth0", "veth0")

    records = _load_execution(path)

    with pytest.raises(RepeatedLabError, match="targets the same device"):
        _pair_skews(path, records)


@pytest.mark.parametrize("device", ["", "   ", 7, True, []])
def test_load_execution_rejects_invalid_present_device(tmp_path: Path, device: object) -> None:
    path = tmp_path / "profile-execution.jsonl"
    _write_records(path, device, "veth-reverse")

    with pytest.raises(RepeatedLabError, match="invalid device"):
        _load_execution(path)


def test_load_execution_keeps_legacy_logs_without_device(tmp_path: Path) -> None:
    path = tmp_path / "profile-execution.jsonl"
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

    loaded = _load_execution(path)

    assert _pair_skews(path, loaded) == pytest.approx([2.0])
