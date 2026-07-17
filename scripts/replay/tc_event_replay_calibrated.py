#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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

    # learned / calibrated fields
    calibrated_delay_ms: float = 0.0
    delay_extra_ms: float = 0.0
    calibrated_jitter_ms: float = 0.0
    jitter_correction_ms: float = 0.0
    calibrated_spike_ms: float = 0.0
    spike_correction_ms: float = 0.0


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def load_events(path: Path) -> list[EventSegment]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    out: list[EventSegment] = []
    for row in rows:
        out.append(
            EventSegment(
                start_sec=safe_float(row.get("start_sec")),
                end_sec=safe_float(row.get("end_sec")),
                duration_sec=safe_float(row.get("duration_sec")),
                event=str(row.get("event", "")),
                severity=safe_int(row.get("severity")),
                bins=safe_int(row.get("bins")),
                avg_rate_mbps=safe_float(row.get("avg_rate_mbps")),
                max_loss_pct=safe_float(row.get("max_loss_pct")),
                avg_delay_ms=safe_float(row.get("avg_delay_ms")),
                avg_ping_rtt_ms=safe_float(row.get("avg_ping_rtt_ms")),
                max_ping_timeout_ratio=safe_float(row.get("max_ping_timeout_ratio")),
                dominant_grpc_state=str(row.get("dominant_grpc_state", "")),
                avg_pop_ping_latency_ms=safe_float(row.get("avg_pop_ping_latency_ms")),
                max_fraction_obstructed=safe_float(row.get("max_fraction_obstructed")),
                calibrated_delay_ms=safe_float(row.get("calibrated_delay_ms")),
                delay_extra_ms=safe_float(row.get("delay_extra_ms")),
                calibrated_jitter_ms=safe_float(row.get("calibrated_jitter_ms")),
                jitter_correction_ms=safe_float(row.get("jitter_correction_ms")),
                calibrated_spike_ms=safe_float(row.get("calibrated_spike_ms")),
                spike_correction_ms=safe_float(row.get("spike_correction_ms")),
            )
        )
    out.sort(key=lambda x: x.start_sec)
    return out


def shift_events(events: list[EventSegment], offset_sec: float) -> None:
    if offset_sec == 0.0:
        return
    for ev in events:
        ev.start_sec += offset_sec
        ev.end_sec += offset_sec


def run(cmd: list[str], *, dry_run: bool = False, check: bool = True) -> None:
    print("$ " + " ".join(shlex.quote(x) for x in cmd))
    if not dry_run:
        subprocess.run(cmd, check=check)


def tc_reset(iface: str, *, dry_run: bool = False) -> None:
    run(["tc", "qdisc", "del", "dev", iface, "root"], dry_run=dry_run, check=False)


def tc_show(iface: str, *, dry_run: bool = False) -> None:
    run(["tc", "qdisc", "show", "dev", iface], dry_run=dry_run, check=False)


def apply_tc(
    iface: str,
    *,
    rate_mbps: float,
    delay_ms: float,
    jitter_ms: float,
    loss_pct: float,
    burst_kbit: int,
    tbf_latency_ms: int,
    dry_run: bool = False,
) -> None:
    rate_str = f"{max(rate_mbps, 0.1):.6f}mbit"
    delay_str = f"{max(delay_ms, 0.1):.6f}ms"
    jitter_str = f"{max(jitter_ms, 0.0):.6f}ms"
    loss_str = f"{clamp(loss_pct, 0.0, 99.0):.6f}%"

    run(
        [
            "tc", "qdisc", "replace",
            "dev", iface,
            "root", "handle", "1:",
            "tbf",
            "rate", rate_str,
            "burst", f"{burst_kbit}kbit",
            "latency", f"{tbf_latency_ms}ms",
        ],
        dry_run=dry_run,
        check=True,
    )

    run(
        [
            "tc", "qdisc", "replace",
            "dev", iface,
            "parent", "1:1",
            "handle", "10:",
            "netem",
            "delay", delay_str, jitter_str,
            "loss", loss_str,
        ],
        dry_run=dry_run,
        check=True,
    )


def event_to_tc_params(
    ev: EventSegment,
    *,
    default_rate_mbps: float,
    default_delay_ms: float,
    default_loss_pct: float,
    default_jitter_ms: float,
    default_spike_ms: float,
    max_effective_spike_ms: float,
    handover_loss_pct: float,
    outage_loss_pct: float,
    obstruction_loss_pct: float,
) -> tuple[float, float, float, float, float, float]:
    """
    Returns:
      rate_mbps, effective_delay_ms, effective_jitter_ms, loss_pct, base_delay_ms, spike_ms
    """
    rate_mbps = default_rate_mbps
    base_delay_ms = default_delay_ms
    jitter_ms = default_jitter_ms
    loss_pct = default_loss_pct
    spike_ms = default_spike_ms

    # learned/calibrated delay
    if ev.calibrated_delay_ms > 0:
        base_delay_ms = max(default_delay_ms, ev.calibrated_delay_ms)

    # learned/calibrated jitter
    if ev.calibrated_jitter_ms > 0:
        jitter_ms = max(0.0, ev.calibrated_jitter_ms)

    # learned/calibrated spike
    if ev.calibrated_spike_ms > 0:
        spike_ms = clamp(ev.calibrated_spike_ms, 0.0, max_effective_spike_ms)

    # event-type specific fallback tweaks
    if ev.event == "backhaul_degradation_suspected":
        jitter_ms = max(jitter_ms, default_jitter_ms)

    elif ev.event == "handover_suspected":
        jitter_ms = max(jitter_ms, 2.0)
        loss_pct = max(default_loss_pct, handover_loss_pct)

    elif ev.event == "outage_suspected":
        jitter_ms = max(jitter_ms, 3.0)
        loss_pct = max(default_loss_pct, outage_loss_pct)

    elif ev.event == "obstruction_suspected":
        jitter_ms = max(jitter_ms, 2.0)
        loss_pct = max(default_loss_pct, obstruction_loss_pct)

    elif ev.event == "collapse_suspected":
        jitter_ms = max(jitter_ms, 2.0)
        loss_pct = max(default_loss_pct, max(10.0, ev.max_loss_pct))

    elif ev.event == "degradation_suspected":
        jitter_ms = max(jitter_ms, 1.0)

    effective_delay_ms = base_delay_ms + spike_ms
    return rate_mbps, effective_delay_ms, jitter_ms, loss_pct, base_delay_ms, spike_ms


def replay_events(
    events: list[EventSegment],
    iface: str,
    *,
    default_rate_mbps: float,
    default_delay_ms: float,
    default_loss_pct: float,
    default_jitter_ms: float,
    default_spike_ms: float,
    max_effective_spike_ms: float,
    burst_kbit: int,
    tbf_latency_ms: int,
    dry_run: bool,
    time_scale: float,
    loop: bool,
    handover_loss_pct: float,
    outage_loss_pct: float,
    obstruction_loss_pct: float,
    restore_default_between_events: bool,
    start_delay_sec: float,
) -> None:
    if not events:
        raise ValueError("No events found.")

    while True:
        if start_delay_sec > 0:
            print(f"[wait] start replay after {start_delay_sec:.3f}s")
            if not dry_run:
                time.sleep(start_delay_sec)

        start_wall = time.monotonic()
        last_end = 0.0

        # initial baseline
        apply_tc(
            iface,
            rate_mbps=default_rate_mbps,
            delay_ms=default_delay_ms,
            jitter_ms=default_jitter_ms,
            loss_pct=default_loss_pct,
            burst_kbit=burst_kbit,
            tbf_latency_ms=tbf_latency_ms,
            dry_run=dry_run,
        )

        for ev in events:
            # restore baseline in gaps
            if restore_default_between_events and ev.start_sec > last_end:
                target = last_end / time_scale
                now_elapsed = time.monotonic() - start_wall
                remaining = target - now_elapsed
                if remaining > 0 and not dry_run:
                    time.sleep(remaining)

                apply_tc(
                    iface,
                    rate_mbps=default_rate_mbps,
                    delay_ms=default_delay_ms,
                    jitter_ms=default_jitter_ms,
                    loss_pct=default_loss_pct,
                    burst_kbit=burst_kbit,
                    tbf_latency_ms=tbf_latency_ms,
                    dry_run=dry_run,
                )

            # wait until event start
            target = ev.start_sec / time_scale
            now_elapsed = time.monotonic() - start_wall
            remaining = target - now_elapsed
            if remaining > 0 and not dry_run:
                time.sleep(remaining)

            (
                rate_mbps,
                effective_delay_ms,
                jitter_ms,
                loss_pct,
                base_delay_ms,
                spike_ms,
            ) = event_to_tc_params(
                ev,
                default_rate_mbps=default_rate_mbps,
                default_delay_ms=default_delay_ms,
                default_loss_pct=default_loss_pct,
                default_jitter_ms=default_jitter_ms,
                default_spike_ms=default_spike_ms,
                max_effective_spike_ms=max_effective_spike_ms,
                handover_loss_pct=handover_loss_pct,
                outage_loss_pct=outage_loss_pct,
                obstruction_loss_pct=obstruction_loss_pct,
            )

            print(
                f"[event] {ev.event} "
                f"t={ev.start_sec:.3f}-{ev.end_sec:.3f}s "
                f"dur={ev.duration_sec:.3f}s "
                f"rate={rate_mbps:.3f}Mbps "
                f"delay={effective_delay_ms:.3f}ms "
                f"(base={base_delay_ms:.3f} + spike={spike_ms:.3f}) "
                f"jitter={jitter_ms:.3f}ms "
                f"loss={loss_pct:.3f}%"
            )

            apply_tc(
                iface,
                rate_mbps=rate_mbps,
                delay_ms=effective_delay_ms,
                jitter_ms=jitter_ms,
                loss_pct=loss_pct,
                burst_kbit=burst_kbit,
                tbf_latency_ms=tbf_latency_ms,
                dry_run=dry_run,
            )

            last_end = ev.end_sec

        # restore baseline after final event
        target = last_end / time_scale
        now_elapsed = time.monotonic() - start_wall
        remaining = target - now_elapsed
        if remaining > 0 and not dry_run:
            time.sleep(remaining)

        apply_tc(
            iface,
            rate_mbps=default_rate_mbps,
            delay_ms=default_delay_ms,
            jitter_ms=default_jitter_ms,
            loss_pct=default_loss_pct,
            burst_kbit=burst_kbit,
            tbf_latency_ms=tbf_latency_ms,
            dry_run=dry_run,
        )

        if not loop:
            break


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay calibrated events_with_grpc.json using tc")
    ap.add_argument("--events-json", required=True, type=Path)
    ap.add_argument("--iface", required=True)

    ap.add_argument("--default-rate-mbps", type=float, default=260.0)
    ap.add_argument("--default-delay-ms", type=float, default=15.0)
    ap.add_argument("--default-loss-pct", type=float, default=0.0)
    ap.add_argument("--default-jitter-ms", type=float, default=1.0)
    ap.add_argument("--default-spike-ms", type=float, default=0.0)
    ap.add_argument("--max-effective-spike-ms", type=float, default=200.0)

    ap.add_argument("--burst-kbit", type=int, default=32)
    ap.add_argument("--tbf-latency-ms", type=int, default=400)

    ap.add_argument("--handover-loss-pct", type=float, default=5.0)
    ap.add_argument("--outage-loss-pct", type=float, default=99.0)
    ap.add_argument("--obstruction-loss-pct", type=float, default=10.0)

    ap.add_argument("--time-scale", type=float, default=1.0)
    ap.add_argument("--start-delay-sec", type=float, default=0.0)
    ap.add_argument("--event-offset-sec", type=float, default=0.0)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--restore-default-between-events", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset-only", action="store_true")
    ap.add_argument("--show-only", action="store_true")

    args = ap.parse_args()

    if args.reset_only:
        tc_reset(args.iface, dry_run=args.dry_run)
        return

    if args.show_only:
        tc_show(args.iface, dry_run=args.dry_run)
        return

    events = load_events(args.events_json)
    shift_events(events, args.event_offset_sec)

    replay_events(
        events,
        args.iface,
        default_rate_mbps=args.default_rate_mbps,
        default_delay_ms=args.default_delay_ms,
        default_loss_pct=args.default_loss_pct,
        default_jitter_ms=args.default_jitter_ms,
        default_spike_ms=args.default_spike_ms,
        max_effective_spike_ms=args.max_effective_spike_ms,
        burst_kbit=args.burst_kbit,
        tbf_latency_ms=args.tbf_latency_ms,
        dry_run=args.dry_run,
        time_scale=args.time_scale,
        loop=args.loop,
        handover_loss_pct=args.handover_loss_pct,
        outage_loss_pct=args.outage_loss_pct,
        obstruction_loss_pct=args.obstruction_loss_pct,
        restore_default_between_events=args.restore_default_between_events,
        start_delay_sec=args.start_delay_sec,
    )


if __name__ == "__main__":
    main()
