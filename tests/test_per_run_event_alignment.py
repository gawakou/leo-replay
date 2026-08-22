from __future__ import annotations

import pytest

from leo_replay.event_replay_summary import summarize_event_documents
from leo_replay.orbit_context_summary import summarize_orbit_context_documents
from leo_replay.paper_bundle import PaperBundleError, _validate_event_orbit_alignment


def _event() -> dict[str, object]:
    return {
        "measured": {"detected": True},
        "replayed": {"detected": True},
        "errors": {},
    }


def _annotation() -> dict[str, object]:
    return {
        "candidate_set_changed": False,
        "candidate_satellites_before": [],
        "candidate_satellites_during": [],
        "candidate_satellites_after": [],
        "minimum_epoch_distance_sec": None,
    }


def test_repeated_summaries_record_events_per_evaluation() -> None:
    event_summary = summarize_event_documents(
        [
            {"evaluation_type": "event_replay", "events": [_event(), _event()]},
            {"evaluation_type": "event_replay", "events": [_event()]},
        ]
    )
    orbit_summary = summarize_orbit_context_documents(
        [
            {
                "annotation_type": "event_orbit_context",
                "annotations": [_annotation(), _annotation()],
            },
            {"annotation_type": "event_orbit_context", "annotations": [_annotation()]},
        ]
    )

    assert event_summary["events_per_evaluation"] == [2, 1]
    assert orbit_summary["events_per_evaluation"] == [2, 1]


def test_paper_alignment_rejects_equal_totals_with_different_run_counts() -> None:
    event_summary = {
        "evaluation_count": 2,
        "event_count": 3,
        "events_per_evaluation": [2, 1],
    }
    orbit_summary = {
        "evaluation_count": 2,
        "event_count": 3,
        "events_per_evaluation": [1, 2],
    }

    with pytest.raises(PaperBundleError, match="first mismatch at evaluation 1"):
        _validate_event_orbit_alignment(event_summary, orbit_summary)


def test_paper_alignment_keeps_legacy_total_count_check() -> None:
    event_summary = {"evaluation_count": 2, "event_count": 3}
    orbit_summary = {"evaluation_count": 2, "event_count": 3}

    _validate_event_orbit_alignment(event_summary, orbit_summary)
