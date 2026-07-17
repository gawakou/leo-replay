#!/usr/bin/env python3
"""Merge measured Starlink ping.csv + iperf.json + grpc.csv into replay profile.csv.

Default input formats match the user's sample dataset:
- ping.csv columns: time_s,timestamp,rtt_ms,timeout,...
- grpc.csv columns: time_s,timestamp,state,pop_ping_drop_rate,downlink_throughput_bps,
  uplink_throughput_bps,pop_ping_latency_ms,fraction_obstructed,...
- iperf.json: iperf3 JSON with intervals[].sum.bits_per_second

Output columns:
sec,delay_ms,jitter_ms,loss_pct,rate_mbit,reorder_pct,correlation_pct,note
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def safe_float(v: Any, default: float | None = None) -> float | None:
    if v is None:
        return default
    try:
        if isinstance(v, str) and not v.strip():
            return default
        out = float(v)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


@dataclass
class SeriesPoint:
    t: float
    values: dict[str, Any]


def read_csv_series(path: Path) -> list[dict[str, Any]]:
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def parse_ping(path: Path) -> list[SeriesPoint]:
    rows = read_csv_series(path)
    pts: list[SeriesPoint] = []
    for r in rows:
        t = safe_float(r.get('time_s'))
        if t is None:
            continue
        timeout = int(safe_float(r.get('timeout'), 0) or 0)
        rtt = safe_float(r.get('rtt_ms'))
        pts.append(SeriesPoint(t, {
            'delay_ms': None if timeout else rtt,
            'timeout': timeout,
        }))
    return pts


def parse_grpc(path: Path) -> list[SeriesPoint]:
    rows = read_csv_series(path)
    pts: list[SeriesPoint] = []
    for r in rows:
        t = safe_float(r.get('time_s'))
        if t is None:
            continue
        pts.append(SeriesPoint(t, {
            'state': (r.get('state') or '').strip(),
            'pop_ping_drop_rate': safe_float(r.get('pop_ping_drop_rate')),
            'pop_ping_latency_ms': safe_float(r.get('pop_ping_latency_ms')),
            'fraction_obstructed': safe_float(r.get('fraction_obstructed')),
            'downlink_mbit': (safe_float(r.get('downlink_throughput_bps')) or 0.0) / 1e6,
            'uplink_mbit': (safe_float(r.get('uplink_throughput_bps')) or 0.0) / 1e6,
            'currently_obstructed': str(r.get('currently_obstructed') or '').lower() == 'true',
        }))
    return pts


def parse_iperf_json(path: Path) -> list[SeriesPoint]:
    with path.open(encoding='utf-8') as f:
        obj = json.load(f)
    intervals = obj.get('intervals', [])
    pts: list[SeriesPoint] = []
    for it in intervals:
        s = it.get('sum') or {}
        t = safe_float(s.get('end'))
        if t is None:
            continue
        pts.append(SeriesPoint(t, {
            'rate_mbit': (safe_float(s.get('bits_per_second')) or 0.0) / 1e6,
            'bytes': safe_float(s.get('bytes')),
            'packets': safe_float(s.get('packets')),
        }))
    return pts


def nearest(points: list[SeriesPoint], t: float, max_gap: float) -> dict[str, Any] | None:
    if not points:
        return None
    best = None
    best_gap = None
    for p in points:
        gap = abs(p.t - t)
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best = p
    if best is None or best_gap is None or best_gap > max_gap:
        return None
    return best.values


def prev_value(points: list[SeriesPoint], t: float) -> dict[str, Any] | None:
    prev = None
    for p in points:
        if p.t <= t:
            prev = p.values
        else:
            break
    return prev


def estimate_jitter(delays: list[float | None], window: int = 5, fallback: float = 2.0) -> list[float]:
    out: list[float] = []
    history: list[float] = []
    prev = None
    for d in delays:
        if d is None:
            out.append(out[-1] if out else fallback)
            continue
        if prev is not None:
            history.append(abs(d - prev))
        prev = d
        recent = history[-window:]
        out.append(max(fallback, mean(recent) if recent else fallback))
    return out


def build_profile(
    ping_pts: list[SeriesPoint],
    iperf_pts: list[SeriesPoint],
    grpc_pts: list[SeriesPoint],
    resample_sec: float,
    duration: float | None,
    max_gap_ping: float,
    max_gap_iperf: float,
    max_gap_grpc: float,
    base_reorder_pct: float,
    correlation_pct: float,
) -> list[dict[str, Any]]:
    max_t = 0.0
    for pts in (ping_pts, iperf_pts, grpc_pts):
        if pts:
            max_t = max(max_t, pts[-1].t)
    if duration is not None:
        max_t = min(max_t, duration)
    timeline = []
    t = 0.0
    while t <= max_t + 1e-9:
        timeline.append(round(t, 6))
        t += resample_sec

    delays: list[float | None] = []
    rows: list[dict[str, Any]] = []
    last_delay = 30.0
    last_loss = 0.0
    last_rate = 10.0

    for sec in timeline:
        ping = nearest(ping_pts, sec, max_gap_ping) or prev_value(ping_pts, sec) or {}
        iperf = nearest(iperf_pts, sec, max_gap_iperf) or prev_value(iperf_pts, sec) or {}
        grpc = nearest(grpc_pts, sec, max_gap_grpc) or prev_value(grpc_pts, sec) or {}

        delay = ping.get('delay_ms')
        if delay is None:
            delay = grpc.get('pop_ping_latency_ms')
        delay = safe_float(delay, last_delay)

        timeout = int(ping.get('timeout', 0) or 0)
        ping_loss = 100.0 if timeout else 0.0
        grpc_drop = safe_float(grpc.get('pop_ping_drop_rate'), 0.0) or 0.0
        grpc_loss = clamp(grpc_drop * 100.0, 0.0, 100.0)
        loss_pct = max(ping_loss, grpc_loss)

        # Prefer iperf replay rate. Fallback to grpc downlink if missing.
        rate_mbit = safe_float(iperf.get('rate_mbit'))
        if rate_mbit is None or rate_mbit <= 0:
            rate_mbit = safe_float(grpc.get('downlink_mbit'), last_rate)

        obstruct = safe_float(grpc.get('fraction_obstructed'), 0.0) or 0.0
        currently_obstructed = bool(grpc.get('currently_obstructed', False))
        state = str(grpc.get('state', '') or '')

        # Obstruction-based correction to make replay reflect terminal state changes.
        if obstruct > 0:
            delay *= (1.0 + min(obstruct, 1.0) * 1.5)
            loss_pct = clamp(loss_pct + min(obstruct, 1.0) * 20.0, 0.0, 100.0)
            rate_mbit *= (1.0 - min(obstruct, 1.0) * 0.7)
        if currently_obstructed:
            delay *= 1.2
            loss_pct = clamp(loss_pct + 5.0, 0.0, 100.0)
            rate_mbit *= 0.9
        if state and state != 'CONNECTED':
            delay *= 1.3
            loss_pct = clamp(loss_pct + 10.0, 0.0, 100.0)
            rate_mbit *= 0.8

        delay = round(clamp(delay, 0.0, 5000.0), 3)
        loss_pct = round(clamp(loss_pct, 0.0, 100.0), 3)
        rate_mbit = round(max(rate_mbit, 0.1), 3)

        note_parts = []
        if state:
            note_parts.append(state)
        if obstruct > 0:
            note_parts.append(f'obstructed={obstruct:.3f}')
        if currently_obstructed:
            note_parts.append('currently_obstructed')
        note = '|'.join(note_parts) if note_parts else 'merged'

        delays.append(delay)
        rows.append({
            'sec': round(sec, 3),
            'delay_ms': delay,
            'loss_pct': loss_pct,
            'rate_mbit': rate_mbit,
            'reorder_pct': round(base_reorder_pct, 3),
            'correlation_pct': round(correlation_pct, 3),
            'note': note,
        })

        last_delay, last_loss, last_rate = delay, loss_pct, rate_mbit

    jitters = estimate_jitter(delays)
    for row, jitter in zip(rows, jitters):
        row['jitter_ms'] = round(jitter, 3)
    return rows


def write_profile(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ['sec', 'delay_ms', 'jitter_ms', 'loss_pct', 'rate_mbit', 'reorder_pct', 'correlation_pct', 'note']
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    ap = argparse.ArgumentParser(description='Merge Starlink measurement files into replay profile.csv')
    ap.add_argument('--ping', required=True, help='Path to ping.csv')
    ap.add_argument('--iperf', required=True, help='Path to iperf.json')
    ap.add_argument('--grpc', required=True, help='Path to grpc.csv')
    ap.add_argument('--output', required=True, help='Output profile.csv')
    ap.add_argument('--resample-sec', type=float, default=0.5, help='Output interval in seconds')
    ap.add_argument('--duration', type=float, default=None, help='Optional maximum duration to export')
    ap.add_argument('--max-gap-ping', type=float, default=0.6)
    ap.add_argument('--max-gap-iperf', type=float, default=0.8)
    ap.add_argument('--max-gap-grpc', type=float, default=1.2)
    ap.add_argument('--reorder-pct', type=float, default=0.0)
    ap.add_argument('--correlation-pct', type=float, default=20.0)
    args = ap.parse_args()

    ping_pts = parse_ping(Path(args.ping))
    iperf_pts = parse_iperf_json(Path(args.iperf))
    grpc_pts = parse_grpc(Path(args.grpc))
    rows = build_profile(
        ping_pts=ping_pts,
        iperf_pts=iperf_pts,
        grpc_pts=grpc_pts,
        resample_sec=args.resample_sec,
        duration=args.duration,
        max_gap_ping=args.max_gap_ping,
        max_gap_iperf=args.max_gap_iperf,
        max_gap_grpc=args.max_gap_grpc,
        base_reorder_pct=args.reorder_pct,
        correlation_pct=args.correlation_pct,
    )
    write_profile(Path(args.output), rows)
    print(f'Wrote {len(rows)} rows to {args.output}')


if __name__ == '__main__':
    main()
