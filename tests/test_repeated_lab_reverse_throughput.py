from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.repeated_lab import RepeatedLabError, summarize


def _write_run(root: Path, reverse_throughput_mbps: float) -> None:
    run_dir = root / "run-001"
    run_dir.mkdir(parents=True)
    (run_dir / "fixed-summary.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "rtt_delta_ms": 50.0,
                "forward_throughput_mbps": 18.0,
                "reverse_throughput_mbps": reverse_throughput_mbps,
                "configured_forward_rate_mbps": 20.0,
                "configured_reverse_rate_mbps": 60.0,
            }
        ),
        encoding="utf-8",
    )
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


@pytest.mark.parametrize("reverse_throughput_mbps", [0.0, -1.0])
def test_summarize_rejects_nonpositive_reverse_throughput(
    tmp_path: Path, reverse_throughput_mbps: float
) -> None:
    _write_run(tmp_path, reverse_throughput_mbps)

    with pytest.raises(RepeatedLabError, match="positive reverse_throughput_mbps"):
        summarize(tmp_path)
