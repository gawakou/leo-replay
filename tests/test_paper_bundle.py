from __future__ import annotations

import pytest

from leo_replay.paper_bundle import PaperBundleError, render_paper_bundle_macros


def _lab_summary() -> dict[str, object]:
    return {
        "fixed_runs": 30,
        "profile_runs": 30,
        "fixed": {
            "rtt_delta_ms": {"mean": 50.125},
            "forward_realization_ratio": {"mean": 0.925},
            "reverse_realization_ratio": {"mean": 0.91},
            "reverse_forward_ratio": {"mean": 3.0049},
        },
        "execution": {
            "absolute_lateness_ms": {"mean": 2.345, "p95": 5.678, "p99": 8.901},
            "forward_absolute_lateness_ms": {"p95": 4.321},
            "reverse_absolute_lateness_ms": {"p95": 6.543},
            "forward_reverse_skew_ms": {"mean": 1.234, "p95": 2.345, "p99": 3.456},
        },
    }


def _event_summary() -> dict[str, object]:
    return {
        "summary_type": "repeated_event_replay",
        "evaluation_count": 30,
        "event_count": 90,
        "detection": {"precision": 0.98, "recall": 0.97, "f1": 0.9749},
        "errors": {
            "start_time_error_sec": {"p95_abs": 0.1234},
            "duration_error_sec": {"p95_abs": 0.4567},
            "rtt_mae_ms": {"mean_abs": 3.219},
        },
    }


def _orbit_summary() -> dict[str, object]:
    return {
        "summary_type": "repeated_event_orbit_context",
        "evaluation_count": 30,
        "event_count": 90,
        "candidate_set_changed_ratio": 0.6111,
        "candidate_count": {"during": {"mean": 4.25}},
        "minimum_epoch_distance_sec": {"p95": 7200.0},
    }


def test_render_paper_bundle_macros() -> None:
    payload = render_paper_bundle_macros(_lab_summary(), _event_summary(), _orbit_summary())

    assert "\\newcommand{\\LeoFixedRuns}{30}" in payload
    assert "\\newcommand{\\LeoEventEvaluations}{30}" in payload
    assert "\\newcommand{\\LeoEventFOnePct}{97.5}" in payload
    assert "\\newcommand{\\LeoEventStartErrorP95Sec}{0.123}" in payload
    assert "\\newcommand{\\LeoOrbitCandidateChangedPct}{61.1}" in payload
    assert "\\newcommand{\\LeoOrbitCandidatesDuringMean}{4.25}" in payload


def test_render_paper_bundle_rejects_wrong_summary_type() -> None:
    event = _event_summary()
    event["summary_type"] = "other"

    with pytest.raises(PaperBundleError, match="repeated_event_replay"):
        render_paper_bundle_macros(_lab_summary(), event, _orbit_summary())


def test_render_paper_bundle_rejects_missing_metric() -> None:
    orbit = _orbit_summary()
    orbit.pop("candidate_set_changed_ratio")

    with pytest.raises(PaperBundleError, match="candidate_set_changed_ratio"):
        render_paper_bundle_macros(_lab_summary(), _event_summary(), orbit)
