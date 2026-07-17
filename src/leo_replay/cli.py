from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .event_metrics import evaluate_events
from .event_profile import (
    EventProfileError,
    create_document,
    legacy_rows,
    load_document,
    save_document,
    validate_document,
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def script_path(relative: str) -> Path:
    path = repository_root() / relative
    if not path.exists():
        raise FileNotFoundError(f"Required repository script not found: {path}")
    return path


def run_script(relative: str, arguments: list[str]) -> int:
    command = [sys.executable, str(script_path(relative)), *arguments]
    print("$ " + " ".join(command))
    return subprocess.run(command, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leo-replay", description="LEO communication replay toolkit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    profile = sub.add_parser("profile", help="Generate replay profiles")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    generate = profile_sub.add_parser("generate", help="Generate a time-series or event profile")
    generate.add_argument("--mode", choices=["timeseries", "event"], required=True)
    generate.add_argument("--ping", required=True, type=Path)
    generate.add_argument("--iperf", required=True, type=Path)
    generate.add_argument("--grpc", required=True, type=Path)
    generate.add_argument("--output", required=True, type=Path)
    generate.add_argument("--detail-output", type=Path)
    generate.add_argument("--csv-output", type=Path)
    generate.add_argument("--bin-sec", type=float, default=0.5)
    generate.add_argument("--base-delay-ms", type=float, default=20.0)
    generate.add_argument("--target-rate-mbps", type=float)
    generate.add_argument("--min-event-duration-sec", type=float, default=0.05)
    generate.add_argument("--legacy-event-format", action="store_true")

    replay = sub.add_parser("replay", help="Replay a time-series or event profile")
    replay.add_argument("--mode", choices=["timeseries", "event"], required=True)
    replay.add_argument("--input", required=True, type=Path)
    replay.add_argument("--dev", required=True)
    replay.add_argument("--dry-run", action="store_true")
    replay.add_argument("--verbose", action="store_true")
    replay.add_argument("--time-scale", type=float, default=1.0)
    replay.add_argument("--event-offset-sec", type=float, default=0.0)
    replay.add_argument("--execution-log", type=Path)
    replay.add_argument("--restore-default-between-events", action="store_true")
    replay.add_argument("--default-rate-mbps", type=float, default=260.0)
    replay.add_argument("--default-delay-ms", type=float, default=15.0)
    replay.add_argument("--default-jitter-ms", type=float, default=1.0)
    replay.add_argument("--default-loss-pct", type=float, default=0.0)

    validate = sub.add_parser("validate", help="Validate an event profile")
    validate.add_argument("--input", required=True, type=Path)
    validate.add_argument("--normalized-output", type=Path)

    evaluate = sub.add_parser("evaluate", help="Evaluate event replay accuracy")
    evaluate_sub = evaluate.add_subparsers(dest="evaluate_command", required=True)
    events = evaluate_sub.add_parser("events", help="Compute event-window and timing metrics")
    events.add_argument("--measured-ping", required=True, type=Path)
    events.add_argument("--replayed-ping", required=True, type=Path)
    events.add_argument("--events", required=True, type=Path)
    events.add_argument("--output", required=True, type=Path)
    events.add_argument("--csv-output", type=Path)
    events.add_argument("--search-margin-sec", type=float, default=0.5)
    events.add_argument("--align-tolerance-sec", type=float, default=0.11)
    events.add_argument("--threshold-ms", type=float)

    return parser


def generate_profile(args: argparse.Namespace) -> int:
    if args.bin_sec <= 0:
        raise ValueError("--bin-sec must be > 0")
    if args.mode == "timeseries":
        command = [
            "--ping", str(args.ping),
            "--iperf", str(args.iperf),
            "--grpc", str(args.grpc),
            "--output", str(args.output),
            "--resample-sec", str(args.bin_sec),
        ]
        return run_script("scripts/profile/starlink_merge_realdata_to_profile.py", command)

    with tempfile.TemporaryDirectory(prefix="leo-replay-event-") as temp_dir:
        temp = Path(temp_dir)
        detail_json = args.detail_output or temp / "event-detail.json"
        legacy_events = temp / "events-legacy.json"
        command = [
            "--iperf-json", str(args.iperf),
            "--ping-csv", str(args.ping),
            "--grpc-csv", str(args.grpc),
            "--out-json", str(detail_json),
            "--out-events-json", str(legacy_events),
            "--bin-sec", str(args.bin_sec),
            "--base-delay-ms", str(args.base_delay_ms),
            "--min-event-duration-sec", str(args.min_event_duration_sec),
        ]
        if args.csv_output:
            command.extend(["--out-csv", str(args.csv_output)])
        if args.target_rate_mbps is not None:
            command.extend(["--target-rate-mbps", str(args.target_rate_mbps)])
        result = run_script("scripts/profile/iperf_ping_grpc_to_event_profile.py", command)
        if result != 0:
            return result
        rows = json.loads(legacy_events.read_text(encoding="utf-8"))
        if args.legacy_event_format:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return 0
        document = create_document(
            rows,
            baseline={
                "rate_mbit": args.target_rate_mbps or 0.0,
                "delay_ms": args.base_delay_ms,
                "jitter_ms": 1.0,
                "loss_pct": 0.0,
            },
            metadata={
                "generator": "leo-replay profile generate --mode event",
                "bin_sec": args.bin_sec,
                "source_files": {
                    "ping": str(args.ping),
                    "iperf": str(args.iperf),
                    "grpc": str(args.grpc),
                },
            },
        )
        save_document(args.output, document)
        print(json.dumps({"events": len(document["events"]), "output": str(args.output)}, indent=2))
        return 0


def replay_profile(args: argparse.Namespace) -> int:
    if args.time_scale <= 0:
        raise ValueError("--time-scale must be > 0")
    if args.mode == "timeseries":
        command = ["--dev", args.dev, "--csv", str(args.input)]
        if args.dry_run:
            command.append("--dry-run")
        if args.verbose:
            command.append("--verbose")
        return run_script("scripts/replay/tc_csv_replay.py", command)

    document = load_document(args.input)
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
        legacy_path = Path(handle.name)
        json.dump(legacy_rows(document), handle, ensure_ascii=False, indent=2)
    try:
        baseline = document.get("baseline") or {}
        command = [
            "--events-json", str(legacy_path),
            "--iface", args.dev,
            "--time-scale", str(args.time_scale),
            "--event-offset-sec", str(args.event_offset_sec),
            "--default-rate-mbps", str(baseline.get("rate_mbit") or args.default_rate_mbps),
            "--default-delay-ms", str(baseline.get("delay_ms") or args.default_delay_ms),
            "--default-jitter-ms", str(baseline.get("jitter_ms") or args.default_jitter_ms),
            "--default-loss-pct", str(baseline.get("loss_pct") or args.default_loss_pct),
        ]
        if args.execution_log:
            command.extend(["--execution-log", str(args.execution_log)])
        if args.restore_default_between_events:
            command.append("--restore-default-between-events")
        if args.dry_run:
            command.append("--dry-run")
        return run_script("scripts/replay/tc_event_replay_calibrated.py", command)
    finally:
        legacy_path.unlink(missing_ok=True)


def validate_profile(args: argparse.Namespace) -> int:
    document = load_document(args.input, validate=False)
    errors = validate_document(document)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"Valid event profile: {args.input} ({len(document['events'])} events)")
    if args.normalized_output:
        save_document(args.normalized_output, document)
        print(f"Normalized profile: {args.normalized_output}")
    return 0


def write_metrics_csv(path: Path, metrics: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "event_id", "event_type", "nominal_start_sec", "nominal_end_sec",
        "aligned_points", "rtt_mae_ms", "rtt_rmse_ms", "start_time_error_sec",
        "end_time_error_sec", "duration_error_sec", "peak_rtt_error_ms", "peak_time_error_sec",
        "event_mean_rtt_error_ms", "timeout_ratio_error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for event in metrics["events"]:
            writer.writerow({
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "nominal_start_sec": event["nominal_start_sec"],
                "nominal_end_sec": event["nominal_end_sec"],
                **event["errors"],
            })


def evaluate_event_profiles(args: argparse.Namespace) -> int:
    metrics = evaluate_events(
        args.measured_ping,
        args.replayed_ping,
        args.events,
        search_margin_sec=args.search_margin_sec,
        align_tolerance_sec=args.align_tolerance_sec,
        threshold_ms=args.threshold_ms,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.csv_output:
        write_metrics_csv(args.csv_output, metrics)
    print(json.dumps(metrics["aggregate"], ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "profile" and args.profile_command == "generate":
            return generate_profile(args)
        if args.command == "replay":
            return replay_profile(args)
        if args.command == "validate":
            return validate_profile(args)
        if args.command == "evaluate" and args.evaluate_command == "events":
            return evaluate_event_profiles(args)
    except (ValueError, FileNotFoundError, EventProfileError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    parser.error("unsupported command")
    return 2
