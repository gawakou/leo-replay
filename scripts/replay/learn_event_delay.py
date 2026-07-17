#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def load_ping_csv(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = safe_float(row.get("time_s"))
            rtt = safe_float(row.get("rtt_ms"))
            rows.append((t, rtt))
    return rows


def window_values(
    points: list[tuple[float, float]],
    start_sec: float,
    end_sec: float,
) -> list[float]:
    return [v for t, v in points if start_sec <= t <= end_sec]


def mean_or_none(vals: list[float]) -> float | None:
    if not vals:
        return None
    return statistics.fmean(vals)


def std_or_none(vals: list[float]) -> float | None:
    if not vals:
        return None
    if len(vals) == 1:
        return 0.0
    return statistics.pstdev(vals)


def max_or_none(vals: list[float]) -> float | None:
    if not vals:
        return None
    return max(vals)


def percentile_or_none(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    xs = sorted(vals)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Learn calibrated delay+jitter+spike for each event from measured vs replay RTT"
    )
    ap.add_argument("--events-json", required=True, type=Path)
    ap.add_argument("--measured-ping-csv", required=True, type=Path)
    ap.add_argument("--replay-ping-csv", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)

    ap.add_argument("--learning-rate-delay", type=float, default=0.5,
                    help="Learning rate for delay update")
    ap.add_argument("--learning-rate-jitter", type=float, default=0.5,
                    help="Learning rate for jitter update")
    ap.add_argument("--learning-rate-spike", type=float, default=0.5,
                    help="Learning rate for spike update")

    ap.add_argument("--rtt-to-oneway-scale", type=float, default=0.5,
                    help="RTT mean error -> one-way delay correction")
    ap.add_argument("--event-offset-sec", type=float, default=0.0)
    ap.add_argument("--window-margin-sec", type=float, default=0.3)
    ap.add_argument("--min-samples", type=int, default=3)

    ap.add_argument("--spike-stat", choices=["max", "p95", "p90"], default="max",
                    help="Statistic used for spike learning")

    ap.add_argument("--min-delay-ms", type=float, default=0.1)
    ap.add_argument("--max-delay-ms", type=float, default=2000.0)
    ap.add_argument("--min-jitter-ms", type=float, default=0.0)
    ap.add_argument("--max-jitter-ms", type=float, default=500.0)
    ap.add_argument("--min-spike-ms", type=float, default=0.0)
    ap.add_argument("--max-spike-ms", type=float, default=1000.0)

    ap.add_argument("--default-jitter-ms", type=float, default=1.0)
    ap.add_argument("--default-spike-ms", type=float, default=0.0)

    args = ap.parse_args()

    events = json.loads(args.events_json.read_text(encoding="utf-8"))
    measured = load_ping_csv(args.measured_ping_csv)
    replay = load_ping_csv(args.replay_ping_csv)

    out = []

    for ev in events:
        start_sec = safe_float(ev.get("start_sec")) + args.event_offset_sec - args.window_margin_sec
        end_sec = safe_float(ev.get("end_sec")) + args.event_offset_sec + args.window_margin_sec

        measured_vals = window_values(measured, start_sec, end_sec)
        replay_vals = window_values(replay, start_sec, end_sec)

        new_ev = dict(ev)

        if len(measured_vals) < args.min_samples or len(replay_vals) < args.min_samples:
            new_ev["measured_window_avg_rtt_ms"] = None
            new_ev["replay_window_avg_rtt_ms"] = None
            new_ev["measured_window_std_rtt_ms"] = None
            new_ev["replay_window_std_rtt_ms"] = None
            new_ev["measured_window_spike_rtt_ms"] = None
            new_ev["replay_window_spike_rtt_ms"] = None
            new_ev["rtt_error_ms"] = None
            new_ev["jitter_error_ms"] = None
            new_ev["spike_error_ms"] = None
            new_ev["delay_correction_ms"] = 0.0
            new_ev["jitter_correction_ms"] = 0.0
            new_ev["spike_correction_ms"] = 0.0
            out.append(new_ev)
            continue

        measured_avg = mean_or_none(measured_vals)
        replay_avg = mean_or_none(replay_vals)
        measured_std = std_or_none(measured_vals)
        replay_std = std_or_none(replay_vals)

        if args.spike_stat == "max":
            measured_spike = max_or_none(measured_vals)
            replay_spike = max_or_none(replay_vals)
        elif args.spike_stat == "p95":
            measured_spike = percentile_or_none(measured_vals, 0.95)
            replay_spike = percentile_or_none(replay_vals, 0.95)
        else:
            measured_spike = percentile_or_none(measured_vals, 0.90)
            replay_spike = percentile_or_none(replay_vals, 0.90)

        if (
            measured_avg is None or replay_avg is None or
            measured_std is None or replay_std is None or
            measured_spike is None or replay_spike is None
        ):
            new_ev["measured_window_avg_rtt_ms"] = None
            new_ev["replay_window_avg_rtt_ms"] = None
            new_ev["measured_window_std_rtt_ms"] = None
            new_ev["replay_window_std_rtt_ms"] = None
            new_ev["measured_window_spike_rtt_ms"] = None
            new_ev["replay_window_spike_rtt_ms"] = None
            new_ev["rtt_error_ms"] = None
            new_ev["jitter_error_ms"] = None
            new_ev["spike_error_ms"] = None
            new_ev["delay_correction_ms"] = 0.0
            new_ev["jitter_correction_ms"] = 0.0
            new_ev["spike_correction_ms"] = 0.0
            out.append(new_ev)
            continue

        # delay update
        rtt_error_ms = measured_avg - replay_avg
        delay_correction_ms = (
            rtt_error_ms
            * args.rtt_to_oneway_scale
            * args.learning_rate_delay
        )

        current_delay = safe_float(
            ev.get("calibrated_delay_ms", ev.get("avg_delay_ms", 0.0))
        )
        updated_delay = clamp(
            current_delay + delay_correction_ms,
            args.min-delay-ms if False else args.min_delay_ms,  # keep linter happy? no
            args.max_delay_ms,
        )

        # jitter update
        jitter_error_ms = measured_std - replay_std
        jitter_correction_ms = jitter_error_ms * args.learning_rate_jitter

        current_jitter = safe_float(
            ev.get("calibrated_jitter_ms", args.default_jitter_ms),
            args.default_jitter_ms,
        )
        updated_jitter = clamp(
            current_jitter + jitter_correction_ms,
            args.min_jitter_ms,
            args.max_jitter_ms,
        )

        # spike update
        spike_error_ms = measured_spike - replay_spike
        spike_correction_ms = spike_error_ms * args.learning_rate_spike

        current_spike = safe_float(
            ev.get("calibrated_spike_ms", args.default_spike_ms),
            args.default_spike_ms,
        )
        updated_spike = clamp(
            current_spike + spike_correction_ms,
            args.min_spike_ms,
            args.max_spike_ms,
        )

        new_ev["measured_window_avg_rtt_ms"] = round(measured_avg, 6)
        new_ev["replay_window_avg_rtt_ms"] = round(replay_avg, 6)
        new_ev["measured_window_std_rtt_ms"] = round(measured_std, 6)
        new_ev["replay_window_std_rtt_ms"] = round(replay_std, 6)
        new_ev["measured_window_spike_rtt_ms"] = round(measured_spike, 6)
        new_ev["replay_window_spike_rtt_ms"] = round(replay_spike, 6)

        new_ev["rtt_error_ms"] = round(rtt_error_ms, 6)
        new_ev["jitter_error_ms"] = round(jitter_error_ms, 6)
        new_ev["spike_error_ms"] = round(spike_error_ms, 6)

        new_ev["delay_correction_ms"] = round(delay_correction_ms, 6)
        new_ev["jitter_correction_ms"] = round(jitter_correction_ms, 6)
        new_ev["spike_correction_ms"] = round(spike_correction_ms, 6)

        new_ev["calibrated_delay_ms"] = round(updated_delay, 6)
        new_ev["calibrated_jitter_ms"] = round(updated_jitter, 6)
        new_ev["calibrated_spike_ms"] = round(updated_spike, 6)

        reference_delay = safe_float(ev.get("reference_avg_delay_ms", ev.get("avg_delay_ms", 0.0)))
        new_ev["delay_extra_ms"] = round(max(0.0, updated_delay - reference_delay), 6)
        new_ev["calibration_method"] = f"eventwise_closed_loop_delay_jitter_spike_{args.spike_stat}"

        out.append(new_ev)

    args.out_json.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"Saved: {args.out_json}")


if __name__ == "__main__":
    main()
