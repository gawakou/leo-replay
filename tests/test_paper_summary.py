from __future__ import annotations

import pytest

from leo_replay.paper_summary import PaperSummaryError, render_latex_macros


def _summary() -> dict[str, object]:
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


def test_render_latex_macros() -> None:
    payload = render_latex_macros(_summary())

    assert "\\newcommand{\\LeoFixedRuns}{30}" in payload
    assert "\\newcommand{\\LeoRttDeltaMeanMs}{50.12}" in payload
    assert "\\newcommand{\\LeoForwardRealizationMeanPct}{92.5}" in payload
    assert "\\newcommand{\\LeoReverseRealizationMeanPct}{91.0}" in payload
    assert "\\newcommand{\\LeoReverseForwardRatioMean}{3.005}" in payload
    assert "\\newcommand{\\LeoLatenessP95Ms}{5.68}" in payload
    assert "\\newcommand{\\LeoDirectionSkewP99Ms}{3.46}" in payload


def test_render_latex_macros_rejects_missing_metric() -> None:
    summary = _summary()
    execution = summary["execution"]
    assert isinstance(execution, dict)
    execution.pop("forward_reverse_skew_ms")

    with pytest.raises(PaperSummaryError, match="forward_reverse_skew_ms"):
        render_latex_macros(summary)
