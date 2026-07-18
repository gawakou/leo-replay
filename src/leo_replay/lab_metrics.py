from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PING_SUMMARY_RE = re.compile(
    r"=\s*([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+)\s*ms"
)
PING_SAMPLE_RE = re.compile(r"time[=<]([0-9.]+)\s*ms")


class LabMetricError(ValueError):
    """Raised when a virtual-lab result cannot be parsed or validated."""


def parse_ping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    samples = [float(value) for value in PING_SAMPLE_RE.findall(text)]
    summary_match = PING_SUMMARY_RE.search(text)
    if summary_match:
        minimum, average, maximum, deviation = map(float, summary_match.groups())
    elif samples:
        minimum = min(samples)
        maximum = max(samples)
        average = sum(samples) / len(samples)
        deviation = 0.0
    else:
        raise LabMetricError(f"no ping RTT values found in {path}")
    return {
        "minimum_ms": minimum,
        "average_ms": average,
        "maximum_ms": maximum,
        "deviation_ms": deviation,
        "samples_ms": samples,
        "sample_count": len(samples),
    }


def _nested(document: dict[str, Any], *keys: str) -> Any:
    current: Any = document
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def parse_iperf_mbps(path: Path) -> float:
    document = json.loads(path.read_text(encoding="utf-8"))
    candidates = (
        _nested(document, "end", "sum_received", "bits_per_second"),
        _nested(document, "end", "sum_sent", "bits_per_second"),
        _nested(document, "end", "sum", "bits_per_second"),
    )
    for value in candidates:
        if isinstance(value, (int, float)):
            return float(value) / 1_000_000.0
    raise LabMetricError(f"iperf3 throughput was not found in {path}")


def parse_execution_log(path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LabMetricError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise LabMetricError(f"execution record at {path}:{line_number} is not an object")
        records.append(record)
    if not records:
        raise LabMetricError(f"execution log is empty: {path}")
    directions = sorted({str(record.get("direction", "")) for record in records})
    lateness = [abs(float(record.get("lateness_ms", 0.0))) for record in records]
    return {
        "records": len(records),
        "directions": directions,
        "maximum_absolute_lateness_ms": max(lateness, default=0.0),
        "average_absolute_lateness_ms": sum(lateness) / len(lateness) if lateness else 0.0,
    }


def _write_result(path: Path | None, result: dict[str, Any]) -> None:
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if path is None:
        print(payload, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    print(payload, end="")


def verify_fixed(args: argparse.Namespace) -> int:
    baseline = parse_ping(args.baseline_ping)
    impaired = parse_ping(args.impaired_ping)
    forward_mbps = parse_iperf_mbps(args.forward_iperf)
    reverse_mbps = parse_iperf_mbps(args.reverse_iperf)
    rtt_delta = impaired["average_ms"] - baseline["average_ms"]

    errors: list[str] = []
    if rtt_delta < args.min_rtt_delta_ms:
        errors.append(
            f"RTT increase {rtt_delta:.3f} ms is below {args.min_rtt_delta_ms:.3f} ms"
        )
    if rtt_delta > args.max_rtt_delta_ms:
        errors.append(
            f"RTT increase {rtt_delta:.3f} ms exceeds {args.max_rtt_delta_ms:.3f} ms"
        )

    for direction, measured, configured in (
        ("forward", forward_mbps, args.forward_rate_mbps),
        ("reverse", reverse_mbps, args.reverse_rate_mbps),
    ):
        if measured < configured * args.minimum_rate_ratio:
            errors.append(
                f"{direction} throughput {measured:.3f} Mbit/s is unexpectedly low "
                f"for configured {configured:.3f} Mbit/s"
            )
        if measured > configured * args.maximum_rate_ratio:
            errors.append(
                f"{direction} throughput {measured:.3f} Mbit/s exceeds the tolerance "
                f"for configured {configured:.3f} Mbit/s"
            )
    if reverse_mbps <= forward_mbps * args.minimum_direction_ratio:
        errors.append(
            f"reverse throughput {reverse_mbps:.3f} Mbit/s is not sufficiently greater "
            f"than forward throughput {forward_mbps:.3f} Mbit/s"
        )

    result = {
        "status": "pass" if not errors else "fail",
        "baseline_ping": baseline,
        "impaired_ping": impaired,
        "rtt_delta_ms": rtt_delta,
        "forward_throughput_mbps": forward_mbps,
        "reverse_throughput_mbps": reverse_mbps,
        "configured_forward_rate_mbps": args.forward_rate_mbps,
        "configured_reverse_rate_mbps": args.reverse_rate_mbps,
        "errors": errors,
    }
    _write_result(args.output, result)
    return 0 if not errors else 2


def verify_profile(args: argparse.Namespace) -> int:
    ping = parse_ping(args.ping)
    execution = parse_execution_log(args.execution_log)
    samples = ping["samples_ms"]
    observed_range = max(samples) - min(samples) if samples else 0.0
    errors: list[str] = []
    if ping["sample_count"] < args.minimum_samples:
        errors.append(
            f"only {ping['sample_count']} ping samples were recorded; "
            f"at least {args.minimum_samples} are required"
        )
    if observed_range < args.minimum_rtt_range_ms:
        errors.append(
            f"RTT range {observed_range:.3f} ms is below {args.minimum_rtt_range_ms:.3f} ms"
        )
    if set(execution["directions"]) != {"forward", "reverse"}:
        errors.append(f"execution log directions are {execution['directions']!r}")
    if execution["maximum_absolute_lateness_ms"] > args.maximum_lateness_ms:
        errors.append(
            "maximum tc application lateness "
            f"{execution['maximum_absolute_lateness_ms']:.3f} ms exceeds "
            f"{args.maximum_lateness_ms:.3f} ms"
        )

    result = {
        "status": "pass" if not errors else "fail",
        "ping": ping,
        "observed_rtt_range_ms": observed_range,
        "execution": execution,
        "errors": errors,
    }
    _write_result(args.output, result)
    return 0 if not errors else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate virtual bidirectional lab results")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixed = subparsers.add_parser("fixed", help="Validate fixed delay and rate shaping")
    fixed.add_argument("--baseline-ping", required=True, type=Path)
    fixed.add_argument("--impaired-ping", required=True, type=Path)
    fixed.add_argument("--forward-iperf", required=True, type=Path)
    fixed.add_argument("--reverse-iperf", required=True, type=Path)
    fixed.add_argument("--forward-rate-mbps", type=float, default=20.0)
    fixed.add_argument("--reverse-rate-mbps", type=float, default=60.0)
    fixed.add_argument("--min-rtt-delta-ms", type=float, default=35.0)
    fixed.add_argument("--max-rtt-delta-ms", type=float, default=100.0)
    fixed.add_argument("--minimum-rate-ratio", type=float, default=0.10)
    fixed.add_argument("--maximum-rate-ratio", type=float, default=1.50)
    fixed.add_argument("--minimum-direction-ratio", type=float, default=1.30)
    fixed.add_argument("--output", type=Path)
    fixed.set_defaults(handler=verify_fixed)

    profile = subparsers.add_parser("profile", help="Validate a directional profile replay")
    profile.add_argument("--ping", required=True, type=Path)
    profile.add_argument("--execution-log", required=True, type=Path)
    profile.add_argument("--minimum-samples", type=int, default=20)
    profile.add_argument("--minimum-rtt-range-ms", type=float, default=40.0)
    profile.add_argument("--maximum-lateness-ms", type=float, default=1000.0)
    profile.add_argument("--output", type=Path)
    profile.set_defaults(handler=verify_profile)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, LabMetricError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
