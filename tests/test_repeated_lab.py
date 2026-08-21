from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from leo_replay.repeated_lab import RepeatedLabError, summarize


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_execution(path: Path, run: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "action": "timeseries_state",
            "event_id": None,
            "direction": "forward",
            "planned_sec": 0.0,
            "applied_sec": 0.001 * run,
            "lateness_ms": 1.0 * run,
        },
        {
            "action": "timeseries_state",
            "event_id": None,
            "direction": "reverse",
            "planned_sec": 0.0,
            "applied_sec": 0.003 * run,
            "lateness_ms": 3.0 * run,
        },
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_summarize_repeated_lab_artifacts(tmp_path: Path) -> None:
    for run, rtt, forward, reverse in (
        (1, 50.0, 18.0, 54.0),
        (2, 52.0, 19.0, 57.0),
    ):
        run_dir = tmp_path / f"run-{run:02d}"
        _write_json(
            run_dir / "fixed-summary.json",
            {
                "status": "pass",
                "rtt_delta_ms": rtt,
                "forward_throughput_mbps": forward,
                "reverse_throughput_mbps": reverse,
                "configured_forward_rate_mbps": 20.0,
                "configured_reverse_rate_mbps": 60.0,
            },
        )
        _write_execution(run_dir / "profile-execution.jsonl", run)

    result = summarize(tmp_path)

    assert result["fixed_runs"] == 2
    assert result["profile_runs"] == 2
    assert result["fixed"]["rtt_delta_ms"]["mean"] == 51.0
    assert result["fixed"]["rtt_delta_ms"]["standard_deviation"] == pytest.approx(math.sqrt(2.0))
    assert result["fixed"]["rtt_delta_ms"]["mean_ci95_half_width"] == pytest.approx(1.96)
    assert result["fixed"]["forward_realization_ratio"]["mean"] == 0.925
    assert result["fixed"]["reverse_realization_ratio"]["mean"] == 0.925
    assert result["fixed"]["reverse_forward_ratio"]["mean"] == 3.0
    assert result["execution"]["signed_lateness_ms"]["mean"] == 3.0
    assert result["execution"]["absolute_lateness_ms"]["count"] == 4
    assert result["execution"]["absolute_lateness_ms"]["maximum"] == 6.0
    assert result["execution"]["absolute_lateness_ms"]["standard_deviation"] == pytest.approx(
        math.sqrt(14.0 / 3.0)
    )
    assert result["execution"]["forward_absolute_lateness_ms"]["mean"] == 1.5
    assert result["execution"]["reverse_absolute_lateness_ms"]["mean"] == 4.5
    assert result["execution"]["forward_reverse_skew_ms"]["count"] == 2
    assert result["execution"]["forward_reverse_skew_ms"]["mean"] == 3.0

    # Paper-facing uncertainty should also be available at the independent-run
    # level rather than only across the pooled event applications.
    assert result["execution"]["run_mean_absolute_lateness_ms"]["count"] == 2
    assert result["execution"]["run_mean_absolute_lateness_ms"]["mean"] == 3.0
    assert result["execution"]["run_mean_absolute_lateness_ms"]["standard_deviation"] == pytest.approx(
        math.sqrt(2.0)
    )
    assert result["execution"]["run_mean_absolute_lateness_ms"]["mean_ci95_half_width"] == pytest.approx(
        1.96
    )
    assert result["execution"]["run_p95_absolute_lateness_ms"]["mean"] == pytest.approx(4.35)
    assert result["execution"]["run_forward_mean_absolute_lateness_ms"]["mean"] == 1.5
    assert result["execution"]["run_reverse_mean_absolute_lateness_ms"]["mean"] == 4.5
    assert result["execution"]["run_mean_forward_reverse_skew_ms"]["mean"] == 3.0


def test_summarize_rejects_unpaired_run_artifacts(tmp_path: Path) -> None:
    run_one = tmp_path / "run-001"
    _write_json(
        run_one / "fixed-summary.json",
        {
            "status": "pass",
            "rtt_delta_ms": 50.0,
            "forward_throughput_mbps": 18.0,
            "reverse_throughput_mbps": 54.0,
            "configured_forward_rate_mbps": 20.0,
            "configured_reverse_rate_mbps": 60.0,
        },
    )
    _write_execution(run_one / "profile-execution.jsonl", 1)

    run_two = tmp_path / "run-002"
    _write_json(
        run_two / "fixed-summary.json",
        {
            "status": "pass",
            "rtt_delta_ms": 52.0,
            "forward_throughput_mbps": 19.0,
            "reverse_throughput_mbps": 57.0,
            "configured_forward_rate_mbps": 20.0,
            "configured_reverse_rate_mbps": 60.0,
        },
    )

    with pytest.raises(RepeatedLabError, match="missing profile-execution.jsonl for run-002"):
        summarize(tmp_path)
