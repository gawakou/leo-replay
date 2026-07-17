#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass
class IperfInterval:
    start_sec: float
    end_sec: float
    duration_sec: float
    rate_mbps: float
    loss_pct: float
    jitter_ms: float
    source: str


@dataclass
class PingPoint:
    time_s: float
    timestamp: float
    rtt_ms: float
    timeout: int
    seq: int
    ttl: int
    dst_ip: str


@dataclass
class GrpcPoint:
    time_s: float
    timestamp: float
    id: str
    hardware_version: str
    software_version: str
    state: str
    uptime: float
    pop_ping_drop_rate: float
    downlink_throughput_bps: float
    uplink_throughput_bps: float
    pop_ping_latency_ms: float
    alerts_bit_field: int
    fraction_obstructed: float
    currently_obstructed: str
    direction_azimuth: float
    direction_elevation: float
    is_snr_above_noise_floor: str
    gps_ready: str
    gps_enabled: str
    gps_sats: int
    raw_ok: int


@dataclass
class ProfileRow:
    start_sec: float
    end_sec: float
    duration_sec: float

    rate_mbps: float
    loss_pct: float
    delay_ms: float
    jitter_ms: float
    source: str

    ping_rtt_ms: float = 0.0
    ping_timeout_ratio: float = 0.0

    grpc_state: str = ""
    grpc_pop_ping_latency_ms: float = 0.0
    grpc_pop_ping_drop_rate: float = 0.0
    grpc_fraction_obstructed: float = 0.0
    grpc_currently_obstructed: str = ""

    state: str = "normal"
    event: str = ""
    severity: int = 0


@dataclass
class EventSegment:
    start_sec: float
    end_sec: float
    duration_sec: float
    event: str
    severity: int
    bins: int
    avg_rate_mbps: float
    max_loss_pct: float
    avg_delay_ms: float
    avg_ping_rtt_ms: float
    max_ping_timeout_ratio: float
    dominant_grpc_state: str
    avg_pop_ping_latency_ms: float
    max_fraction_obstructed: float


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        s = str(v).strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default


def safe_int(v: Any, default: int = 0) -> int:
    try:
        s = str(v).strip()
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def parse_iperf_json(path: Path) -> list[IperfInterval]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    intervals_raw = obj.get("intervals", [])
    if not intervals_raw:
        raise ValueError("No 'intervals' found in iperf JSON")

    out: list[IperfInterval] = []
    for item in intervals_raw:
        sum_obj = item.get("sum", {})
        streams = item.get("streams", [])

        start_sec = safe_float(sum_obj.get("start", 0.0))
        end_sec = safe_float(sum_obj.get("end", 0.0))
        duration_sec = max(0.0, end_sec - start_sec)

        if "lost_percent" in sum_obj or "jitter_ms" in sum_obj:
            out.append(
                IperfInterval(
                    start_sec=start_sec,
                    end_sec=end_sec,
                    duration_sec=duration_sec,
                    rate_mbps=safe_float(sum_obj.get("bits_per_second")) / 1_000_000.0,
                    loss_pct=safe_float(sum_obj.get("lost_percent")),
                    jitter_ms=safe_float(sum_obj.get("jitter_ms")),
                    source="udp",
                )
            )
        else:
            rate = 0.0
            if "bits_per_second" in sum_obj:
                rate = safe_float(sum_obj.get("bits_per_second")) / 1_000_000.0
            elif streams and "bits_per_second" in streams[0]:
                rate = safe_float(streams[0].get("bits_per_second")) / 1_000_000.0

            out.append(
                IperfInterval(
                    start_sec=start_sec,
                    end_sec=end_sec,
                    duration_sec=duration_sec,
                    rate_mbps=rate,
                    loss_pct=0.0,
                    jitter_ms=0.0,
                    source="tcp",
                )
            )
    return out


def load_ping_csv(path: Path) -> list[PingPoint]:
    out: list[PingPoint] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(
                PingPoint(
                    time_s=safe_float(row.get("time_s")),
                    timestamp=safe_float(row.get("timestamp")),
                    rtt_ms=safe_float(row.get("rtt_ms")),
                    timeout=safe_int(row.get("timeout")),
                    seq=safe_int(row.get("seq")),
                    ttl=safe_int(row.get("ttl")),
                    dst_ip=str(row.get("dst_ip", "")),
                )
            )
    return out


def load_grpc_csv(path: Path) -> list[GrpcPoint]:
    out: list[GrpcPoint] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(
                GrpcPoint(
                    time_s=safe_float(row.get("time_s")),
                    timestamp=safe_float(row.get("timestamp")),
                    id=str(row.get("id", "")),
                    hardware_version=str(row.get("hardware_version", "")),
                    software_version=str(row.get("software_version", "")),
                    state=str(row.get("state", "")),
                    uptime=safe_float(row.get("uptime")),
                    pop_ping_drop_rate=safe_float(row.get("pop_ping_drop_rate")),
                    downlink_throughput_bps=safe_float(row.get("downlink_throughput_bps")),
                    uplink_throughput_bps=safe_float(row.get("uplink_throughput_bps")),
                    pop_ping_latency_ms=safe_float(row.get("pop_ping_latency_ms")),
                    alerts_bit_field=safe_int(row.get("alerts_bit_field")),
                    fraction_obstructed=safe_float(row.get("fraction_obstructed")),
                    currently_obstructed=str(row.get("currently_obstructed", "")),
                    direction_azimuth=safe_float(row.get("direction_azimuth")),
                    direction_elevation=safe_float(row.get("direction_elevation")),
                    is_snr_above_noise_floor=str(row.get("is_snr_above_noise_floor", "")),
                    gps_ready=str(row.get("gps_ready", "")),
                    gps_enabled=str(row.get("gps_enabled", "")),
                    gps_sats=safe_int(row.get("gps_sats")),
                    raw_ok=safe_int(row.get("raw_ok"), 1),
                )
            )
    return out


def aggregate_iperf(intervals: list[IperfInterval], bin_sec: float) -> list[IperfInterval]:
    if not intervals:
        return []
    total_end = max(x.end_sec for x in intervals)
    bins: list[IperfInterval] = []
    left = 0.0

    while left < total_end - 1e-9:
        right = left + bin_sec
        chunk = [x for x in intervals if x.start_sec < right and x.end_sec > left]
        if not chunk:
            left = right
            continue

        w_sum = 0.0
        rate_sum = 0.0
        loss_sum = 0.0
        jitter_sum = 0.0
        source = chunk[0].source
        actual_end = min(right, total_end)

        for x in chunk:
            overlap = max(0.0, min(x.end_sec, actual_end) - max(x.start_sec, left))
            if overlap <= 0:
                continue
            w_sum += overlap
            rate_sum += x.rate_mbps * overlap
            loss_sum += x.loss_pct * overlap
            jitter_sum += x.jitter_ms * overlap

        bins.append(
            IperfInterval(
                start_sec=left,
                end_sec=actual_end,
                duration_sec=actual_end - left,
                rate_mbps=(rate_sum / w_sum) if w_sum else 0.0,
                loss_pct=(loss_sum / w_sum) if w_sum else 0.0,
                jitter_ms=(jitter_sum / w_sum) if w_sum else 0.0,
                source=source,
            )
        )
        left = right

    return bins


def mean_ping_rtt(points: list[PingPoint], start_sec: float, end_sec: float) -> float:
    vals = [p.rtt_ms for p in points if start_sec <= p.time_s < end_sec and p.timeout == 0]
    if not vals:
        return 0.0
    return statistics.fmean(vals)


def ping_timeout_ratio(points: list[PingPoint], start_sec: float, end_sec: float) -> float:
    vals = [p.timeout for p in points if start_sec <= p.time_s < end_sec]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def dominant_state(points: list[GrpcPoint], start_sec: float, end_sec: float) -> str:
    vals = [p.state for p in points if start_sec <= p.time_s < end_sec and p.raw_ok == 1 and p.state]
    if not vals:
        return ""
    return max(set(vals), key=vals.count)


def mean_grpc_value(points: list[GrpcPoint], start_sec: float, end_sec: float, attr: str) -> float:
    vals = []
    for p in points:
        if start_sec <= p.time_s < end_sec and p.raw_ok == 1:
            vals.append(safe_float(getattr(p, attr, 0.0)))
    if not vals:
        return 0.0
    return statistics.fmean(vals)


def any_currently_obstructed(points: list[GrpcPoint], start_sec: float, end_sec: float) -> str:
    vals = [
        str(p.currently_obstructed).strip()
        for p in points
        if start_sec <= p.time_s < end_sec and p.raw_ok == 1
    ]
    if any(v.lower() == "true" for v in vals):
        return "True"
    if any(v.lower() == "false" for v in vals):
        return "False"
    return ""


def build_profile(
    iperf_bins: list[IperfInterval],
    ping_points: list[PingPoint],
    grpc_points: list[GrpcPoint],
    *,
    base_delay_ms: float,
) -> list[ProfileRow]:
    rows: list[ProfileRow] = []

    for x in iperf_bins:
        avg_ping_rtt = mean_ping_rtt(ping_points, x.start_sec, x.end_sec)
        timeout_ratio = ping_timeout_ratio(ping_points, x.start_sec, x.end_sec)

        delay_ms = base_delay_ms
        if avg_ping_rtt > 0:
            delay_ms = avg_ping_rtt / 2.0

        row = ProfileRow(
            start_sec=round(x.start_sec, 6),
            end_sec=round(x.end_sec, 6),
            duration_sec=round(x.duration_sec, 6),
            rate_mbps=round(x.rate_mbps, 6),
            loss_pct=round(x.loss_pct, 6),
            delay_ms=round(delay_ms, 6),
            jitter_ms=round(x.jitter_ms, 6),
            source=x.source,
            ping_rtt_ms=round(avg_ping_rtt, 6),
            ping_timeout_ratio=round(timeout_ratio, 6),
            grpc_state=dominant_state(grpc_points, x.start_sec, x.end_sec),
            grpc_pop_ping_latency_ms=round(
                mean_grpc_value(grpc_points, x.start_sec, x.end_sec, "pop_ping_latency_ms"), 6
            ),
            grpc_pop_ping_drop_rate=round(
                mean_grpc_value(grpc_points, x.start_sec, x.end_sec, "pop_ping_drop_rate"), 6
            ),
            grpc_fraction_obstructed=round(
                mean_grpc_value(grpc_points, x.start_sec, x.end_sec, "fraction_obstructed"), 6
            ),
            grpc_currently_obstructed=any_currently_obstructed(grpc_points, x.start_sec, x.end_sec),
        )
        rows.append(row)

    return rows


def classify_rows(
    rows: list[ProfileRow],
    *,
    target_rate_mbps: float | None,
    degraded_loss_pct: float,
    severe_loss_pct: float,
    collapse_loss_pct: float,
    degraded_rate_ratio: float,
    collapse_rate_ratio: float,
    ping_timeout_degraded_ratio: float,
    ping_timeout_collapse_ratio: float,
    pop_ping_latency_high_ms: float,
    pop_ping_drop_high: float,
    obstruction_threshold: float,
) -> None:
    for row in rows:
        rate_ratio = 1.0
        if target_rate_mbps and target_rate_mbps > 0:
            rate_ratio = row.rate_mbps / target_rate_mbps

        row.state = "normal"
        row.severity = 0
        row.event = ""

        # obstruction first
        if (
            row.grpc_currently_obstructed.lower() == "true"
            or row.grpc_fraction_obstructed >= obstruction_threshold
        ):
            row.state = "degraded"
            row.event = "obstruction_suspected"
            row.severity = max(row.severity, 2)

        # gRPC state based
        if row.grpc_state and row.grpc_state != "CONNECTED":
            row.state = "degraded"
            row.event = "handover_suspected"
            row.severity = max(row.severity, 2)

        # ping timeout based
        if row.ping_timeout_ratio >= ping_timeout_collapse_ratio:
            row.state = "collapse"
            row.event = "outage_suspected"
            row.severity = max(row.severity, 4)
        elif row.ping_timeout_ratio >= ping_timeout_degraded_ratio:
            row.state = "degraded"
            if not row.event:
                row.event = "handover_suspected"
            row.severity = max(row.severity, 2)

        # iperf based
        if row.loss_pct >= collapse_loss_pct or rate_ratio <= collapse_rate_ratio:
            row.state = "collapse"
            if not row.event:
                row.event = "collapse_suspected"
            row.severity = max(row.severity, 3)
        elif row.loss_pct >= severe_loss_pct:
            if row.state != "collapse":
                row.state = "severe_loss"
            if not row.event:
                row.event = "handover_suspected"
            row.severity = max(row.severity, 2)
        elif row.loss_pct >= degraded_loss_pct or rate_ratio <= degraded_rate_ratio:
            if row.state == "normal":
                row.state = "degraded"
            if not row.event:
                row.event = "degradation_suspected"
            row.severity = max(row.severity, 1)

        # gRPC pop ping hints
        if (
            row.grpc_pop_ping_latency_ms >= pop_ping_latency_high_ms
            or row.grpc_pop_ping_drop_rate >= pop_ping_drop_high
        ):
            if row.state == "normal":
                row.state = "degraded"
            if not row.event:
                row.event = "backhaul_degradation_suspected"
            row.severity = max(row.severity, 1)


def build_segments(rows: list[ProfileRow], *, min_event_duration_sec: float) -> list[EventSegment]:
    segments: list[EventSegment] = []
    current: list[ProfileRow] = []

    def flush_chunk(chunk: list[ProfileRow]) -> None:
        if not chunk:
            return
        start_sec = chunk[0].start_sec
        end_sec = chunk[-1].end_sec
        duration_sec = end_sec - start_sec
        if duration_sec < min_event_duration_sec:
            return

        # choose representative event
        event_names = [r.event for r in chunk if r.event]
        event = max(set(event_names), key=event_names.count) if event_names else "degradation_suspected"

        grpc_states = [r.grpc_state for r in chunk if r.grpc_state]
        dom_state = max(set(grpc_states), key=grpc_states.count) if grpc_states else ""

        segments.append(
            EventSegment(
                start_sec=round(start_sec, 6),
                end_sec=round(end_sec, 6),
                duration_sec=round(duration_sec, 6),
                event=event,
                severity=max(r.severity for r in chunk),
                bins=len(chunk),
                avg_rate_mbps=round(statistics.fmean(r.rate_mbps for r in chunk), 6),
                max_loss_pct=round(max(r.loss_pct for r in chunk), 6),
                avg_delay_ms=round(statistics.fmean(r.delay_ms for r in chunk), 6),
                avg_ping_rtt_ms=round(statistics.fmean(r.ping_rtt_ms for r in chunk), 6),
                max_ping_timeout_ratio=round(max(r.ping_timeout_ratio for r in chunk), 6),
                dominant_grpc_state=dom_state,
                avg_pop_ping_latency_ms=round(
                    statistics.fmean(r.grpc_pop_ping_latency_ms for r in chunk), 6
                ),
                max_fraction_obstructed=round(
                    max(r.grpc_fraction_obstructed for r in chunk), 6
                ),
            )
        )

    for row in rows:
        if row.state == "normal":
            flush_chunk(current)
            current = []
        else:
            if not current:
                current = [row]
            else:
                prev = current[-1]
                # merge if contiguous and same event family
                if abs(row.start_sec - prev.end_sec) < 1e-6 and row.event == prev.event:
                    current.append(row)
                else:
                    flush_chunk(current)
                    current = [row]

    flush_chunk(current)
    return segments


def write_profile_json(path: Path, rows: list[ProfileRow]) -> None:
    path.write_text(json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=2), encoding="utf-8")


def write_profile_csv(path: Path, rows: list[ProfileRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()) if rows else [])
        if rows:
            writer.writeheader()
            for r in rows:
                writer.writerow(asdict(r))


def write_events_json(path: Path, rows: list[EventSegment]) -> None:
    path.write_text(json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=2), encoding="utf-8")


def summary(rows: list[ProfileRow], segments: list[EventSegment]) -> dict[str, Any]:
    return {
        "rows": len(rows),
        "segments": len(segments),
        "abnormal_rows": sum(1 for r in rows if r.state != "normal"),
        "event_types": sorted({s.event for s in segments}),
        "avg_rate_mbps": round(statistics.fmean(r.rate_mbps for r in rows), 6) if rows else 0.0,
        "avg_loss_pct": round(statistics.fmean(r.loss_pct for r in rows), 6) if rows else 0.0,
        "avg_ping_rtt_ms": round(statistics.fmean(r.ping_rtt_ms for r in rows), 6) if rows else 0.0,
        "avg_pop_ping_latency_ms": round(
            statistics.fmean(r.grpc_pop_ping_latency_ms for r in rows), 6
        ) if rows else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build event profile from iperf + ping + grpc")
    ap.add_argument("--iperf-json", required=True, type=Path)
    ap.add_argument("--ping-csv", required=True, type=Path)
    ap.add_argument("--grpc-csv", required=True, type=Path)

    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-csv", type=Path, default=None)
    ap.add_argument("--out-events-json", type=Path, default=None)

    ap.add_argument("--bin-sec", type=float, default=0.5)
    ap.add_argument("--base-delay-ms", type=float, default=20.0)
    ap.add_argument("--target-rate-mbps", type=float, default=None)

    ap.add_argument("--degraded-loss-pct", type=float, default=5.0)
    ap.add_argument("--severe-loss-pct", type=float, default=30.0)
    ap.add_argument("--collapse-loss-pct", type=float, default=80.0)
    ap.add_argument("--degraded-rate-ratio", type=float, default=0.7)
    ap.add_argument("--collapse-rate-ratio", type=float, default=0.3)

    ap.add_argument("--ping-timeout-degraded-ratio", type=float, default=0.25)
    ap.add_argument("--ping-timeout-collapse-ratio", type=float, default=0.8)

    ap.add_argument("--pop-ping-latency-high-ms", type=float, default=60.0)
    ap.add_argument("--pop-ping-drop-high", type=float, default=0.2)
    ap.add_argument("--obstruction-threshold", type=float, default=0.01)

    ap.add_argument("--min-event-duration-sec", type=float, default=0.5)

    args = ap.parse_args()

    iperf_intervals = parse_iperf_json(args.iperf_json)
    iperf_bins = aggregate_iperf(iperf_intervals, args.bin_sec)
    ping_points = load_ping_csv(args.ping_csv)
    grpc_points = load_grpc_csv(args.grpc_csv)

    rows = build_profile(
        iperf_bins,
        ping_points,
        grpc_points,
        base_delay_ms=args.base_delay_ms,
    )

    classify_rows(
        rows,
        target_rate_mbps=args.target_rate_mbps,
        degraded_loss_pct=args.degraded_loss_pct,
        severe_loss_pct=args.severe_loss_pct,
        collapse_loss_pct=args.collapse_loss_pct,
        degraded_rate_ratio=args.degraded_rate_ratio,
        collapse_rate_ratio=args.collapse_rate_ratio,
        ping_timeout_degraded_ratio=args.ping_timeout_degraded_ratio,
        ping_timeout_collapse_ratio=args.ping_timeout_collapse_ratio,
        pop_ping_latency_high_ms=args.pop_ping_latency_high_ms,
        pop_ping_drop_high=args.pop_ping_drop_high,
        obstruction_threshold=args.obstruction_threshold,
    )

    segments = build_segments(rows, min_event_duration_sec=args.min_event_duration_sec)

    write_profile_json(args.out_json, rows)
    if args.out_csv:
        write_profile_csv(args.out_csv, rows)
    if args.out_events_json:
        write_events_json(args.out_events_json, segments)

    print(json.dumps(summary(rows, segments), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
