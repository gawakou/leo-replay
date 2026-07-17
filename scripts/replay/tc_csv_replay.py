#!/usr/bin/env python3
"""
CSV-driven tc/netem replay script for LEO/Starlink-like network fluctuation emulation.

Overview:
- Reads a time-series CSV profile.
- Applies delay / jitter / loss / rate / reorder to a specified egress interface.
- Updates qdisc parameters over time using `tc qdisc replace`.
- Intended for a Linux router/emulator placed between two NICs.

Recommended topology:
    Client -- [eth_in | Linux Router | eth_out] -- Server

Typical use:
    sudo python3 tc_csv_replay.py \
        --dev eth1 \
        --csv profile.csv \
        --base-time relative \
        --dry-run

Then remove --dry-run to apply.

CSV format example:
sec,delay_ms,jitter_ms,loss_pct,rate_mbit,reorder_pct,correlation_pct,note
0,40,5,0.0,100,0.0,20,normal
5,55,8,0.2,80,0.0,20,slightly_degraded
10,120,20,2.0,20,0.5,10,handover_start
12,250,30,10.0,5,2.0,0,handover_peak
15,80,10,1.0,50,0.0,20,recovery
20,40,5,0.0,100,0.0,20,stable

Notes:
- `sec` is required and represents the elapsed time from replay start when base-time=relative.
- Missing optional fields fall back to defaults.
- This script uses a simple root netem. For stronger bandwidth shaping fidelity,
  you can extend it to HTB/TBF + netem, but this version keeps updates robust.
"""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TcState:
    sec: float
    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    loss_pct: float = 0.0
    rate_mbit: Optional[float] = None
    reorder_pct: float = 0.0
    correlation_pct: float = 0.0
    note: str = ""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay CSV network profile via tc/netem")
    p.add_argument("--dev", required=True, help="Target egress interface, e.g. eth1")
    p.add_argument("--csv", required=True, help="CSV profile path")
    p.add_argument(
        "--base-time",
        choices=["relative"],
        default="relative",
        help="Interpretation of sec column. Currently only relative is supported.",
    )
    p.add_argument(
        "--default-rate-mbit",
        type=float,
        default=None,
        help="Fallback rate if rate_mbit is missing in a row",
    )
    p.add_argument(
        "--preserve-existing",
        action="store_true",
        help="Do not clear existing qdisc before starting; replace root instead.",
    )
    p.add_argument(
        "--setup-only",
        action="store_true",
        help="Apply only the first row and exit",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print tc commands without executing them",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed replay logs",
    )
    return p.parse_args()


def require_root(dry_run: bool) -> None:
    if dry_run:
        return
    if os.geteuid() != 0:
        print("[ERROR] This script must be run as root (or use --dry-run).", file=sys.stderr)
        sys.exit(1)


def read_csv_profile(path: str, default_rate_mbit: Optional[float]) -> List[TcState]:
    rows: List[TcState] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"sec"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

        for i, row in enumerate(reader, start=2):
            try:
                sec = float(row.get("sec", "0") or 0)
                delay_ms = float(row.get("delay_ms", "0") or 0)
                jitter_ms = float(row.get("jitter_ms", "0") or 0)
                loss_pct = float(row.get("loss_pct", "0") or 0)
                reorder_pct = float(row.get("reorder_pct", "0") or 0)
                correlation_pct = float(row.get("correlation_pct", "0") or 0)
                note = (row.get("note", "") or "").strip()

                rate_raw = (row.get("rate_mbit", "") or "").strip()
                rate_mbit = float(rate_raw) if rate_raw else default_rate_mbit
            except ValueError as e:
                raise ValueError(f"Invalid numeric value at CSV line {i}: {e}") from e

            rows.append(
                TcState(
                    sec=sec,
                    delay_ms=delay_ms,
                    jitter_ms=jitter_ms,
                    loss_pct=loss_pct,
                    rate_mbit=rate_mbit,
                    reorder_pct=reorder_pct,
                    correlation_pct=correlation_pct,
                    note=note,
                )
            )

    if not rows:
        raise ValueError("CSV profile is empty")

    rows.sort(key=lambda x: x.sec)
    return rows


def run_cmd(cmd: List[str], dry_run: bool, verbose: bool) -> None:
    rendered = shlex.join(cmd)
    print(f"$ {rendered}")
    if dry_run:
        return
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        if verbose and proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"Command failed: {rendered}")
    if verbose and proc.stdout:
        print(proc.stdout, end="")


def clear_qdisc(dev: str, dry_run: bool, verbose: bool) -> None:
    cmd = ["tc", "qdisc", "del", "dev", dev, "root"]
    if dry_run:
        print(f"$ {shlex.join(cmd)}")
        return
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 and "No such file or directory" not in (proc.stderr or ""):
        if verbose and proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)


def build_netem_cmd(dev: str, state: TcState) -> List[str]:
    cmd = ["tc", "qdisc", "replace", "dev", dev, "root", "netem"]

    if state.delay_ms > 0 or state.jitter_ms > 0:
        cmd += ["delay", f"{state.delay_ms:.3f}ms"]
        if state.jitter_ms > 0:
            cmd += [f"{state.jitter_ms:.3f}ms"]
            if state.correlation_pct > 0:
                cmd += [f"{state.correlation_pct:.1f}%"]

    if state.loss_pct > 0:
        cmd += ["loss", f"{state.loss_pct:.3f}%"]
        if state.correlation_pct > 0:
            cmd += [f"{state.correlation_pct:.1f}%"]

    if state.rate_mbit is not None and state.rate_mbit > 0:
        cmd += ["rate", f"{state.rate_mbit:.3f}mbit"]

    if state.reorder_pct > 0:
        cmd += ["reorder", f"{state.reorder_pct:.3f}%"]
        if state.correlation_pct > 0:
            cmd += [f"{state.correlation_pct:.1f}%"]

    return cmd


stop_requested = False


def handle_signal(signum, frame) -> None:  # type: ignore[no-untyped-def]
    global stop_requested
    stop_requested = True
    print(f"\n[INFO] Caught signal {signum}; stopping replay.")


def sleep_until(target_monotonic: float) -> None:
    while True:
        now = time.monotonic()
        remaining = target_monotonic - now
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.05))


def replay(dev: str, states: List[TcState], dry_run: bool, verbose: bool, setup_only: bool) -> None:
    start = time.monotonic()

    for idx, state in enumerate(states):
        if stop_requested:
            break

        target = start + state.sec
        sleep_until(target)

        now_rel = time.monotonic() - start
        print(
            f"[APPLY] t={now_rel:7.3f}s sec={state.sec:7.3f} "
            f"delay={state.delay_ms:.1f}ms jitter={state.jitter_ms:.1f}ms "
            f"loss={state.loss_pct:.3f}% rate={state.rate_mbit if state.rate_mbit is not None else 'None'}mbit "
            f"reorder={state.reorder_pct:.3f}% note='{state.note}'"
        )

        cmd = build_netem_cmd(dev, state)
        run_cmd(cmd, dry_run=dry_run, verbose=verbose)

        if setup_only:
            print("[INFO] --setup-only specified; exiting after first state.")
            break

        if idx + 1 == len(states):
            print("[INFO] Reached final state; replay completed.")


def main() -> None:
    args = parse_args()
    require_root(args.dry_run)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        states = read_csv_profile(args.csv, args.default_rate_mbit)
    except Exception as e:
        print(f"[ERROR] Failed to read CSV: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Loaded {len(states)} states from {args.csv}")
    print(f"[INFO] Target device: {args.dev}")

    if not args.preserve_existing:
        clear_qdisc(args.dev, dry_run=args.dry_run, verbose=args.verbose)

    try:
        replay(
            dev=args.dev,
            states=states,
            dry_run=args.dry_run,
            verbose=args.verbose,
            setup_only=args.setup_only,
        )
    except Exception as e:
        print(f"[ERROR] Replay failed: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
