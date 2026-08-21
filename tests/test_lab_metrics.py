import json
from pathlib import Path

import pytest

from leo_replay.lab_metrics import (
    LabMetricError,
    parse_execution_log,
    parse_iperf_mbps,
    parse_ping,
)


def test_parse_ping(tmp_path: Path):
    path = tmp_path / "ping.txt"
    path.write_text(
        "64 bytes from x: time=10.0 ms\n"
        "64 bytes from x: time=20.0 ms\n"
        "rtt min/avg/max/mdev = 10.000/15.000/20.000/5.000 ms\n",
        encoding="utf-8",
    )
    result = parse_ping(path)
    assert result["average_ms"] == 15.0
    assert result["samples_ms"] == [10.0, 20.0]


def test_parse_iperf(tmp_path: Path):
    path = tmp_path / "iperf.json"
    path.write_text(
        json.dumps({"end": {"sum_received": {"bits_per_second": 20_000_000}}}),
        encoding="utf-8",
    )
    assert parse_iperf_mbps(path) == 20.0


def test_parse_execution_log(tmp_path: Path):
    path = tmp_path / "execution.jsonl"
    records = [
        {"direction": "forward", "lateness_ms": 1.0},
        {"direction": "reverse", "lateness_ms": -2.0},
        {"direction": "forward", "lateness_ms": 3.0},
        {"direction": "reverse", "lateness_ms": -4.0},
    ]
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    result = parse_execution_log(path)
    assert result["directions"] == ["forward", "reverse"]
    assert result["maximum_absolute_lateness_ms"] == 4.0
    assert result["average_absolute_lateness_ms"] == 2.5

    overall = result["lateness_ms"]
    assert overall["sample_count"] == 4
    assert overall["mean_ms"] == -0.5
    assert overall["p50_absolute_ms"] == pytest.approx(2.5)
    assert overall["p95_absolute_ms"] == pytest.approx(3.85)
    assert overall["p99_absolute_ms"] == pytest.approx(3.97)

    forward = result["lateness_by_direction_ms"]["forward"]
    reverse = result["lateness_by_direction_ms"]["reverse"]
    assert forward["sample_count"] == 2
    assert forward["mean_absolute_ms"] == 2.0
    assert reverse["sample_count"] == 2
    assert reverse["mean_absolute_ms"] == 3.0


@pytest.mark.parametrize(
    "record",
    [
        {"direction": "forward"},
        {"direction": "forward", "lateness_ms": "1.0"},
        {"direction": "forward", "lateness_ms": True},
        {"direction": "forward", "lateness_ms": float("nan")},
        {"direction": "forward", "lateness_ms": float("inf")},
        {"direction": "sideways", "lateness_ms": 1.0},
        {"lateness_ms": 1.0},
    ],
)
def test_parse_execution_log_rejects_invalid_timing_records(tmp_path: Path, record: dict):
    path = tmp_path / "invalid-execution.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(LabMetricError):
        parse_execution_log(path)
