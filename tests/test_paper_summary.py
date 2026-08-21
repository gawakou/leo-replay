from __future__ import annotations

import pytest

from leo_replay.paper_summary import PaperSummaryError, render_latex_macros


def _summary() -> dict[str, object]:
    return {
        "fixed_runs": 30,
        "profile_runs": 30,
        "fixed": {
            "rtt_delta_ms": {
                "mean": 50.125,
                "standard_deviation": 1.234,
                "mean_ci95_half_width": 0.441,
            },
            "forward_realization_ratio": {"mean": 0.925, "mean_ci95_half_width": 0.0123},
            "reverse_realization_ratio": {"mean": 0.91, "mean_ci95_half_width": 0.0154},
            "reverse_forward_ratio": {"mean": 3.0049},
        },
        "execution": {
            "absolute_lateness_ms": {
                "mean": 2.345,
                "standard_deviation": 0.876,
                "mean_ci95_half_width": 0.313,
                "p95": 5.678,
                "p99": 8.901,
            },
            "forward_absolute_lateness_ms": {"p95": 4.321},
            "reverse_absolute_lateness_ms": {"p95": 6.543},
            "forward_reverse_skew_ms": {
                "mean": 1.234,
                "standard_deviation": 0.456,
                "mean_ci95_half_width": 0.163,
                "p95": 2.345,
                "p99": 3.456,
            },
            "run_mean_absolute_lateness_ms": {
                "mean": 2.111,
                "standard_deviation": 0.333,
                "mean_ci95_half_width": 0.119,
            },
            "run_p95_absolute_lateness_ms": {
                "mean": 5.432,
                "standard_deviation": 0.654,
                "mean_ci95_half_width": 0.234,
            },
            "run_forward_mean_absolute_lateness_ms": {"mean": 1.987},
            "run_reverse_mean_absolute_lateness_ms": {"mean": 2.235},
            "run_mean_forward_reverse_skew_ms": {
                "mean": 1.101,
                "standard_deviation": 0.222,
                "mean_ci95_half_width": 0.079,
            },
        },
    }


def test_render_latex_macros() -> None:
    payload = render_latex_macros(_summary())

    assert "\\newcommand{\\LeoFixedRuns}{30}" in payload
    assert "\\newcommand{\\LeoRttDeltaMeanMs}{50.12}" in payload
    assert "\\newcommand{\\LeoRttDeltaSdMs}{1.23}" in payload
    assert "\\newcommand{\\LeoRttDeltaCi95HalfWidthMs}{0.44}" in payload
    assert "\\newcommand{\\LeoForwardRealizationMeanPct}{92.5}" in payload
    assert "\\newcommand{\\LeoForwardRealizationCi95HalfWidthPct}{1.2}" in payload
    assert "\\newcommand{\\LeoReverseRealizationMeanPct}{91.0}" in payload
    assert "\\newcommand{\\LeoReverseRealizationCi95HalfWidthPct}{1.5}" in payload
    assert "\\newcommand{\\LeoReverseForwardRatioMean}{3.005}" in payload
    assert "\\newcommand{\\LeoLatenessSdMs}{0.88}" in payload
    assert "\\newcommand{\\LeoLatenessCi95HalfWidthMs}{0.31}" in payload
    assert "\\newcommand{\\LeoLatenessP95Ms}{5.68}" in payload
    assert "\\newcommand{\\LeoDirectionSkewSdMs}{0.46}" in payload
    assert "\\newcommand{\\LeoDirectionSkewCi95HalfWidthMs}{0.16}" in payload
    assert "\\newcommand{\\LeoDirectionSkewP99Ms}{3.46}" in payload
    assert "\\newcommand{\\LeoRunLatenessMeanMs}{2.11}" in payload
    assert "\\newcommand{\\LeoRunLatenessSdMs}{0.33}" in payload
    assert "\\newcommand{\\LeoRunLatenessCi95HalfWidthMs}{0.12}" in payload
    assert "\\newcommand{\\LeoRunP95LatenessMeanMs}{5.43}" in payload
    assert "\\newcommand{\\LeoRunP95LatenessCi95HalfWidthMs}{0.23}" in payload
    assert "\\newcommand{\\LeoRunForwardLatenessMeanMs}{1.99}" in payload
    assert "\\newcommand{\\LeoRunReverseLatenessMeanMs}{2.23}" in payload
    assert "\\newcommand{\\LeoRunDirectionSkewMeanMs}{1.10}" in payload
    assert "\\newcommand{\\LeoRunDirectionSkewSdMs}{0.22}" in payload
    assert "\\newcommand{\\LeoRunDirectionSkewCi95HalfWidthMs}{0.08}" in payload


def test_render_latex_macros_rejects_missing_metric() -> None:
    summary = _summary()
    execution = summary["execution"]
    assert isinstance(execution, dict)
    execution.pop("run_mean_forward_reverse_skew_ms")

    with pytest.raises(PaperSummaryError, match="run_mean_forward_reverse_skew_ms"):
        render_latex_macros(summary)
