import json
from pathlib import Path

from leo_replay.orbit_context_summary import main, summarize_orbit_context_documents


def _candidates(count):
    return [{"norad_cat_id": str(10000 + index)} for index in range(count)]


def _annotation(changed, before, during, after, epoch_distance):
    return {
        "candidate_set_changed": changed,
        "candidate_satellites_before": _candidates(before),
        "candidate_satellites_during": _candidates(during),
        "candidate_satellites_after": _candidates(after),
        "minimum_epoch_distance_sec": epoch_distance,
    }


def _assert_invalid(annotation, expected):
    document = {"annotation_type": "event_orbit_context", "annotations": [annotation]}
    try:
        summarize_orbit_context_documents([document])
    except ValueError as exc:
        assert expected in str(exc)
    else:
        raise AssertionError("expected ValueError")


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


def test_cli_rejects_output_input_collision(tmp_path: Path):
    source = tmp_path / "orbit-context.json"
    original = json.dumps(
        {
            "annotation_type": "event_orbit_context",
            "annotations": [_annotation(True, 1, 1, 2, 30.0)],
        }
    )
    source.write_text(original, encoding="utf-8")

    try:
        main([str(source), "--output", str(tmp_path / "." / "orbit-context.json")])
    except ValueError as exc:
        assert "output path must differ from input path" in str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert source.read_text(encoding="utf-8") == original


def test_cli_rejects_duplicate_input_paths(tmp_path: Path):
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

    try:
        main([str(source), str(tmp_path / "." / "orbit-context.json"), "--output", str(output)])
    except ValueError as exc:
        assert "duplicate input path is not allowed" in str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert not output.exists()


def test_rejects_non_orbit_context_input():
    try:
        summarize_orbit_context_documents([{"annotation_type": "other", "annotations": []}])
    except ValueError as exc:
        assert "event_orbit_context" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_non_object_annotation():
    _assert_invalid("not-an-object", "must be an object")


def test_rejects_non_boolean_candidate_change_flag():
    annotation = _annotation("false", 1, 1, 1, 12.0)
    _assert_invalid(annotation, "candidate_set_changed must be boolean")


def test_rejects_invalid_candidate_lists():
    annotation = _annotation(False, 1, 1, 1, 12.0)
    annotation["candidate_satellites_during"] = None
    _assert_invalid(annotation, "candidate_satellites_during must be a list")


def test_rejects_invalid_candidate_entries():
    annotation = _annotation(False, 1, 1, 1, 12.0)
    annotation["candidate_satellites_during"] = ["10001"]
    _assert_invalid(annotation, "candidate_satellites_during[1] must be an object")

    annotation = _annotation(False, 1, 1, 1, 12.0)
    annotation["candidate_satellites_during"] = [{}]
    _assert_invalid(annotation, "norad_cat_id must be a non-empty string")


def test_rejects_duplicate_candidate_identities():
    annotation = _annotation(False, 1, 1, 1, 12.0)
    annotation["candidate_satellites_during"] = [
        {"norad_cat_id": "12345"},
        {"norad_cat_id": "12345"},
    ]
    _assert_invalid(annotation, "duplicate norad_cat_id '12345'")


def test_rejects_invalid_epoch_distance():
    annotation = _annotation(False, 1, 1, 1, "12.0")
    _assert_invalid(annotation, "minimum_epoch_distance_sec must be numeric or null")

    annotation = _annotation(False, 1, 1, 1, float("nan"))
    _assert_invalid(annotation, "minimum_epoch_distance_sec must be finite")

    annotation = _annotation(False, 1, 1, 1, -0.001)
    _assert_invalid(annotation, "minimum_epoch_distance_sec must be nonnegative")