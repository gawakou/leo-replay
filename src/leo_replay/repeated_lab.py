from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable


class RepeatedLabError(ValueError):
    """Raised when repeated lab artifacts are incomplete or invalid."""


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
            "minimum": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "maximum": 0.0,
        }
    return {
        "count": len(sample),
        "mean": sum(sample) / len(sample),
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
        direction = str(record.get("direction", ""))
        if direction not in {"forward", "reverse"}:
            raise RepeatedLabError(f"unknown direction {direction!r} at {path}:{line_number}")
        try:
            lateness = float(record["lateness_ms"])
            planned_sec = float(record["planned_sec"])
            applied_sec = float(record["applied_sec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RepeatedLabError(f"invalid timing fields at {path}:{line_number}") from exc
        records.append(
            {
                "direction": direction,
                "lateness_ms": lateness,
                "planned_sec": planned_sec,
                "applied_sec": applied_sec,
                "action": str(record.get("action", "")),
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


def summarize(root: Path) -> dict[str, Any]:
    fixed_paths = sorted(root.rglob("fixed-summary.json"))
    execution_paths = sorted(root.rglob("profile-execution.jsonl"))
    if not fixed_paths:
        raise RepeatedLabError(f"no fixed-summary.json files found below {root}")
    if not execution_paths:
        raise RepeatedLabError(f"no profile-execution.jsonl files found below {root}")

    fixed = [_load_object(path) for path in fixed_paths]
    failed_fixed = [path for path, item in zip(fixed_paths, fixed) if item.get("status") != "pass"]
    if failed_fixed:
        raise RepeatedLabError(
            "fixed-condition failures found: " + ", ".join(str(path) for path in failed_fixed)
        )

    forward_realization = [
        float(item["forward_throughput_mbps"]) / float(item["configured_forward_rate_mbps"])
        for item in fixed
    ]
    reverse_realization = [
        float(item["reverse_throughput_mbps"]) / float(item["configured_reverse_rate_mbps"])
        for item in fixed
    ]
    direction_ratio = [
        float(item["reverse_throughput_mbps"]) / float(item["forward_throughput_mbps"])
        for item in fixed
    ]

    signed_lateness: list[float] = []
    absolute_lateness: list[float] = []
    by_direction: dict[str, list[float]] = {"forward": [], "reverse": []}
    pair_skews: list[float] = []
    for path in execution_paths:
        records = _load_execution(path)
        pair_skews.extend(_pair_skews(path, records))
        for record in records:
            direction = str(record["direction"])
            value = float(record["lateness_ms"])
            signed_lateness.append(value)
            absolute_lateness.append(abs(value))
            by_direction[direction].append(abs(value))

    return {
        "fixed_runs": len(fixed_paths),
        "profile_runs": len(execution_paths),
        "fixed": {
            "rtt_delta_ms": _stats(float(item["rtt_delta_ms"]) for item in fixed),
            "forward_throughput_mbps": _stats(
                float(item["forward_throughput_mbps"]) for item in fixed
            ),
            "reverse_throughput_mbps": _stats(
                float(item["reverse_throughput_mbps"]) for item in fixed
            ),
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
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize repeated LEO-Replay bidirectional lab artifacts"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = summarize(args.input)
    except (OSError, RepeatedLabError, KeyError, ZeroDivisionError) as exc:
        parser.error(str(exc))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0
