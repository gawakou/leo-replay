from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.repeated_lab import RepeatedLabError, summarize


def _write_run(root: Path, fixed: dict[str, object]) -> None:
    run_dir = root / "run-001"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "fixed-summary.json").write_text(json.dumps(fixed), encoding="utf-8")
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
    (run_dir / "profile-execution.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _valid_fixed() -> dict[str, object]:
    return {
        "status": "pass",
        "rtt_delta_ms": 50.0,
        "forward_throughput_mbps": 18.0,
        "reverse_throughput_mbps": 54.0,
        "configured_forward_rate_mbps": 20.0,
        "configured_reverse_rate_mbps": 60.0,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("rtt_delta_ms", "50.0"),
        ("rtt_delta_ms", True),
        ("rtt_delta_ms", float("nan")),
        ("forward_throughput_mbps", "18.0"),
        ("forward_throughput_mbps", False),
        ("forward_throughput_mbps", float("inf")),
        ("reverse_throughput_mbps", "54.0"),
        ("reverse_throughput_mbps", float("nan")),
        ("configured_forward_rate_mbps", "20.0"),
        ("configured_reverse_rate_mbps", True),
        ("configured_reverse_rate_mbps", float("inf")),
    ],
)
def test_summarize_rejects_invalid_fixed_metrics(
    tmp_path: Path, field: str, value: object
) -> None:
    fixed = _valid_fixed()
    fixed[field] = value
    _write_run(tmp_path, fixed)

    with pytest.raises(RepeatedLabError, match=field):
        summarize(tmp_path)


@pytest.mark.parametrize(
    "field",
    [
        "forward_throughput_mbps",
        "configured_forward_rate_mbps",
        "configured_reverse_rate_mbps",
    ],
)
def test_summarize_rejects_nonpositive_ratio_denominators(
    tmp_path: Path, field: str
) -> None:
    fixed = _valid_fixed()
    fixed[field] = 0.0
    _write_run(tmp_path, fixed)

    with pytest.raises(RepeatedLabError, match=field):
        summarize(tmp_path)
