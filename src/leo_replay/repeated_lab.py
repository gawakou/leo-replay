from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable


class RepeatedLabError(ValueError):
    """Raised when repeated lab artifacts are incomplete or invalid."""


_TIMING_CONSISTENCY_TOLERANCE_MS = 0.002


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _stats(values: Iterable[float]) -> dict[str, float | int]:
    sample = [float(value) for value in values]
    if not sample:
        return {
            "count": 0,
            "mean": 0.0,
            "standard_deviation": 0.0,
            "mean_ci95_half_width": 0.0,
            "minimum": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "maximum": 0.0,
        }

    mean = sum(sample) / len(sample)
    if len(sample) > 1:
        variance = sum((value - mean) ** 2 for value in sample) / (len(sample) - 1)
        standard_deviation = math.sqrt(variance)
        mean_ci95_half_width = 1.96 * standard_deviation / math.sqrt(len(sample))
    else:
        standard_deviation = 0.0
        mean_ci95_half_width = 0.0

    return {
        "count": len(sample),
        "mean": mean,
        "standard_deviation": standard_deviation,
        "mean_ci95_half_width": mean_ci95_half_width,
        "minimum": min(sample),
        "p50": _percentile(sample, 0.50),
        "p95": _percentile(sample, 0.95),
        "p99": _percentile(sample, 0.99),
        "maximum": max(sample),
    }


def _load_object(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RepeatedLabError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise RepeatedLabError(f"expected JSON object in {path}")
    return document


def _finite_fixed_field(
    item: dict[str, Any], field: str, path: Path, *, require_positive: bool = False
) -> float:
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RepeatedLabError(f"fixed summary at {path} has invalid {field} {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise RepeatedLabError(f"fixed summary at {path} has non-finite {field} {value!r}")
    if require_positive and number <= 0.0:
        raise RepeatedLabError(f"fixed summary at {path} requires positive {field}, got {value!r}")
    return number


def _finite_timing_field(record: dict[str, Any], field: str, path: Path, line_number: int) -> float:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RepeatedLabError(
            f"execution record at {path}:{line_number} has invalid {field} {value!r}"
        )
    number = float(value)
    if not math.isfinite(number):
        raise RepeatedLabError(
            f"execution record at {path}:{line_number} has non-finite {field} {value!r}"
        )
    return number


def _validate_timing_consistency(
    path: Path,
    line_number: int,
    *,
    planned_sec: float,
    applied_sec: float,
    lateness_ms: float,
) -> None:
    expected_lateness_ms = (applied_sec - planned_sec) * 1000.0
    if abs(lateness_ms - expected_lateness_ms) > _TIMING_CONSISTENCY_TOLERANCE_MS:
        raise RepeatedLabError(
            f"execution record at {path}:{line_number} has inconsistent timing: "
            f"lateness_ms={lateness_ms!r}, expected approximately {expected_lateness_ms!r}"
        )


def _load_execution(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RepeatedLabError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise RepeatedLabError(f"execution record at {path}:{line_number} is not an object")
        direction = record.get("direction")
        if direction not in {"forward", "reverse"}:
            raise RepeatedLabError(f"unknown direction {direction!r} at {path}:{line_number}")
        action = record.get("action")
        if not isinstance(action, str) or not action.strip():
            raise RepeatedLabError(
                f"execution record at {path}:{line_number} has invalid action {action!r}"
            )
        lateness = _finite_timing_field(record, "lateness_ms", path, line_number)
        planned_sec = _finite_timing_field(record, "planned_sec", path, line_number)
        applied_sec = _finite_timing_field(record, "applied_sec", path, line_number)
        _validate_timing_consistency(
            path,
            line_number,
            planned_sec=planned_sec,
            applied_sec=applied_sec,
            lateness_ms=lateness,
        )
        records.append(
            {
                "direction": direction,
                "lateness_ms": lateness,
                "planned_sec": planned_sec,
                "applied_sec": applied_sec,
                "action": action,
                "event_id": record.get("event_id"),
            }
        )
    if not records:
        raise RepeatedLabError(f"execution log is empty: {path}")
    return records


def _pair_skews(path: Path, records: list[dict[str, Any]]) -> list[float]:
    pairs: dict[tuple[str, str, float], dict[str, float]] = {}
    for record in records:
        key = (
            str(record["action"]),
            "" if record["event_id"] is None else str(record["event_id"]),
            float(record["planned_sec"]),
        )
        direction = str(record["direction"])
        pair = pairs.setdefault(key, {})
        if direction in pair:
            raise RepeatedLabError(f"duplicate {direction} application for {key!r} in {path}")
        pair[direction] = float(record["applied_sec"])

    skews: list[float] = []
    for key, pair in pairs.items():
        if set(pair) != {"forward", "reverse"}:
            raise RepeatedLabError(f"incomplete forward/reverse application pair {key!r} in {path}")
        skews.append(abs(pair["reverse"] - pair["forward"]) * 1000.0)
    return skews


def _validate_paired_runs(
    root: Path, fixed_paths: list[Path], execution_paths: list[Path]
) -> None:
    fixed_runs = {path.parent.relative_to(root) for path in fixed_paths}
    execution_runs = {path.parent.relative_to(root) for path in execution_paths}
    missing_execution = sorted(fixed_runs - execution_runs, key=str)
    missing_fixed = sorted(execution_runs - fixed_runs, key=str)
    if not missing_execution and not missing_fixed:
        return

    details: list[str] = []
    if missing_execution:
        details.append(
            "missing profile-execution.jsonl for "
            + ", ".join(str(path) for path in missing_execution)
        )
    if missing_fixed:
        details.append(
            "missing fixed-summary.json for " + ", ".join(str(path) for path in missing_fixed)
        )
    raise RepeatedLabError("unpaired repeated-lab artifacts: " + "; ".join(details))


def summarize(root: Path) -> dict[str, Any]:
    fixed_paths = sorted(root.rglob("fixed-summary.json"))
    execution_paths = sorted(root.rglob("profile-execution.jsonl"))
    if not fixed_paths:
        raise RepeatedLabError(f"no fixed-summary.json files found below {root}")
    if not execution_paths:
        raise RepeatedLabError(f"no profile-execution.jsonl files found below {root}")
    _validate_paired_runs(root, fixed_paths, execution_paths)

    fixed = [_load_object(path) for path in fixed_paths]
    failed_fixed = [path for path, item in zip(fixed_paths, fixed) if item.get("status") != "pass"]
    if failed_fixed:
        raise RepeatedLabError(
            "fixed-condition failures found: " + ", ".join(str(path) for path in failed_fixed)
        )

    rtt_delta = [
        _finite_fixed_field(item, "rtt_delta_ms", path)
        for path, item in zip(fixed_paths, fixed)
    ]
    forward_throughput = [
        _finite_fixed_field(item, "forward_throughput_mbps", path, require_positive=True)
        for path, item in zip(fixed_paths, fixed)
    ]
    reverse_throughput = [
        _finite_fixed_field(item, "reverse_throughput_mbps", path, require_positive=True)
        for path, item in zip(fixed_paths, fixed)
    ]
    configured_forward = [
        _finite_fixed_field(item, "configured_forward_rate_mbps", path, require_positive=True)
        for path, item in zip(fixed_paths, fixed)
    ]
    configured_reverse = [
        _finite_fixed_field(item, "configured_reverse_rate_mbps", path, require_positive=True)
        for path, item in zip(fixed_paths, fixed)
    ]

    forward_realization = [
        throughput / configured
        for throughput, configured in zip(forward_throughput, configured_forward)
    ]
    reverse_realization = [
        throughput / configured
        for throughput, configured in zip(reverse_throughput, configured_reverse)
    ]
    direction_ratio = [
        reverse / forward for reverse, forward in zip(reverse_throughput, forward_throughput)
    ]

    signed_lateness: list[float] = []
    absolute_lateness: list[float] = []
    by_direction: dict[str, list[float]] = {"forward": [], "reverse": []}
    pair_skews: list[float] = []
    run_mean_absolute_lateness: list[float] = []
    run_p95_absolute_lateness: list[float] = []
    run_forward_mean_absolute_lateness: list[float] = []
    run_reverse_mean_absolute_lateness: list[float] = []
    run_mean_forward_reverse_skew: list[float] = []

    for path in execution_paths:
        records = _load_execution(path)
        run_skews = _pair_skews(path, records)
        pair_skews.extend(run_skews)

        run_absolute: list[float] = []
        run_by_direction: dict[str, list[float]] = {"forward": [], "reverse": []}
        for record in records:
            direction = str(record["direction"])
            value = float(record["lateness_ms"])
            absolute = abs(value)
            signed_lateness.append(value)
            absolute_lateness.append(absolute)
            by_direction[direction].append(absolute)
            run_absolute.append(absolute)
            run_by_direction[direction].append(absolute)

        if not run_by_direction["forward"] or not run_by_direction["reverse"]:
            raise RepeatedLabError(f"execution log lacks both directions: {path}")
        run_mean_absolute_lateness.append(sum(run_absolute) / len(run_absolute))
        run_p95_absolute_lateness.append(_percentile(run_absolute, 0.95))
        run_forward_mean_absolute_lateness.append(
            sum(run_by_direction["forward"]) / len(run_by_direction["forward"])
        )
        run_reverse_mean_absolute_lateness.append(
            sum(run_by_direction["reverse"]) / len(run_by_direction["reverse"])
        )
        run_mean_forward_reverse_skew.append(sum(run_skews) / len(run_skews))

    return {
        "fixed_runs": len(fixed_paths),
        "profile_runs": len(execution_paths),
        "fixed": {
            "rtt_delta_ms": _stats(rtt_delta),
            "forward_throughput_mbps": _stats(forward_throughput),
            "reverse_throughput_mbps": _stats(reverse_throughput),
            "forward_realization_ratio": _stats(forward_realization),
            "reverse_realization_ratio": _stats(reverse_realization),
            "reverse_forward_ratio": _stats(direction_ratio),
        },
        "execution": {
            "signed_lateness_ms": _stats(signed_lateness),
            "absolute_lateness_ms": _stats(absolute_lateness),
            "forward_absolute_lateness_ms": _stats(by_direction["forward"]),
            "reverse_absolute_lateness_ms": _stats(by_direction["reverse"]),
            "forward_reverse_skew_ms": _stats(pair_skews),
            "run_mean_absolute_lateness_ms": _stats(run_mean_absolute_lateness),
            "run_p95_absolute_lateness_ms": _stats(run_p95_absolute_lateness),
            "run_forward_mean_absolute_lateness_ms": _stats(
                run_forward_mean_absolute_lateness
            ),
            "run_reverse_mean_absolute_lateness_ms": _stats(
                run_reverse_mean_absolute_lateness
            ),
            "run_mean_forward_reverse_skew_ms": _stats(run_mean_forward_reverse_skew),
        },
    }


def _validate_output_path(root: Path, output: Path) -> None:
    output_path = output.resolve(strict=False)
    input_paths = [
        *root.rglob("fixed-summary.json"),
        *root.rglob("profile-execution.jsonl"),
    ]
    for input_path in input_paths:
        if input_path.resolve(strict=False) == output_path:
            raise RepeatedLabError(
                f"output path collides with repeated-lab input artifact: {input_path}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize repeated LEO-Replay bidirectional lab artifacts"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            _validate_output_path(args.input, args.output)
        result = summarize(args.input)
    except (OSError, RepeatedLabError, KeyError, ZeroDivisionError) as exc:
        parser.error(str(exc))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0
