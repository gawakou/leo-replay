#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


@dataclass
class EventSegment:
    start_sec: float
    end_sec: float
    duration_sec: float
    event: str
    severity: int = 0
    bins: int = 0
    avg_rate_mbps: float = 0.0
    max_loss_pct: float = 0.0
    avg_delay_ms: float = 0.0
    avg_ping_rtt_ms: float = 0.0
    max_ping_timeout_ratio: float = 0.0
    dominant_grpc_state: str = ""
    avg_pop_ping_latency_ms: float = 0.0
    max_fraction_obstructed: float = 0.0
    calibrated_delay_ms: float = 0.0
    delay_extra_ms: float = 0.0
    calibrated_jitter_ms: float = 0.0
    jitter_correction_ms: float = 0.0
    calibrated_spike_ms: float = 0.0
    spike_correction_ms: float = 0.0
    replay_rate_mbps: float = 0.0
    replay_delay_ms: float = 0.0
    replay_jitter_ms: float = 0.0
    replay_loss_pct: float = 0.0
    replay_spike_ms: float = 0.0
    event_id: str = ""


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _flatten_v1_event(event: dict[str, Any]) -> dict[str, Any]:
    parameters = event.get("parameters") or {}
    observations = event.get("observations") or {}
    calibration = event.get("calibration") or {}
    row: dict[str, Any] = {
        "event_id": event.get("event_id", ""),
        "start_sec": event.get("start_sec", 0.0),
        "end_sec": event.get("end_sec", 0.0),
        "duration_sec": event.get("duration_sec", 0.0),
        "event": event.get("event_type", "custom"),
        "severity": event.get("severity", 0),
        "bins": observations.get("bins", 0),
        "avg_rate_mbps": observations.get("avg_rate_mbps", parameters.get("rate_mbit", 0.0)),
        "max_loss_pct": observations.get("max_loss_pct", parameters.get("loss_pct", 0.0)),
        "avg_delay_ms": observations.get("avg_delay_ms", parameters.get("delay_ms", 0.0)),
        "avg_ping_rtt_ms": observations.get("avg_ping_rtt_ms", 0.0),
        "max_ping_timeout_ratio": observations.get("max_ping_timeout_ratio", 0.0),
        "dominant_grpc_state": observations.get("dominant_grpc_state", ""),
        "avg_pop_ping_latency_ms": observations.get("avg_pop_ping_latency_ms", 0.0),
        "max_fraction_obstructed": observations.get("max_fraction_obstructed", 0.0),
        "replay_rate_mbps": parameters.get("rate_mbit", 0.0),
        "replay_delay_ms": parameters.get("delay_ms", 0.0),
        "replay_jitter_ms": parameters.get("jitter_ms", 0.0),
        "replay_loss_pct": parameters.get("loss_pct", 0.0),
        "replay_spike_ms": parameters.get("spike_ms", 0.0),
    }
    row.update(calibration)
    return row


def load_events(path: Path) -> list[EventSegment]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("events"), list):
        rows = [_flatten_v1_event(event) for event in data["events"]]
    elif isinstance(data, list):
        rows = data
    else:
        raise ValueError("events JSON must be a v1 event document or a legacy event array")

    out: list[EventSegment] = []
    for index, row in enumerate(rows, start=1):
        start = safe_float(row.get("start_sec"))
        end = safe_float(row.get("end_sec"))
        duration = safe_float(row.get("duration_sec"), end - start)
        if end <= start and duration > 0:
            end = start + duration
        if start < 0 or end <= start:
            raise ValueError(f"invalid event interval at row {index}: {start}..{end}")
        out.append(
            EventSegment(
                start_sec=start,
                end_sec=end,
                duration_sec=end - start,
                event=str(row.get("event", "custom")),
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
                replay_rate_mbps=safe_float(row.get("replay_rate_mbps")),
                replay_delay_ms=safe_float(row.get("replay_delay_ms")),
                replay_jitter_ms=safe_float(row.get("replay_jitter_ms")),
                replay_loss_pct=safe_float(row.get("replay_loss_pct")),
                replay_spike_ms=safe_float(row.get("replay_spike_ms")),
                event_id=str(row.get("event_id", f"EV-{index:04d}")),
            )
        )
    out.sort(key=lambda event: event.start_sec)
    return out


def shift_events(events: list[EventSegment], offset_sec: float) -> None:
    for event in events:
        event.start_sec += offset_sec
        event.end_sec += offset_sec
        if event.start_sec < 0:
            raise ValueError("event offset makes an event start negative")


def require_root(dry_run: bool) -> None:
    if not dry_run and os.geteuid() != 0:
        raise PermissionError("tc replay requires root privileges; use --dry-run for validation")


def run(command: list[str], *, dry_run: bool = False, check: bool = True) -> None:
    print("$ " + shlex.join(command))
    if not dry_run:
        subprocess.run(command, check=check)


def tc_reset(interface: str, *, dry_run: bool = False) -> None:
    run(["tc", "qdisc", "del", "dev", interface, "root"], dry_run=dry_run, check=False)


def tc_show(interface: str, *, dry_run: bool = False) -> None:
    run(["tc", "qdisc", "show", "dev", interface], dry_run=dry_run, check=False)


def apply_tc(
    interface: str,
    *,
    rate_mbps: float,
    delay_ms: float,
    jitter_ms: float,
    loss_pct: float,
    burst_kbit: int,
    tbf_latency_ms: int,
    dry_run: bool = False,
) -> None:
    run(
        [
            "tc", "qdisc", "replace", "dev", interface, "root", "handle", "1:", "tbf",
            "rate", f"{max(rate_mbps, 0.1):.6f}mbit", "burst", f"{burst_kbit}kbit",
            "latency", f"{tbf_latency_ms}ms",
        ],
        dry_run=dry_run,
    )
    run(
        [
            "tc", "qdisc", "replace", "dev", interface, "parent", "1:1", "handle", "10:",
            "netem", "delay", f"{max(delay_ms, 0.1):.6f}ms", f"{max(jitter_ms, 0.0):.6f}ms",
            "loss", f"{clamp(loss_pct, 0.0, 99.0):.6f}%",
        ],
        dry_run=dry_run,
    )


def event_to_tc_params(
    event: EventSegment,
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
    rate = event.replay_rate_mbps if event.replay_rate_mbps > 0 else default_rate_mbps
    base_delay = default_delay_ms
    if event.replay_delay_ms > 0:
        base_delay = event.replay_delay_ms
    elif event.calibrated_delay_ms > 0:
        base_delay = max(default_delay_ms, event.calibrated_delay_ms)

    jitter = default_jitter_ms
    if event.replay_jitter_ms > 0:
        jitter = event.replay_jitter_ms
    elif event.calibrated_jitter_ms > 0:
        jitter = event.calibrated_jitter_ms

    loss = event.replay_loss_pct if event.replay_loss_pct > 0 else default_loss_pct
    spike = event.replay_spike_ms if event.replay_spike_ms > 0 else default_spike_ms
    if event.calibrated_spike_ms > 0 and event.replay_spike_ms <= 0:
        spike = event.calibrated_spike_ms
    spike = clamp(spike, 0.0, max_effective_spike_ms)

    if event.event == "handover_suspected":
        jitter = max(jitter, 2.0)
        loss = max(loss, handover_loss_pct)
    elif event.event == "outage_suspected":
        jitter = max(jitter, 3.0)
        loss = max(loss, outage_loss_pct)
    elif event.event == "obstruction_suspected":
        jitter = max(jitter, 2.0)
        loss = max(loss, obstruction_loss_pct)
    elif event.event == "collapse_suspected":
        jitter = max(jitter, 2.0)
        loss = max(loss, max(10.0, event.max_loss_pct))
    elif event.event == "degradation_suspected":
        jitter = max(jitter, 1.0)

    return rate, base_delay + spike, jitter, loss, base_delay, spike


def wait_until(start_wall: float, planned_profile_sec: float, time_scale: float, dry_run: bool) -> float:
    if dry_run:
        return planned_profile_sec / time_scale
    target_wall = start_wall + planned_profile_sec / time_scale
    while True:
        remaining = target_wall - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 0.005))
    return time.monotonic() - start_wall


def write_log(handle: TextIO | None, record: dict[str, Any]) -> None:
    if handle is None:
        return
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()


def replay_events(
    events: list[EventSegment],
    interface: str,
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
    execution_log: Path | None,
) -> None:
    if not events:
        raise ValueError("no events found")
    if time_scale <= 0:
        raise ValueError("time scale must be > 0")

    log_handle: TextIO | None = None
    if execution_log:
        execution_log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = execution_log.open("a", encoding="utf-8")

    try:
        while True:
            if start_delay_sec > 0 and not dry_run:
                time.sleep(start_delay_sec)
            start_wall = time.monotonic()
            last_end = 0.0
            previous_event_id: str | None = None

            apply_tc(
                interface,
                rate_mbps=default_rate_mbps,
                delay_ms=default_delay_ms,
                jitter_ms=default_jitter_ms,
                loss_pct=default_loss_pct,
                burst_kbit=burst_kbit,
                tbf_latency_ms=tbf_latency_ms,
                dry_run=dry_run,
            )
            write_log(log_handle, {"action": "baseline", "planned_sec": 0.0, "applied_sec": 0.0})

            for event in events:
                if (
                    restore_default_between_events
                    and previous_event_id is not None
                    and event.start_sec > last_end
                ):
                    applied = wait_until(start_wall, last_end, time_scale, dry_run)
                    apply_tc(
                        interface,
                        rate_mbps=default_rate_mbps,
                        delay_ms=default_delay_ms,
                        jitter_ms=default_jitter_ms,
                        loss_pct=default_loss_pct,
                        burst_kbit=burst_kbit,
                        tbf_latency_ms=tbf_latency_ms,
                        dry_run=dry_run,
                    )
                    write_log(
                        log_handle,
                        {
                            "action": "event_end",
                            "event_id": previous_event_id,
                            "planned_sec": last_end,
                            "applied_sec": round(applied * time_scale, 6),
                            "lateness_ms": round((applied * time_scale - last_end) * 1000.0, 6),
                        },
                    )

                applied = wait_until(start_wall, event.start_sec, time_scale, dry_run)
                rate, delay, jitter, loss, base_delay, spike = event_to_tc_params(
                    event,
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
                    f"[event] {event.event_id} {event.event} "
                    f"t={event.start_sec:.3f}-{event.end_sec:.3f}s dur={event.duration_sec:.3f}s "
                    f"rate={rate:.3f}Mbps delay={delay:.3f}ms "
                    f"(base={base_delay:.3f}+spike={spike:.3f}) jitter={jitter:.3f}ms loss={loss:.3f}%"
                )
                apply_tc(
                    interface,
                    rate_mbps=rate,
                    delay_ms=delay,
                    jitter_ms=jitter,
                    loss_pct=loss,
                    burst_kbit=burst_kbit,
                    tbf_latency_ms=tbf_latency_ms,
                    dry_run=dry_run,
                )
                write_log(
                    log_handle,
                    {
                        "action": "event_start",
                        "event_id": event.event_id,
                        "event_type": event.event,
                        "planned_sec": event.start_sec,
                        "applied_sec": round(applied * time_scale, 6),
                        "lateness_ms": round((applied * time_scale - event.start_sec) * 1000.0, 6),
                        "parameters": {
                            "rate_mbps": rate,
                            "delay_ms": delay,
                            "jitter_ms": jitter,
                            "loss_pct": loss,
                        },
                    },
                )
                last_end = event.end_sec
                previous_event_id = event.event_id

            applied = wait_until(start_wall, last_end, time_scale, dry_run)
            apply_tc(
                interface,
                rate_mbps=default_rate_mbps,
                delay_ms=default_delay_ms,
                jitter_ms=default_jitter_ms,
                loss_pct=default_loss_pct,
                burst_kbit=burst_kbit,
                tbf_latency_ms=tbf_latency_ms,
                dry_run=dry_run,
            )
            write_log(
                log_handle,
                {
                    "action": "final_baseline",
                    "planned_sec": last_end,
                    "applied_sec": round(applied * time_scale, 6),
                    "lateness_ms": round((applied * time_scale - last_end) * 1000.0, 6),
                },
            )
            if not loop:
                break
    finally:
        if log_handle:
            log_handle.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay LEO event profile using tc/TBF/netem")
    parser.add_argument("--events-json", required=True, type=Path)
    parser.add_argument("--iface", required=True)
    parser.add_argument("--default-rate-mbps", type=float, default=260.0)
    parser.add_argument("--default-delay-ms", type=float, default=15.0)
    parser.add_argument("--default-loss-pct", type=float, default=0.0)
    parser.add_argument("--default-jitter-ms", type=float, default=1.0)
    parser.add_argument("--default-spike-ms", type=float, default=0.0)
    parser.add_argument("--max-effective-spike-ms", type=float, default=200.0)
    parser.add_argument("--burst-kbit", type=int, default=32)
    parser.add_argument("--tbf-latency-ms", type=int, default=400)
    parser.add_argument("--handover-loss-pct", type=float, default=5.0)
    parser.add_argument("--outage-loss-pct", type=float, default=99.0)
    parser.add_argument("--obstruction-loss-pct", type=float, default=10.0)
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--start-delay-sec", type=float, default=0.0)
    parser.add_argument("--event-offset-sec", type=float, default=0.0)
    parser.add_argument("--execution-log", type=Path)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--restore-default-between-events", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset-only", action="store_true")
    parser.add_argument("--show-only", action="store_true")
    args = parser.parse_args()

    try:
        require_root(args.dry_run)
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
            execution_log=args.execution_log,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
