import json
from pathlib import Path

from leo_replay.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_event_generation_validation_and_dry_run(tmp_path):
    events = tmp_path / "events.json"
    details = tmp_path / "details.json"
    result = main(
        [
            "profile",
            "generate",
            "--mode",
            "event",
            "--ping",
            str(ROOT / "examples/raw/ping.csv"),
            "--iperf",
            str(ROOT / "examples/raw/iperf.json"),
            "--grpc",
            str(ROOT / "examples/raw/grpc.csv"),
            "--output",
            str(events),
            "--detail-output",
            str(details),
            "--bin-sec",
            "0.5",
            "--target-rate-mbps",
            "100",
            "--min-event-duration-sec",
            "0.05",
        ]
    )
    assert result == 0
    document = json.loads(events.read_text(encoding="utf-8"))
    assert document["profile_type"] == "event"
    assert document["events"]

    assert main(["validate", "--input", str(events)]) == 0

    execution_log = tmp_path / "execution.jsonl"
    assert (
        main(
            [
                "replay",
                "--mode",
                "event",
                "--input",
                str(events),
                "--dev",
                "eth-test",
                "--dry-run",
                "--restore-default-between-events",
                "--execution-log",
                str(execution_log),
            ]
        )
        == 0
    )
    records = [json.loads(line) for line in execution_log.read_text().splitlines()]
    assert any(record["action"] == "event_start" for record in records)
    assert records[-1]["action"] == "final_baseline"
