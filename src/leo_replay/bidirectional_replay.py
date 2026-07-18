from __future__ import annotations

import json
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from .directional_profile import (
    ConversionPolicy,
    DirectionalState,
    LinkCondition,
    event_direction_conditions,
)
from .tc_backend import (
    CommandRunner,
    build_netem_command,
    cleanup_ifb,
    clear_root_qdisc,
    setup_ifb,
)


@dataclass(frozen=True)
class DirectionTargets:
    mode: str
    forward_device: str
    reverse_device: str
    physical_device: str | None = None
    ifb_device: str | None = None

    @classmethod
    def dual_egress(cls, forward_device: str, reverse_device: str) -> "DirectionTargets":
        if not forward_device or not reverse_device:
            raise ValueError("dual-egress mode requires forward and reverse devices")
        if forward_device == reverse_device:
            raise ValueError("forward and reverse devices must be different in dual-egress mode")
        return cls("dual-egress", forward_device, reverse_device)

    @classmethod
    def ifb(cls, physical_device: str, ifb_device: str) -> "DirectionTargets":
        if not physical_device or not ifb_device:
            raise ValueError("ifb mode requires a physical device and an IFB device")
        if physical_device == ifb_device:
            raise ValueError("physical and IFB devices must be different")
        return cls(
            "ifb",
            forward_device=physical_device,
            reverse_device=ifb_device,
            physical_device=physical_device,
            ifb_device=ifb_device,
        )


_stop_requested = False


def install_signal_handlers() -> None:
    def handle_signal(signum: int, _frame: Any) -> None:
        global _stop_requested
        _stop_requested = True
        print(f"\n[INFO] Caught signal {signum}; stopping replay.")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


def _wait_until(start_wall: float, planned_sec: float, time_scale: float, dry_run: bool) -> float:
    if dry_run:
        return planned_sec
    target = start_wall + planned_sec / time_scale
    while True:
        remaining = target - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 0.005))
    return (time.monotonic() - start_wall) * time_scale


def _open_log(path: Path | None) -> TextIO | None:
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8")


def _write_log(handle: TextIO | None, record: dict[str, Any]) -> None:
    if handle is None:
        return
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()


def prepare_targets(
    runner: CommandRunner,
    targets: DirectionTargets,
    *,
    preserve_existing: bool,
) -> None:
    if targets.mode == "ifb":
        assert targets.physical_device and targets.ifb_device
        setup_ifb(
            runner,
            physical_device=targets.physical_device,
            ifb_device=targets.ifb_device,
        )
    if not preserve_existing:
        clear_root_qdisc(runner, targets.forward_device)
        clear_root_qdisc(runner, targets.reverse_device)


def cleanup_targets(
    runner: CommandRunner,
    targets: DirectionTargets,
    *,
    delete_ifb_device: bool,
) -> None:
    clear_root_qdisc(runner, targets.forward_device)
    if targets.mode == "ifb":
        assert targets.physical_device and targets.ifb_device
        cleanup_ifb(
            runner,
            physical_device=targets.physical_device,
            ifb_device=targets.ifb_device,
            delete_device=delete_ifb_device,
        )
    else:
        clear_root_qdisc(runner, targets.reverse_device)


def _apply_direction_pair(
    runner: CommandRunner,
    targets: DirectionTargets,
    *,
    forward: LinkCondition,
    reverse: LinkCondition,
    planned_sec: float,
    start_wall: float,
    time_scale: float,
    action: str,
    event_id: str | None,
    log_handle: TextIO | None,
) -> None:
    for direction, device, condition in (
        ("forward", targets.forward_device, forward),
        ("reverse", targets.reverse_device, reverse),
    ):
        runner.run(build_netem_command(device, condition))
        if runner.dry_run:
            applied_sec = planned_sec
        else:
            applied_sec = (time.monotonic() - start_wall) * time_scale
        _write_log(
            log_handle,
            {
                "action": action,
                "event_id": event_id,
                "direction": direction,
                "device": device,
                "planned_sec": round(planned_sec, 6),
                "applied_sec": round(applied_sec, 6),
                "lateness_ms": round((applied_sec - planned_sec) * 1000.0, 6),
                "parameters": condition.to_mapping(),
            },
        )


def replay_timeseries(
    states: list[DirectionalState],
    *,
    targets: DirectionTargets,
    runner: CommandRunner,
    time_scale: float = 1.0,
    setup_only: bool = False,
    execution_log: Path | None = None,
) -> None:
    if not states:
        raise ValueError("no time-series states found")
    if time_scale <= 0:
        raise ValueError("time_scale must be > 0")
    log_handle = _open_log(execution_log)
    start_wall = time.monotonic()
    try:
        for state in states:
            if _stop_requested:
                break
            _wait_until(start_wall, state.sec, time_scale, runner.dry_run)
            print(
                f"[APPLY] t={state.sec:.3f}s note={state.note!r} "
                f"forward(delay={state.forward.delay_ms:.3f}ms, loss={state.forward.loss_pct:.3f}%, "
                f"rate={state.forward.rate_mbit}) "
                f"reverse(delay={state.reverse.delay_ms:.3f}ms, loss={state.reverse.loss_pct:.3f}%, "
                f"rate={state.reverse.rate_mbit})"
            )
            _apply_direction_pair(
                runner,
                targets,
                forward=state.forward,
                reverse=state.reverse,
                planned_sec=state.sec,
                start_wall=start_wall,
                time_scale=time_scale,
                action="timeseries_state",
                event_id=None,
                log_handle=log_handle,
            )
            if setup_only:
                break
    finally:
        if log_handle:
            log_handle.close()


def _event_effect(
    condition: LinkCondition, event_type: str, *, loss_floor_pct: float = 0.0
) -> LinkCondition:
    jitter = condition.jitter_ms
    loss = max(condition.loss_pct, loss_floor_pct)
    if event_type == "handover_suspected":
        jitter = max(jitter, 2.0)
    elif event_type == "outage_suspected":
        jitter = max(jitter, 3.0)
    elif event_type == "obstruction_suspected":
        jitter = max(jitter, 2.0)
    elif event_type == "collapse_suspected":
        jitter = max(jitter, 2.0)
    elif event_type == "degradation_suspected":
        jitter = max(jitter, 1.0)
    return LinkCondition(
        delay_ms=condition.delay_ms,
        jitter_ms=jitter,
        loss_pct=loss,
        rate_mbit=condition.rate_mbit,
        reorder_pct=condition.reorder_pct,
        correlation_pct=condition.correlation_pct,
    )


def _event_path_loss_floor(event_type: str) -> float:
    return {
        "handover_suspected": 5.0,
        "outage_suspected": 99.0,
        "obstruction_suspected": 10.0,
        "collapse_suspected": 10.0,
    }.get(event_type, 0.0)


def replay_events(
    document: dict[str, Any],
    *,
    targets: DirectionTargets,
    runner: CommandRunner,
    policy: ConversionPolicy,
    time_scale: float = 1.0,
    event_offset_sec: float = 0.0,
    restore_default_between_events: bool = False,
    execution_log: Path | None = None,
) -> None:
    if time_scale <= 0:
        raise ValueError("time_scale must be > 0")
    events = document.get("events") or []
    if not events:
        raise ValueError("no events found")
    baseline_forward, baseline_reverse = event_direction_conditions(
        document.get("baseline") or {}, policy=policy
    )
    log_handle = _open_log(execution_log)
    start_wall = time.monotonic()
    previous_end = 0.0
    previous_event_id: str | None = None
    try:
        _apply_direction_pair(
            runner,
            targets,
            forward=baseline_forward,
            reverse=baseline_reverse,
            planned_sec=0.0,
            start_wall=start_wall,
            time_scale=time_scale,
            action="baseline",
            event_id=None,
            log_handle=log_handle,
        )
        for event in events:
            if _stop_requested:
                break
            start_sec = float(event["start_sec"]) + event_offset_sec
            end_sec = float(event["end_sec"]) + event_offset_sec
            if start_sec < 0:
                raise ValueError("event_offset_sec makes an event start negative")
            if restore_default_between_events and previous_event_id and start_sec > previous_end:
                _wait_until(start_wall, previous_end, time_scale, runner.dry_run)
                _apply_direction_pair(
                    runner,
                    targets,
                    forward=baseline_forward,
                    reverse=baseline_reverse,
                    planned_sec=previous_end,
                    start_wall=start_wall,
                    time_scale=time_scale,
                    action="event_end",
                    event_id=previous_event_id,
                    log_handle=log_handle,
                )
            forward, reverse = event_direction_conditions(event, policy=policy)
            event_type = str(event.get("event_type", "custom"))
            path_floor = _event_path_loss_floor(event_type)
            if path_floor > 0:
                floor_forward, floor_reverse = event_direction_conditions(
                    {
                        "rate_mbit": 0.0,
                        "delay_ms": 0.0,
                        "jitter_ms": 0.0,
                        "loss_pct": path_floor,
                    },
                    policy=policy,
                )
            else:
                floor_forward = LinkCondition()
                floor_reverse = LinkCondition()
            forward = _event_effect(
                forward, event_type, loss_floor_pct=floor_forward.loss_pct
            )
            reverse = _event_effect(
                reverse, event_type, loss_floor_pct=floor_reverse.loss_pct
            )
            _wait_until(start_wall, start_sec, time_scale, runner.dry_run)
            print(
                f"[EVENT] {event.get('event_id')} {event_type} "
                f"t={start_sec:.3f}-{end_sec:.3f}s"
            )
            _apply_direction_pair(
                runner,
                targets,
                forward=forward,
                reverse=reverse,
                planned_sec=start_sec,
                start_wall=start_wall,
                time_scale=time_scale,
                action="event_start",
                event_id=str(event.get("event_id", "")),
                log_handle=log_handle,
            )
            previous_end = max(previous_end, end_sec)
            previous_event_id = str(event.get("event_id", ""))

        _wait_until(start_wall, previous_end, time_scale, runner.dry_run)
        _apply_direction_pair(
            runner,
            targets,
            forward=baseline_forward,
            reverse=baseline_reverse,
            planned_sec=previous_end,
            start_wall=start_wall,
            time_scale=time_scale,
            action="final_baseline",
            event_id=previous_event_id,
            log_handle=log_handle,
        )
    finally:
        if log_handle:
            log_handle.close()
