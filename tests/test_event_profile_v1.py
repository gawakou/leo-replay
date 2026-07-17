from pathlib import Path

from leo_replay.event_profile import (
    create_document,
    legacy_rows,
    load_document,
    validate_document,
)

ROOT = Path(__file__).resolve().parents[1]


def test_v1_example_is_valid():
    document = load_document(ROOT / "examples/events-v1.example.json")
    assert document["schema_version"] == "1.0"
    assert len(document["events"]) == 1
    assert validate_document(document) == []


def test_legacy_round_trip_preserves_replay_parameters():
    legacy = [
        {
            "start_sec": 1.0,
            "end_sec": 1.1,
            "duration_sec": 0.1,
            "event": "handover_suspected",
            "severity": 2,
            "avg_rate_mbps": 20.0,
            "max_loss_pct": 8.0,
            "avg_delay_ms": 40.0,
            "calibrated_delay_ms": 45.0,
            "calibrated_jitter_ms": 5.0,
            "calibrated_spike_ms": 10.0,
        }
    ]
    document = create_document(legacy, baseline={"rate_mbit": 100.0})
    assert validate_document(document) == []
    converted = legacy_rows(document)[0]
    assert converted["replay_rate_mbps"] == 20.0
    assert converted["replay_delay_ms"] == 45.0
    assert converted["replay_jitter_ms"] == 5.0
    assert converted["replay_spike_ms"] == 10.0
