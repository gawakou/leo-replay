from __future__ import annotations

import argparse
import copy
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .bidirectional_replay import (
    DirectionTargets,
    cleanup_targets,
    install_signal_handlers,
    prepare_targets,
    replay_events,
    replay_timeseries,
)
from .directional_profile import (
    ConversionPolicy,
    DirectionalProfileError,
    directionalize_event_document,
    read_directional_csv,
    write_conversion_metadata,
    write_directional_csv,
)
from .event_metrics import evaluate_events
from .event_profile import (
    EventProfileError,
    create_document,
    legacy_rows,
    load_document,
    save_document,
    validate_document,
)
from .tc_backend import CommandRunner, TcBackendError, require_linux_root


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


def add_conversion_policy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--legacy-delay-policy",
        choices=["split", "mirror", "forward-only"],
        default="split",
        help="How a legacy delay value is assigned to the two directions",
    )
    parser.add_argument(
        "--delay-forward-share",
        type=float,
        default=0.5,
        help="Forward share used by split/equivalent policies",
    )
    parser.add_argument(
        "--legacy-jitter-policy",
        choices=["split", "mirror", "forward-only"],
        default="split",
    )
    parser.add_argument(
        "--legacy-loss-policy",
        choices=["equivalent", "mirror", "forward-only"],
        default="equivalent",
        help="equivalent preserves the original end-to-end loss probability",
    )
    parser.add_argument(
        "--legacy-rate-policy",
        choices=["forward-only", "mirror"],
        default="forward-only",
    )
    parser.add_argument(
        "--reverse-default-rate-mbps",
        type=float,
        default=260.0,
        help="Reverse rate used when legacy throughput represents only forward traffic",
    )


def conversion_policy(args: argparse.Namespace) -> ConversionPolicy:
    policy = ConversionPolicy(
        delay_policy=args.legacy_delay_policy,
        delay_forward_share=args.delay_forward_share,
        jitter_policy=args.legacy_jitter_policy,
        loss_policy=args.legacy_loss_policy,
        rate_policy=args.legacy_rate_policy,
        reverse_default_rate_mbit=args.reverse_default_rate_mbps,
    )
    policy.validate()
    return policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leo-replay", description="LEO communication replay toolkit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    profile = sub.add_parser("profile", help="Generate and transform replay profiles")
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

    directionalize = profile_sub.add_parser(
        "directionalize",
        help="Convert a legacy profile into explicit forward/reverse conditions",
    )
    directionalize.add_argument("--mode", choices=["timeseries", "event"], required=True)
    directionalize.add_argument("--input", required=True, type=Path)
    directionalize.add_argument("--output", required=True, type=Path)
    directionalize.add_argument("--metadata-output", type=Path)
    directionalize.add_argument("--default-rate-mbps", type=float, default=260.0)
    add_conversion_policy_arguments(directionalize)

    replay = sub.add_parser("replay", help="Replay a time-series or event profile")
    replay.add_argument("--mode", choices=["timeseries", "event"], required=True)
    replay.add_argument("--input", required=True, type=Path)
    replay.add_argument(
        "--direction-mode",
        choices=["single", "dual-egress", "ifb"],
        default="single",
        help="single preserves v0.2 behavior; dual-egress and ifb independently shape both directions",
    )
    replay.add_argument("--dev", help="Legacy single-direction target device")
    replay.add_argument("--forward-dev", help="Forward egress device or physical device in IFB mode")
    replay.add_argument("--reverse-dev", help="Reverse egress device in dual-egress mode")
    replay.add_argument("--ifb-dev", default="ifb0", help="IFB device used for redirected ingress")
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
    replay.add_argument("--preserve-existing", action="store_true")
    replay.add_argument("--setup-only", action="store_true")
    replay.add_argument("--cleanup-on-exit", action="store_true")
    replay.add_argument("--delete-ifb-device", action="store_true")
    add_conversion_policy_arguments(replay)

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


def directionalize_profile(args: argparse.Namespace) -> int:
    policy = conversion_policy(args)
    metadata_output = args.metadata_output or Path(str(args.output) + ".meta.json")
    if args.mode == "timeseries":
        states = read_directional_csv(
            args.input,
            policy=policy,
            default_rate_mbit=args.default_rate_mbps,
        )
        write_directional_csv(args.output, states)
        write_conversion_metadata(
            metadata_output,
            input_path=args.input,
            output_path=args.output,
            mode=args.mode,
            policy=policy,
            states=len(states),
        )
        print(json.dumps({"states": len(states), "output": str(args.output)}, indent=2))
        return 0

    document = load_document(args.input)
    baseline = document.setdefault("baseline", {})
    if not baseline.get("rate_mbit"):
        baseline["rate_mbit"] = args.default_rate_mbps
    updated = directionalize_event_document(document, policy=policy)
    save_document(args.output, updated)
    write_conversion_metadata(
        metadata_output,
        input_path=args.input,
        output_path=args.output,
        mode=args.mode,
        policy=policy,
        events=len(updated.get("events", [])),
    )
    print(json.dumps({"events": len(updated.get("events", [])), "output": str(args.output)}, indent=2))
    return 0


def _single_direction_replay(args: argparse.Namespace) -> int:
    if not args.dev:
        raise ValueError("--dev is required when --direction-mode=single")
    if args.mode == "timeseries":
        command = ["--dev", args.dev, "--csv", str(args.input)]
        if args.dry_run:
            command.append("--dry-run")
        if args.verbose:
            command.append("--verbose")
        if args.setup_only:
            command.append("--setup-only")
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


def _direction_targets(args: argparse.Namespace) -> DirectionTargets:
    if args.direction_mode == "dual-egress":
        return DirectionTargets.dual_egress(args.forward_dev or "", args.reverse_dev or "")
    if args.direction_mode == "ifb":
        return DirectionTargets.ifb(args.forward_dev or "", args.ifb_dev)
    raise ValueError(f"unsupported bidirectional mode: {args.direction_mode}")


def _event_document_with_defaults(args: argparse.Namespace) -> dict[str, Any]:
    document = copy.deepcopy(load_document(args.input))
    baseline = document.setdefault("baseline", {})
    if not baseline.get("rate_mbit"):
        baseline["rate_mbit"] = args.default_rate_mbps
    if not baseline.get("delay_ms"):
        baseline["delay_ms"] = args.default_delay_ms
    if not baseline.get("jitter_ms"):
        baseline["jitter_ms"] = args.default_jitter_ms
    if baseline.get("loss_pct") is None:
        baseline["loss_pct"] = args.default_loss_pct
    directions = baseline.get("directions")
    if isinstance(directions, dict):
        forward = directions.get("forward")
        reverse = directions.get("reverse")
        if isinstance(forward, dict) and not forward.get("rate_mbit"):
            forward["rate_mbit"] = args.default_rate_mbps
        if isinstance(reverse, dict) and not reverse.get("rate_mbit"):
            reverse["rate_mbit"] = args.reverse_default_rate_mbps
    return document


def _bidirectional_replay(args: argparse.Namespace) -> int:
    require_linux_root(dry_run=args.dry_run)
    targets = _direction_targets(args)
    policy = conversion_policy(args)
    runner = CommandRunner(dry_run=args.dry_run, verbose=args.verbose)
    install_signal_handlers()
    prepare_targets(runner, targets, preserve_existing=args.preserve_existing)
    try:
        if args.mode == "timeseries":
            states = read_directional_csv(
                args.input,
                policy=policy,
                default_rate_mbit=args.default_rate_mbps,
            )
            replay_timeseries(
                states,
                targets=targets,
                runner=runner,
                time_scale=args.time_scale,
                setup_only=args.setup_only,
                execution_log=args.execution_log,
            )
        else:
            replay_events(
                _event_document_with_defaults(args),
                targets=targets,
                runner=runner,
                policy=policy,
                time_scale=args.time_scale,
                event_offset_sec=args.event_offset_sec,
                restore_default_between_events=args.restore_default_between_events,
                execution_log=args.execution_log,
            )
    finally:
        if args.cleanup_on_exit:
            cleanup_targets(
                runner,
                targets,
                delete_ifb_device=args.delete_ifb_device,
            )
    return 0


def replay_profile(args: argparse.Namespace) -> int:
    if args.time_scale <= 0:
        raise ValueError("--time-scale must be > 0")
    if args.direction_mode == "single":
        return _single_direction_replay(args)
    return _bidirectional_replay(args)


def validate_profile(args: argparse.Namespace) -> int:
    document = load_document(args.input, validate=False)
    errors = validate_document(document)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    directional = any(isinstance(event.get("directions"), dict) for event in document["events"])
    suffix = ", directional" if directional else ""
    print(f"Valid event profile: {args.input} ({len(document['events'])} events{suffix})")
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
        if args.command == "profile" and args.profile_command == "directionalize":
            return directionalize_profile(args)
        if args.command == "replay":
            return replay_profile(args)
        if args.command == "validate":
            return validate_profile(args)
        if args.command == "evaluate" and args.evaluate_command == "events":
            return evaluate_event_profiles(args)
    except (
        ValueError,
        FileNotFoundError,
        PermissionError,
        EventProfileError,
        DirectionalProfileError,
        TcBackendError,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    parser.error("unsupported command")
    return 2
