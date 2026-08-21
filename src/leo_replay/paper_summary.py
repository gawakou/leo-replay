from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


class PaperSummaryError(ValueError):
    """Raised when a repeated-lab summary cannot be rendered for the paper."""


def _value(summary: dict[str, Any], *path: str) -> float:
    current: Any = summary
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise PaperSummaryError("missing summary field: " + ".".join(path))
        current = current[key]
    field = ".".join(path)
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise PaperSummaryError("non-numeric summary field: " + field)
    value = float(current)
    if not math.isfinite(value):
        raise PaperSummaryError("non-finite summary field: " + field)
    return value


def _integer(summary: dict[str, Any], key: str) -> int:
    if key not in summary:
        raise PaperSummaryError(f"missing summary field: {key}")
    value = summary[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise PaperSummaryError(f"non-integer summary field: {key}")
    if value <= 0:
        raise PaperSummaryError(f"non-positive summary field: {key}")
    return value


def render_latex_macros(summary: dict[str, Any]) -> str:
    """Render stable LaTeX macros for the headline VTCA evaluation metrics."""
    fixed_runs = _integer(summary, "fixed_runs")
    profile_runs = _integer(summary, "profile_runs")
    if fixed_runs != profile_runs:
        raise PaperSummaryError(
            f"mismatched repeated-lab run counts: fixed_runs={fixed_runs}, profile_runs={profile_runs}"
        )

    values: list[tuple[str, str]] = [
        ("LeoFixedRuns", str(fixed_runs)),
        ("LeoProfileRuns", str(profile_runs)),
        (
            "LeoRttDeltaMeanMs",
            f'{_value(summary, "fixed", "rtt_delta_ms", "mean"):.2f}',
        ),
        (
            "LeoRttDeltaSdMs",
            f'{_value(summary, "fixed", "rtt_delta_ms", "standard_deviation"):.2f}',
        ),
        (
            "LeoRttDeltaCi95HalfWidthMs",
            f'{_value(summary, "fixed", "rtt_delta_ms", "mean_ci95_half_width"):.2f}',
        ),
        (
            "LeoForwardRealizationMeanPct",
            f'{100.0 * _value(summary, "fixed", "forward_realization_ratio", "mean"):.1f}',
        ),
        (
            "LeoForwardRealizationCi95HalfWidthPct",
            f'{100.0 * _value(summary, "fixed", "forward_realization_ratio", "mean_ci95_half_width"):.1f}',
        ),
        (
            "LeoReverseRealizationMeanPct",
            f'{100.0 * _value(summary, "fixed", "reverse_realization_ratio", "mean"):.1f}',
        ),
        (
            "LeoReverseRealizationCi95HalfWidthPct",
            f'{100.0 * _value(summary, "fixed", "reverse_realization_ratio", "mean_ci95_half_width"):.1f}',
        ),
        (
            "LeoReverseForwardRatioMean",
            f'{_value(summary, "fixed", "reverse_forward_ratio", "mean"):.3f}',
        ),
        (
            "LeoLatenessMeanMs",
            f'{_value(summary, "execution", "absolute_lateness_ms", "mean"):.2f}',
        ),
        (
            "LeoLatenessSdMs",
            f'{_value(summary, "execution", "absolute_lateness_ms", "standard_deviation"):.2f}',
        ),
        (
            "LeoLatenessCi95HalfWidthMs",
            f'{_value(summary, "execution", "absolute_lateness_ms", "mean_ci95_half_width"):.2f}',
        ),
        (
            "LeoLatenessP95Ms",
            f'{_value(summary, "execution", "absolute_lateness_ms", "p95"):.2f}',
        ),
        (
            "LeoLatenessP99Ms",
            f'{_value(summary, "execution", "absolute_lateness_ms", "p99"):.2f}',
        ),
        (
            "LeoForwardLatenessP95Ms",
            f'{_value(summary, "execution", "forward_absolute_lateness_ms", "p95"):.2f}',
        ),
        (
            "LeoReverseLatenessP95Ms",
            f'{_value(summary, "execution", "reverse_absolute_lateness_ms", "p95"):.2f}',
        ),
        (
            "LeoDirectionSkewMeanMs",
            f'{_value(summary, "execution", "forward_reverse_skew_ms", "mean"):.2f}',
        ),
        (
            "LeoDirectionSkewSdMs",
            f'{_value(summary, "execution", "forward_reverse_skew_ms", "standard_deviation"):.2f}',
        ),
        (
            "LeoDirectionSkewCi95HalfWidthMs",
            f'{_value(summary, "execution", "forward_reverse_skew_ms", "mean_ci95_half_width"):.2f}',
        ),
        (
            "LeoDirectionSkewP95Ms",
            f'{_value(summary, "execution", "forward_reverse_skew_ms", "p95"):.2f}',
        ),
        (
            "LeoDirectionSkewP99Ms",
            f'{_value(summary, "execution", "forward_reverse_skew_ms", "p99"):.2f}',
        ),
        (
            "LeoRunLatenessMeanMs",
            f'{_value(summary, "execution", "run_mean_absolute_lateness_ms", "mean"):.2f}',
        ),
        (
            "LeoRunLatenessSdMs",
            f'{_value(summary, "execution", "run_mean_absolute_lateness_ms", "standard_deviation"):.2f}',
        ),
        (
            "LeoRunLatenessCi95HalfWidthMs",
            f'{_value(summary, "execution", "run_mean_absolute_lateness_ms", "mean_ci95_half_width"):.2f}',
        ),
        (
            "LeoRunP95LatenessMeanMs",
            f'{_value(summary, "execution", "run_p95_absolute_lateness_ms", "mean"):.2f}',
        ),
        (
            "LeoRunP95LatenessCi95HalfWidthMs",
            f'{_value(summary, "execution", "run_p95_absolute_lateness_ms", "mean_ci95_half_width"):.2f}',
        ),
        (
            "LeoRunForwardLatenessMeanMs",
            f'{_value(summary, "execution", "run_forward_mean_absolute_lateness_ms", "mean"):.2f}',
        ),
        (
            "LeoRunReverseLatenessMeanMs",
            f'{_value(summary, "execution", "run_reverse_mean_absolute_lateness_ms", "mean"):.2f}',
        ),
        (
            "LeoRunDirectionSkewMeanMs",
            f'{_value(summary, "execution", "run_mean_forward_reverse_skew_ms", "mean"):.2f}',
        ),
        (
            "LeoRunDirectionSkewSdMs",
            f'{_value(summary, "execution", "run_mean_forward_reverse_skew_ms", "standard_deviation"):.2f}',
        ),
        (
            "LeoRunDirectionSkewCi95HalfWidthMs",
            f'{_value(summary, "execution", "run_mean_forward_reverse_skew_ms", "mean_ci95_half_width"):.2f}',
        ),
    ]
    lines = [
        "% Generated from LEO-Replay repeated-lab summary; do not edit by hand.",
        *[f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in values],
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render VTCA paper LaTeX macros from a repeated-lab summary JSON"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.input.resolve() == args.output.resolve():
        parser.error("--input and --output must refer to different paths")

    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise PaperSummaryError("summary root must be a JSON object")
        payload = render_latex_macros(document)
    except (OSError, json.JSONDecodeError, PaperSummaryError) as exc:
        parser.error(str(exc))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
