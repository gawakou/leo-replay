import json
from pathlib import Path

from leo_replay.event_replay_summary import main, summarize_event_documents


def _event(measured, replayed, start_error=None, rtt_mae=None):
    return {
        "measured": {"detected": measured},
        "replayed": {"detected": replayed},
        "errors": {
            "start_time_error_sec": start_error,
            "rtt_mae_ms": rtt_mae,
        },
    }


def test_detection_and_timing_summary():
    documents = [
        {
            "evaluation_type": "event_replay",
            "events": [
                _event(True, True, 0.05, 4.0),
                _event(True, False, None, 8.0),
                _event(False, True, None, None),
            ],
        },
        {
            "evaluation_type": "event_replay",
            "events": [_event(True, True, -0.15, 12.0)],
        },
    ]

    summary = summarize_event_documents(documents)
    assert summary["evaluation_count"] == 2
    assert summary["event_count"] == 4
    detection = summary["detection"]
    assert detection["matched_detected_count"] == 2
    assert detection["missed_detected_count"] == 1
    assert detection["spurious_detected_count"] == 1
    assert detection["precision"] == 0.666667
    assert detection["recall"] == 0.666667
    assert detection["f1"] == 0.666667
    start = summary["errors"]["start_time_error_sec"]
    assert start["count"] == 2
    assert start["mean_abs"] == 0.1
    assert start["p95_abs"] == 0.145
    assert start["max_abs"] == 0.15


def test_cli_writes_json(tmp_path: Path):
    source = tmp_path / "event.json"
    output = tmp_path / "summary.json"
    source.write_text(
        json.dumps({"evaluation_type": "event_replay", "events": [_event(True, True, 0.02, 3.0)]}),
        encoding="utf-8",
    )
    assert main([str(source), "--output", str(output)]) == 0
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["detection"]["recall"] == 1.0
    assert summary["errors"]["rtt_mae_ms"]["p95_abs"] == 3.0


def test_rejects_non_event_evaluation():
    try:
        summarize_event_documents([{"evaluation_type": "profile", "events": []}])
    except ValueError as exc:
        assert "event_replay" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_non_boolean_detection_flag():
    document = {
        "evaluation_type": "event_replay",
        "events": [_event("false", False, 0.02, 3.0)],
    }
    try:
        summarize_event_documents([document])
    except ValueError as exc:
        assert "measured.detected" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_non_finite_error_metric():
    document = {
        "evaluation_type": "event_replay",
        "events": [_event(True, True, float("nan"), 3.0)],
    }
    try:
        summarize_event_documents([document])
    except ValueError as exc:
        assert "errors.start_time_error_sec" in str(exc)
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_malformed_event_row():
    document = {"evaluation_type": "event_replay", "events": ["bad-row"]}
    try:
        summarize_event_documents([document])
    except ValueError as exc:
        assert "non-object event" in str(exc)
    else:
        raise AssertionError("expected ValueError")
