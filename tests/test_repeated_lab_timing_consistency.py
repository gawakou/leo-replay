from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.repeated_lab import RepeatedLabError, _load_execution


def _write_record(path: Path, *, planned_sec: float, applied_sec: float, lateness_ms: float) -> None:
    path.write_text(
        json.dumps(
            {
                "action": "timeseries_state",
                "event_id": None,
                "direction": "forward",
                "planned_sec": planned_sec,
                "applied_sec": applied_sec,
                "lateness_ms": lateness_ms,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_load_execution_rejects_inconsistent_lateness(tmp_path: Path) -> None:
    path = tmp_path / "profile-execution.jsonl"
    _write_record(path, planned_sec=1.0, applied_sec=1.001, lateness_ms=2.0)

    with pytest.raises(RepeatedLabError, match="inconsistent timing"):
        _load_execution(path)


def test_load_execution_allows_logger_rounding_error(tmp_path: Path) -> None:
    path = tmp_path / "profile-execution.jsonl"
    # planned_sec/applied_sec are persisted at microsecond precision while
    # lateness_ms is computed from the unrounded monotonic timestamps.  The
    # reconstructed value can therefore differ by roughly 0.001 ms.
    _write_record(path, planned_sec=1.0, applied_sec=1.000001, lateness_ms=0.00002)

    records = _load_execution(path)

    assert records[0]["lateness_ms"] == pytest.approx(0.00002)
