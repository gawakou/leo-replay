#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class IperfPoint:
    time_s: float
    throughput_mbps: float


@dataclass
class PingPoint:
    time_s: float
    rtt_ms: float


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def load_iperf_json(path: Path) -> list[IperfPoint]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    intervals = obj.get("intervals", [])
    out: list[IperfPoint] = []

    for item in intervals:
        sum_obj = item.get("sum", {})
        start = safe_float(sum_obj.get("start", 0.0))
        end = safe_float(sum_obj.get("end", 0.0))
        bits_per_second = safe_float(sum_obj.get("bits_per_second", 0.0))
        mbps = bits_per_second / 1_000_000.0
        center_t = (start + end) / 2.0
        out.append(IperfPoint(time_s=round(center_t, 6), throughput_mbps=mbps))

    return out


def load_ping_csv(path: Path) -> list[PingPoint]:
    out: list[PingPoint] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])

        if "rtt_ms" not in fieldnames or "time_s" not in fieldnames:
            raise ValueError(f"{path} must contain time_s and rtt_ms")

        for row in reader:
            out.append(
                PingPoint(
                    time_s=safe_float(row["time_s"]),
                    rtt_ms=safe_float(row["rtt_ms"]),
                )
            )
    return out


def aggregate_series_mean(points: list[tuple[float, float]], bin_sec: float) -> list[tuple[float, float]]:
    if not points:
        return []

    points = sorted(points, key=lambda x: x[0])
    total_end = max(t for t, _ in points)
    out: list[tuple[float, float]] = []

    left = 0.0
    while left <= total_end + 1e-9:
        right = left + bin_sec
        vals = [v for t, v in points if left <= t < right]
        if vals:
            out.append((round(left + bin_sec / 2.0, 6), statistics.fmean(vals)))
        left = right

    return out


def align_by_nearest(
    a: list[tuple[float, float]],
    b: list[tuple[float, float]],
    tolerance_sec: float,
) -> tuple[list[float], list[float], list[float]]:
    if not a or not b:
        return [], [], []

    b_sorted = sorted(b, key=lambda x: x[0])
    out_t: list[float] = []
    out_a: list[float] = []
    out_b: list[float] = []

    j = 0
    for ta, va in sorted(a, key=lambda x: x[0]):
        while j + 1 < len(b_sorted) and abs(b_sorted[j + 1][0] - ta) <= abs(b_sorted[j][0] - ta):
            j += 1

        tb, vb = b_sorted[j]
        if abs(tb - ta) <= tolerance_sec:
            out_t.append(ta)
            out_a.append(va)
            out_b.append(vb)

    return out_t, out_a, out_b


def mae(xs: list[float], ys: list[float]) -> float:
    if not xs or not ys or len(xs) != len(ys):
        return 0.0
    return statistics.fmean(abs(x - y) for x, y in zip(xs, ys))


def rmse(xs: list[float], ys: list[float]) -> float:
    if not xs or not ys or len(xs) != len(ys):
        return 0.0
    return math.sqrt(statistics.fmean((x - y) ** 2 for x, y in zip(xs, ys)))


def corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(ys) < 2 or len(xs) != len(ys):
        return 0.0

    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)

    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))

    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def summary_stats(name: str, vals: list[float]) -> dict[str, float]:
    if not vals:
        return {
            f"{name}_count": 0,
            f"{name}_min": 0.0,
            f"{name}_avg": 0.0,
            f"{name}_max": 0.0,
        }
    return {
        f"{name}_count": len(vals),
        f"{name}_min": min(vals),
        f"{name}_avg": statistics.fmean(vals),
        f"{name}_max": max(vals),
    }


def print_block(title: str, stats: dict[str, float]) -> None:
    print(f"\n[{title}]")
    for k, v in stats.items():
        if isinstance(v, int):
            print(f"{k}: {v}")
        else:
            print(f"{k}: {v:.6f}")


def load_event_times(path: Path | None) -> list[tuple[float, float, str]]:
    if path is None or not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for row in rows:
        out.append((
            safe_float(row.get("start_sec")),
            safe_float(row.get("end_sec")),
            str(row.get("event", "")),
        ))
    return out


def window_stats(
    aligned_t: list[float],
    measured_vals: list[float],
    replay_vals: list[float],
    start_sec: float,
    end_sec: float,
) -> tuple[list[float], list[float]]:
    idx = [i for i, t in enumerate(aligned_t) if start_sec <= t <= end_sec]
    if not idx:
        return [], []
    return [measured_vals[i] for i in idx], [replay_vals[i] for i in idx]


def std_or_zero(vals: list[float]) -> float:
    if not vals:
        return 0.0
    if len(vals) == 1:
        return 0.0
    return statistics.pstdev(vals)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare measured vs replayed throughput/RTT")
    ap.add_argument("--measured-iperf-json", required=True, type=Path)
    ap.add_argument("--replay-iperf-json", required=True, type=Path)
    ap.add_argument("--measured-ping-csv", required=True, type=Path)
    ap.add_argument("--replay-ping-csv", required=True, type=Path)
    ap.add_argument("--events-json", type=Path, default=None)

    ap.add_argument("--iperf-bin-sec", type=float, default=0.2)
    ap.add_argument("--ping-bin-sec", type=float, default=0.2)
    ap.add_argument("--align-tolerance-sec", type=float, default=0.11)
    ap.add_argument("--event-window-margin-sec", type=float, default=0.0)
    args = ap.parse_args()

    measured_iperf = load_iperf_json(args.measured_iperf_json)
    replay_iperf = load_iperf_json(args.replay_iperf_json)

    measured_ping = load_ping_csv(args.measured_ping_csv)
    replay_ping = load_ping_csv(args.replay_ping_csv)

    measured_iperf_binned = aggregate_series_mean(
        [(p.time_s, p.throughput_mbps) for p in measured_iperf],
        args.iperf_bin_sec,
    )
    replay_iperf_binned = aggregate_series_mean(
        [(p.time_s, p.throughput_mbps) for p in replay_iperf],
        args.iperf_bin_sec,
    )

    measured_ping_binned = aggregate_series_mean(
        [(p.time_s, p.rtt_ms) for p in measured_ping],
        args.ping_bin_sec,
    )
    replay_ping_binned = aggregate_series_mean(
        [(p.time_s, p.rtt_ms) for p in replay_ping],
        args.ping_bin_sec,
    )

    _, m_thr, r_thr = align_by_nearest(
        measured_iperf_binned,
        replay_iperf_binned,
        args.align_tolerance_sec,
    )
    aligned_t_rtt, m_rtt, r_rtt = align_by_nearest(
        measured_ping_binned,
        replay_ping_binned,
        args.align_tolerance_sec,
    )

    print_block("Measured throughput", summary_stats("measured_thr", m_thr))
    print_block("Replay throughput", summary_stats("replay_thr", r_thr))
    print_block(
        "Throughput comparison",
        {
            "throughput_points": len(m_thr),
            "throughput_mae_mbps": mae(m_thr, r_thr),
            "throughput_rmse_mbps": rmse(m_thr, r_thr),
            "throughput_corr": corr(m_thr, r_thr),
        },
    )

    print_block("Measured RTT", summary_stats("measured_rtt", m_rtt))
    print_block("Replay RTT", summary_stats("replay_rtt", r_rtt))
    print_block(
        "RTT comparison",
        {
            "rtt_points": len(m_rtt),
            "rtt_mae_ms": mae(m_rtt, r_rtt),
            "rtt_rmse_ms": rmse(m_rtt, r_rtt),
            "rtt_corr": corr(m_rtt, r_rtt),
        },
    )

    events = load_event_times(args.events_json)
    event_mae_vals: list[float] = []
    event_rmse_vals: list[float] = []
    event_std_abs_err_vals: list[float] = []
    event_std_sq_err_vals: list[float] = []

    if events:
        print("\n[Event windows]")
        for start_sec, end_sec, event_name in events:
            start_sec -= args.event_window_margin_sec
            end_sec += args.event_window_margin_sec

            m_vals, r_vals = window_stats(aligned_t_rtt, m_rtt, r_rtt, start_sec, end_sec)
            if not m_vals or not r_vals:
                print(f"{event_name}: {start_sec:.3f}-{end_sec:.3f}s -> no aligned RTT points")
                continue

            measured_avg = statistics.fmean(m_vals)
            replay_avg = statistics.fmean(r_vals)
            measured_std = std_or_zero(m_vals)
            replay_std = std_or_zero(r_vals)

            local_mae = mae(m_vals, r_vals)
            local_rmse = rmse(m_vals, r_vals)
            local_std_abs_err = abs(measured_std - replay_std)
            local_std_sq_err = (measured_std - replay_std) ** 2

            event_mae_vals.append(local_mae)
            event_rmse_vals.append(local_rmse)
            event_std_abs_err_vals.append(local_std_abs_err)
            event_std_sq_err_vals.append(local_std_sq_err)

            print(
                f"{event_name}: {start_sec:.3f}-{end_sec:.3f}s "
                f"| measured_avg_rtt={measured_avg:.6f} ms "
                f"| replay_avg_rtt={replay_avg:.6f} ms "
                f"| measured_std_rtt={measured_std:.6f} ms "
                f"| replay_std_rtt={replay_std:.6f} ms "
                f"| mae={local_mae:.6f} ms "
                f"| std_abs_err={local_std_abs_err:.6f} ms"
            )

        if event_mae_vals:
            print_block(
                "Event-window RTT comparison",
                {
                    "event_window_count": len(event_mae_vals),
                    "event_window_rtt_mae_ms": statistics.fmean(event_mae_vals),
                    "event_window_rtt_rmse_ms": statistics.fmean(event_rmse_vals),
                    "event_window_rtt_mae_max_ms": max(event_mae_vals),
                },
            )

            print_block(
                "Event-window RTT std comparison",
                {
                    "event_window_rtt_std_mae_ms": statistics.fmean(event_std_abs_err_vals),
                    "event_window_rtt_std_rmse_ms": math.sqrt(statistics.fmean(event_std_sq_err_vals)),
                    "event_window_rtt_std_mae_max_ms": max(event_std_abs_err_vals),
                },
            )
        else:
            print_block(
                "Event-window RTT comparison",
                {
                    "event_window_count": 0,
                    "event_window_rtt_mae_ms": 0.0,
                    "event_window_rtt_rmse_ms": 0.0,
                    "event_window_rtt_mae_max_ms": 0.0,
                },
            )
            print_block(
                "Event-window RTT std comparison",
                {
                    "event_window_rtt_std_mae_ms": 0.0,
                    "event_window_rtt_std_rmse_ms": 0.0,
                    "event_window_rtt_std_mae_max_ms": 0.0,
                },
            )


if __name__ == "__main__":
    main()
