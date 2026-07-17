#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_ping_csv(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            timeout = str(row.get("timeout", "0")).strip().lower() in {"1", "true", "yes"}
            if timeout:
                continue
            rtt_raw = str(row.get("rtt_ms", "")).strip()
            if not rtt_raw:
                continue
            rows.append((safe_float(row.get("time_s")), safe_float(rtt_raw)))
    return rows


def window_values(points: list[tuple[float, float]], start_sec: float, end_sec: float) -> list[float]:
    return [value for time_s, value in points if start_sec <= time_s <= end_sec]


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Learn event delay, jitter and spike parameters from measured/replayed RTT"
    )
    parser.add_argument("--events-json", required=True, type=Path)
    parser.add_argument("--measured-ping-csv", required=True, type=Path)
    parser.add_argument("--replay-ping-csv", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--learning-rate-delay", type=float, default=0.5)
    parser.add_argument("--learning-rate-jitter", type=float, default=0.5)
    parser.add_argument("--learning-rate-spike", type=float, default=0.5)
    parser.add_argument("--rtt-to-oneway-scale", type=float, default=0.5)
    parser.add_argument("--event-offset-sec", type=float, default=0.0)
    parser.add_argument("--window-margin-sec", type=float, default=0.3)
    parser.add_argument("--min-samples", type=int, default=3)
    parser.add_argument("--spike-stat", choices=["max", "p95", "p90"], default="max")
    parser.add_argument("--min-delay-ms", type=float, default=0.1)
    parser.add_argument("--max-delay-ms", type=float, default=2000.0)
    parser.add_argument("--min-jitter-ms", type=float, default=0.0)
    parser.add_argument("--max-jitter-ms", type=float, default=500.0)
    parser.add_argument("--min-spike-ms", type=float, default=0.0)
    parser.add_argument("--max-spike-ms", type=float, default=1000.0)
    parser.add_argument("--default-jitter-ms", type=float, default=1.0)
    parser.add_argument("--default-spike-ms", type=float, default=0.0)
    args = parser.parse_args()

    data = json.loads(args.events_json.read_text(encoding="utf-8"))
    v1 = isinstance(data, dict) and isinstance(data.get("events"), list)
    events = data["events"] if v1 else data
    if not isinstance(events, list):
        raise ValueError("events JSON must be a v1 document or legacy array")

    measured = load_ping_csv(args.measured_ping_csv)
    replayed = load_ping_csv(args.replay_ping_csv)
    output_rows: list[dict[str, Any]] = []

    for event in events:
        start_sec = safe_float(event.get("start_sec")) + args.event_offset_sec - args.window_margin_sec
        end_sec = safe_float(event.get("end_sec")) + args.event_offset_sec + args.window_margin_sec
        measured_values = window_values(measured, start_sec, end_sec)
        replay_values = window_values(replayed, start_sec, end_sec)

        new_event = dict(event)
        calibration = dict(event.get("calibration") or {}) if v1 else {}
        parameters = dict(event.get("parameters") or {}) if v1 else {}
        observations = dict(event.get("observations") or {}) if v1 else {}

        if len(measured_values) < args.min_samples or len(replay_values) < args.min_samples:
            updates: dict[str, Any] = {
                "measured_window_avg_rtt_ms": None,
                "replay_window_avg_rtt_ms": None,
                "measured_window_std_rtt_ms": None,
                "replay_window_std_rtt_ms": None,
                "measured_window_spike_rtt_ms": None,
                "replay_window_spike_rtt_ms": None,
                "rtt_error_ms": None,
                "jitter_error_ms": None,
                "spike_error_ms": None,
                "delay_correction_ms": 0.0,
                "jitter_correction_ms": 0.0,
                "spike_correction_ms": 0.0,
            }
        else:
            measured_avg = statistics.fmean(measured_values)
            replay_avg = statistics.fmean(replay_values)
            measured_std = statistics.pstdev(measured_values) if len(measured_values) > 1 else 0.0
            replay_std = statistics.pstdev(replay_values) if len(replay_values) > 1 else 0.0
            quantile = {"max": 1.0, "p95": 0.95, "p90": 0.90}[args.spike_stat]
            measured_spike = max(measured_values) if quantile == 1.0 else percentile(measured_values, quantile)
            replay_spike = max(replay_values) if quantile == 1.0 else percentile(replay_values, quantile)
            assert measured_spike is not None and replay_spike is not None

            rtt_error_ms = measured_avg - replay_avg
            delay_correction_ms = (
                rtt_error_ms * args.rtt_to_oneway_scale * args.learning_rate_delay
            )
            if v1:
                current_delay = safe_float(
                    calibration.get("calibrated_delay_ms", parameters.get("delay_ms", 0.0))
                )
            else:
                current_delay = safe_float(
                    event.get("calibrated_delay_ms", event.get("avg_delay_ms", 0.0))
                )
            updated_delay = clamp(
                current_delay + delay_correction_ms,
                args.min_delay_ms,
                args.max_delay_ms,
            )

            jitter_error_ms = measured_std - replay_std
            jitter_correction_ms = jitter_error_ms * args.learning_rate_jitter
            current_jitter = safe_float(
                calibration.get("calibrated_jitter_ms", parameters.get("jitter_ms", args.default_jitter_ms))
                if v1
                else event.get("calibrated_jitter_ms", args.default_jitter_ms),
                args.default_jitter_ms,
            )
            updated_jitter = clamp(
                current_jitter + jitter_correction_ms,
                args.min_jitter_ms,
                args.max_jitter_ms,
            )

            spike_error_ms = measured_spike - replay_spike
            spike_correction_ms = spike_error_ms * args.learning_rate_spike
            current_spike = safe_float(
                calibration.get("calibrated_spike_ms", parameters.get("spike_ms", args.default_spike_ms))
                if v1
                else event.get("calibrated_spike_ms", args.default_spike_ms),
                args.default_spike_ms,
            )
            updated_spike = clamp(
                current_spike + spike_correction_ms,
                args.min_spike_ms,
                args.max_spike_ms,
            )

            reference_delay = safe_float(
                calibration.get("reference_avg_delay_ms", observations.get("avg_delay_ms", 0.0))
                if v1
                else event.get("reference_avg_delay_ms", event.get("avg_delay_ms", 0.0))
            )
            updates = {
                "measured_window_avg_rtt_ms": round(measured_avg, 6),
                "replay_window_avg_rtt_ms": round(replay_avg, 6),
                "measured_window_std_rtt_ms": round(measured_std, 6),
                "replay_window_std_rtt_ms": round(replay_std, 6),
                "measured_window_spike_rtt_ms": round(measured_spike, 6),
                "replay_window_spike_rtt_ms": round(replay_spike, 6),
                "rtt_error_ms": round(rtt_error_ms, 6),
                "jitter_error_ms": round(jitter_error_ms, 6),
                "spike_error_ms": round(spike_error_ms, 6),
                "delay_correction_ms": round(delay_correction_ms, 6),
                "jitter_correction_ms": round(jitter_correction_ms, 6),
                "spike_correction_ms": round(spike_correction_ms, 6),
                "calibrated_delay_ms": round(updated_delay, 6),
                "calibrated_jitter_ms": round(updated_jitter, 6),
                "calibrated_spike_ms": round(updated_spike, 6),
                "delay_extra_ms": round(max(0.0, updated_delay - reference_delay), 6),
                "calibration_method": f"eventwise_closed_loop_delay_jitter_spike_{args.spike_stat}",
            }
            if v1:
                parameters["delay_ms"] = round(updated_delay, 6)
                parameters["jitter_ms"] = round(updated_jitter, 6)
                parameters["spike_ms"] = round(updated_spike, 6)

        if v1:
            calibration.update(updates)
            new_event["calibration"] = calibration
            new_event["parameters"] = parameters
        else:
            new_event.update(updates)
        output_rows.append(new_event)

    output: Any
    if v1:
        output = dict(data)
        output["events"] = output_rows
    else:
        output = output_rows
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {args.out_json}")


if __name__ == "__main__":
    main()
