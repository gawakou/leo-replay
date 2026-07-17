import csv
from pathlib import Path

from leo_replay.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_event_metrics_csv_output(tmp_path):
    measured = tmp_path / "measured.csv"
    replayed = tmp_path / "replayed.csv"
    measured.write_text("time_s,rtt_ms,timeout\n1.8,30,0\n2.0,80,0\n2.1,120,0\n2.2,70,0\n", encoding="utf-8")
    replayed.write_text("time_s,rtt_ms,timeout\n1.8,30,0\n2.05,75,0\n2.15,110,0\n2.25,65,0\n", encoding="utf-8")
    output = tmp_path / "metrics.json"
    csv_output = tmp_path / "metrics.csv"
    result = main([
        "evaluate", "events",
        "--measured-ping", str(measured),
        "--replayed-ping", str(replayed),
        "--events", str(ROOT / "examples/events-v1.example.json"),
        "--output", str(output),
        "--csv-output", str(csv_output),
        "--threshold-ms", "60",
        "--align-tolerance-sec", "0.06",
    ])
    assert result == 0
    with csv_output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert "end_time_error_sec" in rows[0]
