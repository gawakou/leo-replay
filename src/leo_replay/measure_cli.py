from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .measurement import (
    create_measurement_manifest,
    parse_ping_output,
    parse_traceroute_output,
    run_command,
    verify_measurement_snapshot,
    write_ping_csv,
    write_traceroute_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leo-replay-measure",
        description="Capture reproducible active network measurements for LEO-Replay",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ping = sub.add_parser("ping", help="Capture ICMP RTT samples")
    ping.add_argument("--target", required=True)
    ping.add_argument("--count", type=int, default=20)
    ping.add_argument("--interval-sec", type=float, default=0.2)
    ping.add_argument("--output-dir", required=True, type=Path)
    ping.add_argument("--timeout-sec", type=float, default=60.0)

    traceroute = sub.add_parser("traceroute", help="Capture traceroute path snapshots")
    traceroute.add_argument("--target", required=True)
    traceroute.add_argument("--max-hops", type=int, default=30)
    traceroute.add_argument("--wait-sec", type=float, default=2.0)
    traceroute.add_argument("--output-dir", required=True, type=Path)
    traceroute.add_argument("--timeout-sec", type=float, default=60.0)

    verify = sub.add_parser("verify", help="Verify an active-measurement snapshot")
    verify.add_argument("--input-dir", required=True, type=Path)
    return parser


def _ensure_empty_output_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"output directory is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise FileNotFoundError(f"required command not found: {name}")
    return path


def capture_ping(args: argparse.Namespace) -> int:
    if args.count <= 0:
        raise ValueError("--count must be > 0")
    if args.interval_sec <= 0:
        raise ValueError("--interval-sec must be > 0")
    _ensure_empty_output_dir(args.output_dir)
    command = [
        _require_tool("ping"),
        "-c",
        str(args.count),
        "-i",
        str(args.interval_sec),
        args.target,
    ]
    result = run_command(command, timeout_sec=args.timeout_sec)
    raw_path = args.output_dir / "ping.txt"
    raw_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    samples = parse_ping_output(result.stdout + result.stderr)
    csv_path = args.output_dir / "ping.csv"
    write_ping_csv(csv_path, samples)
    manifest = create_measurement_manifest(
        args.output_dir,
        kind="ping",
        target=args.target,
        command_result=result,
        data_files=[raw_path, csv_path],
    )
    print(json.dumps({
        "status": "pass" if result.returncode == 0 else "command-failed",
        "samples": len(samples),
        "output_dir": str(args.output_dir),
        "manifest": manifest,
    }, ensure_ascii=False, indent=2))
    return 0 if result.returncode == 0 else result.returncode


def capture_traceroute(args: argparse.Namespace) -> int:
    if args.max_hops <= 0:
        raise ValueError("--max-hops must be > 0")
    if args.wait_sec <= 0:
        raise ValueError("--wait-sec must be > 0")
    _ensure_empty_output_dir(args.output_dir)
    command = [
        _require_tool("traceroute"),
        "-m",
        str(args.max_hops),
        "-w",
        str(args.wait_sec),
        args.target,
    ]
    result = run_command(command, timeout_sec=args.timeout_sec)
    raw_path = args.output_dir / "traceroute.txt"
    raw_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    hops = parse_traceroute_output(result.stdout + result.stderr)
    json_path = args.output_dir / "traceroute.json"
    write_traceroute_json(json_path, hops)
    manifest = create_measurement_manifest(
        args.output_dir,
        kind="traceroute",
        target=args.target,
        command_result=result,
        data_files=[raw_path, json_path],
    )
    print(json.dumps({
        "status": "pass" if result.returncode == 0 else "command-failed",
        "hops": len(hops),
        "output_dir": str(args.output_dir),
        "manifest": manifest,
    }, ensure_ascii=False, indent=2))
    return 0 if result.returncode == 0 else result.returncode


def verify_snapshot(args: argparse.Namespace) -> int:
    errors = verify_measurement_snapshot(args.input_dir)
    if errors:
        print(json.dumps({"status": "fail", "errors": errors}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"status": "pass", "input_dir": str(args.input_dir)}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "ping":
            return capture_ping(args)
        if args.command == "traceroute":
            return capture_traceroute(args)
        if args.command == "verify":
            return verify_snapshot(args)
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
