from __future__ import annotations

import math

import pytest

from leo_replay.paper_bundle import PaperBundleError, render_paper_bundle_macros


def _lab_summary() -> dict[str, object]:
    return {
        "fixed_runs": 30,
        "profile_runs": 30,
        "fixed": {
            "rtt_delta_ms": {"mean": 50.0, "standard_deviation": 1.0, "mean_ci95_half_width": 0.4},
            "forward_realization_ratio": {"mean": 0.9, "standard_deviation": 0.01, "mean_ci95_half_width": 0.004},
            "reverse_realization_ratio": {"mean": 0.9, "standard_deviation": 0.01, "mean_ci95_half_width": 0.004},
            "reverse_forward_ratio": {"mean": 1.0},
        },
        "execution": {
            "absolute_lateness_ms": {"mean": 2.0, "standard_deviation": 0.5, "mean_ci95_half_width": 0.2, "p95": 4.0, "p99": 5.0},
            "forward_absolute_lateness_ms": {"p95": 4.0},
            "reverse_absolute_lateness_ms": {"p95": 4.0},
            "forward_reverse_skew_ms": {"mean": 1.0, "standard_deviation": 0.2, "mean_ci95_half_width": 0.1, "p95": 2.0, "p99": 3.0},
            "run_mean_absolute_lateness_ms": {"mean": 2.0, "standard_deviation": 0.3, "mean_ci95_half_width": 0.1},
            "run_p95_absolute_lateness_ms": {"mean": 4.0, "standard_deviation": 0.4, "mean_ci95_half_width": 0.2},
            "run_forward_mean_absolute_lateness_ms": {"mean": 2.0},
            "run_reverse_mean_absolute_lateness_ms": {"mean": 2.0},
            "run_mean_forward_reverse_skew_ms": {"mean": 1.0, "standard_deviation": 0.2, "mean_ci95_half_width": 0.1},
        },
    }


def _event_summary() -> dict[str, object]:
    return {
        "summary_type": "repeated_event_replay",
        "evaluation_count": 30,
        "event_count": 90,
        "detection": {"precision": 0.98, "recall": 0.97, "f1": 0.9749},
        "errors": {
            "start_time_error_sec": {"p95_abs": 0.1},
            "duration_error_sec": {"p95_abs": 0.2},
            "rtt_mae_ms": {"mean_abs": 3.0},
        },
    }


def _orbit_summary() -> dict[str, object]:
    return {
        "summary_type": "repeated_event_orbit_context",
        "evaluation_count": 30,
        "event_count": 90,
        "candidate_set_changed_ratio": 0.6,
        "candidate_count": {"during": {"mean": 4.0}},
        "minimum_epoch_distance_sec": {"p95": 7200.0},
    }


@pytest.mark.parametrize("bad", [True, "0.98", math.nan, math.inf, -math.inf])
def test_rejects_invalid_event_numeric_metrics(bad: object) -> None:
    event = _event_summary()
    detection = event["detection"]
    assert isinstance(detection, dict)
    detection["precision"] = bad

    with pytest.raises(PaperBundleError, match="precision"):
        render_paper_bundle_macros(_lab_summary(), event, _orbit_summary())


@pytest.mark.parametrize("bad", [False, "4.0", math.nan, math.inf, -math.inf])
def test_rejects_invalid_orbit_numeric_metrics(bad: object) -> None:
    orbit = _orbit_summary()
    candidate_count = orbit["candidate_count"]
    assert isinstance(candidate_count, dict)
    during = candidate_count["during"]
    assert isinstance(during, dict)
    during["mean"] = bad

    with pytest.raises(PaperBundleError, match="candidate_count.during.mean"):
        render_paper_bundle_macros(_lab_summary(), _event_summary(), orbit)
