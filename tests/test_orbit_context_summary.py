import json
from pathlib import Path

from leo_replay.orbit_context_summary import main, summarize_orbit_context_documents


def _annotation(changed, before, during, after, epoch_distance):
    return {
        "candidate_set_changed": changed,
        "candidate_satellites_before": [{}] * before,
        "candidate_satellites_during": [{}] * during,
        "candidate_satellites_after": [{}] * after,
        "minimum_epoch_distance_sec": epoch_distance,
    }


def test_orbit_context_summary():
    documents = [
        {
            "annotation_type": "event_orbit_context",
            "annotations": [
                _annotation(True, 1, 2, 1, 12.0),
                _annotation(False, 0, 1, 1, 24.0),
            ],
        }
    ]

    summary = summarize_orbit_context_documents(documents)
    assert summary["evaluation_count"] == 1
    assert summary["event_count"] == 2
    assert summary["candidate_set_changed_count"] == 1
    assert summary["candidate_set_changed_ratio"] == 0.5
    assert summary["candidate_count"]["during"]["mean"] == 1.5
    assert summary["minimum_epoch_distance_sec"]["p50"] == 18.0
    assert "no connected-satellite assertion" in summary["semantics"]


def test_cli_writes_json(tmp_path: Path):
    source = tmp_path / "orbit-context.json"
    output = tmp_path / "summary.json"
    source.write_text(
        json.dumps(
            {
                "annotation_type": "event_orbit_context",
                "annotations": [_annotation(True, 1, 1, 2, 30.0)],
            }
        ),
        encoding="utf-8",
    )
    assert main([str(source), "--output", str(output)]) == 0
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["candidate_set_changed_ratio"] == 1.0
    assert summary["minimum_epoch_distance_sec"]["p95"] == 30.0


def test_rejects_non_orbit_context_input():
    try:
        summarize_orbit_context_documents([{"annotation_type": "other", "annotations": []}])
    except ValueError as exc:
        assert "event_orbit_context" in str(exc)
    else:
        raise AssertionError("expected ValueError")
