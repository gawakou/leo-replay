import csv
from pathlib import Path

from leo_replay.event_metrics import evaluate_events

ROOT = Path(__file__).resolve().parents[1]


def write_ping(path: Path, values: list[tuple[float, str, int]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time_s", "rtt_ms", "timeout"])
        writer.writerows(values)


def test_event_timing_and_peak_metrics(tmp_path):
    measured = tmp_path / "measured.csv"
    replayed = tmp_path / "replayed.csv"
    write_ping(
        measured,
        [(1.8, "30", 0), (2.0, "80", 0), (2.1, "120", 0), (2.2, "70", 0), (2.4, "30", 0)],
    )
    write_ping(
        replayed,
        [(1.8, "30", 0), (2.05, "75", 0), (2.15, "110", 0), (2.25, "65", 0), (2.4, "30", 0)],
    )
    metrics = evaluate_events(
        measured,
        replayed,
        ROOT / "examples/events-v1.example.json",
        search_margin_sec=0.3,
        align_tolerance_sec=0.06,
        threshold_ms=60.0,
    )
    event = metrics["events"][0]
    assert event["errors"]["start_time_error_sec"] == 0.05
    assert event["errors"]["peak_rtt_error_ms"] == -10.0
    assert metrics["aggregate"]["event_count"] == 1
