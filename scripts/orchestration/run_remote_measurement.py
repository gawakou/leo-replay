#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import time
from pathlib import Path


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("$ " + " ".join(shlex.quote(x) for x in cmd))
    return subprocess.run(cmd, check=check)


def shell_join(cmd: list[str]) -> str:
    return " ".join(shlex.quote(x) for x in cmd)


def build_remote_measurement_command(
    *,
    iperf_host: str,
    duration: float,
    protocol: str,
    udp_bitrate_mbps: float | None,
    iperf_interval: float,
    reverse: bool,
    ipv6: bool,
    port: int,
    iperf_json_path: str,
    ping_log_path: str,
    ping_interval: float,
    shell_log_path: str,
) -> str:
    iperf_parts: list[str] = [
        "iperf3",
        "-c", iperf_host,
        "-t", str(duration),
        "-i", str(iperf_interval),
        "-J",
        "-p", str(port),
    ]

    if ipv6:
        iperf_parts.append("-6")

    if reverse:
        iperf_parts.append("-R")

    if protocol.lower() == "udp":
        if udp_bitrate_mbps is None:
            raise ValueError("--udp-bitrate-mbps is required in UDP mode")
        iperf_parts += ["-u", "-b", f"{udp_bitrate_mbps}M"]

    iperf_cmd = shell_join(iperf_parts) + f" > {shlex.quote(iperf_json_path)}"

    ping_parts: list[str] = [
        "ping",
        "-i", str(ping_interval),
        "-n",
    ]
    if ipv6:
        ping_parts.append("-6")
    ping_parts.append(iperf_host)

    ping_cmd = shell_join(ping_parts) + f" > {shlex.quote(ping_log_path)}"
    wrapped_ping_cmd = f"timeout {duration + 5.0}s bash -lc {shlex.quote(ping_cmd)}"

    body_lines = [
        "set -e",
        f"{iperf_cmd} &",
        "IPERF_PID=$!",
        f"{wrapped_ping_cmd} &",
        "PING_PID=$!",
        'wait "$IPERF_PID"',
        'wait "$PING_PID" || true',
    ]
    body = "\n".join(body_lines)

    remote_cmd = (
        f"nohup bash -lc {shlex.quote(body)} "
        f"> {shlex.quote(shell_log_path)} 2>&1 < /dev/null &"
    )
    return remote_cmd


def add_common_ssh_args(cmd: list[str], *, port: int, identity_file: str | None, known_hosts: str | None) -> list[str]:
    out = cmd[:]
    out += ["-p", str(port)]
    if identity_file:
        out += ["-i", identity_file]
    if known_hosts:
        out += ["-o", f"UserKnownHostsFile={known_hosts}"]
    return out


def build_event_replay_cmd(args: argparse.Namespace) -> list[str]:
    if args.events_json is None:
        raise ValueError("--events-json is required in event mode")
    if not args.iface:
        raise ValueError("--iface is required in event mode")

    replay_cmd = [
        "sudo",
        "python3",
        str(args.replay_script),
        "--events-json", str(args.events_json),
        "--iface", args.iface,
        "--default-rate-mbps", str(args.default_rate_mbps),
        "--default-delay-ms", str(args.default_delay_ms),
        "--default-loss-pct", str(args.default_loss_pct),
        "--default-jitter-ms", str(args.default_jitter_ms),
        "--burst-kbit", str(args.burst_kbit),
        "--tbf-latency-ms", str(args.tbf_latency_ms),
        "--handover-loss-pct", str(args.handover_loss_pct),
        "--outage-loss-pct", str(args.outage_loss_pct),
        "--obstruction-loss-pct", str(args.obstruction_loss_pct),
        "--time-scale", str(args.time_scale),
        "--start-delay-sec", str(args.start_delay_sec),
        "--event-offset-sec", str(args.event_offset_sec),
    ]
    if args.restore_default_between_events:
        replay_cmd.append("--restore-default-between-events")
    if args.dry_run:
        replay_cmd.append("--dry-run")
    return replay_cmd


def build_profile_replay_cmd(args: argparse.Namespace) -> list[str]:
    if args.profile_csv is None:
        raise ValueError("--profile-csv is required in profile mode")
    dev = args.dev or args.iface
    if not dev:
        raise ValueError("--dev (or --iface) is required in profile mode")

    replay_cmd = [
        "sudo",
        "python3",
        str(args.replay_script),
        "--csv", str(args.profile_csv),
        "--dev", dev,
    ]
    if args.default_rate_mbps is not None:
        replay_cmd += ["--default-rate-mbit", str(args.default_rate_mbps)]
    if args.preserve_existing:
        replay_cmd.append("--preserve-existing")
    if args.setup_only:
        replay_cmd.append("--setup-only")
    if args.verbose:
        replay_cmd.append("--verbose")
    if args.dry_run:
        replay_cmd.append("--dry-run")
    return replay_cmd


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Launch remote client iperf+ping via SSH, then start tc replay on router"
    )

    ap.add_argument("--client-host", required=True, help="SSH host/IP of client")
    ap.add_argument("--client-user", required=True, help="SSH user of client")
    ap.add_argument("--client-port", type=int, default=22, help="SSH port")
    ap.add_argument("--client-identity-file", default=None, help="SSH private key path")
    ap.add_argument("--client-known-hosts", default=None, help="Optional UserKnownHostsFile")

    ap.add_argument("--remote-out-dir", default="~/replay_measure", help="Remote output directory")
    ap.add_argument("--remote-iperf-json", default="iperf_client.json", help="Remote iperf JSON filename")
    ap.add_argument("--remote-ping-log", default="ping_client.log", help="Remote ping raw log filename")
    ap.add_argument("--remote-shell-log", default="run_client_measure.log", help="Remote wrapper shell log filename")

    ap.add_argument("--iperf-host", required=True, help="iperf server host/IP")
    ap.add_argument("--iperf-port", type=int, default=5201)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--protocol", choices=["tcp", "udp"], default="udp")
    ap.add_argument("--udp-bitrate-mbps", type=float, default=None)
    ap.add_argument("--iperf-interval", type=float, default=0.1)
    ap.add_argument("--ping-interval", type=float, default=0.2)
    ap.add_argument("--reverse", action="store_true")
    ap.add_argument("--ipv6", action="store_true")

    ap.add_argument("--replay-mode", choices=["event", "profile"], default="event")
    ap.add_argument("--replay-script", required=True, type=Path, help="Path to replay script on router")

    ap.add_argument("--events-json", type=Path, default=None)
    ap.add_argument("--profile-csv", type=Path, default=None)

    ap.add_argument("--iface", default=None, help="Router interface for event replay; also used as fallback in profile mode")
    ap.add_argument("--dev", default=None, help="Router device for profile replay")

    ap.add_argument("--default-rate-mbps", type=float, default=260.0)
    ap.add_argument("--default-delay-ms", type=float, default=15.0)
    ap.add_argument("--default-loss-pct", type=float, default=0.0)
    ap.add_argument("--default-jitter-ms", type=float, default=0.1)
    ap.add_argument("--burst-kbit", type=int, default=32)
    ap.add_argument("--tbf-latency-ms", type=int, default=400)
    ap.add_argument("--handover-loss-pct", type=float, default=5.0)
    ap.add_argument("--outage-loss-pct", type=float, default=99.0)
    ap.add_argument("--obstruction-loss-pct", type=float, default=10.0)
    ap.add_argument("--time-scale", type=float, default=1.0)
    ap.add_argument("--restore-default-between-events", action="store_true")
    ap.add_argument("--start-delay-sec", type=float, default=0.0)
    ap.add_argument("--event-offset-sec", type=float, default=0.0)

    ap.add_argument("--preserve-existing", action="store_true")
    ap.add_argument("--setup-only", action="store_true")
    ap.add_argument("--verbose", action="store_true")

    ap.add_argument("--dry-run", action="store_true")

    ap.add_argument(
        "--client-start-lead-sec",
        type=float,
        default=2.0,
        help="Wait after SSH launch before starting replay on router",
    )

    args = ap.parse_args()

    remote_out_dir = args.remote_out_dir.rstrip("/")
    remote_iperf_json_path = f"{remote_out_dir}/{args.remote_iperf_json}"
    remote_ping_log_path = f"{remote_out_dir}/{args.remote_ping_log}"
    remote_shell_log_path = f"{remote_out_dir}/{args.remote_shell_log}"

    remote_cmd = build_remote_measurement_command(
        iperf_host=args.iperf_host,
        duration=args.duration,
        protocol=args.protocol,
        udp_bitrate_mbps=args.udp_bitrate_mbps,
        iperf_interval=args.iperf_interval,
        reverse=args.reverse,
        ipv6=args.ipv6,
        port=args.iperf_port,
        iperf_json_path=remote_iperf_json_path,
        ping_log_path=remote_ping_log_path,
        ping_interval=args.ping_interval,
        shell_log_path=remote_shell_log_path,
    )

    mkdir_cmd = add_common_ssh_args(
        ["ssh"],
        port=args.client_port,
        identity_file=args.client_identity_file,
        known_hosts=args.client_known_hosts,
    )
    mkdir_cmd += [
        f"{args.client_user}@{args.client_host}",
        f"mkdir -p {shlex.quote(remote_out_dir)}",
    ]

    ssh_cmd = add_common_ssh_args(
        ["ssh"],
        port=args.client_port,
        identity_file=args.client_identity_file,
        known_hosts=args.client_known_hosts,
    )
    ssh_cmd += [f"{args.client_user}@{args.client_host}", remote_cmd]

    if args.replay_mode == "event":
        replay_cmd = build_event_replay_cmd(args)
    else:
        replay_cmd = build_profile_replay_cmd(args)

    print("[0/2] Ensure remote output directory exists")
    run(mkdir_cmd, check=True)

    print("[1/2] Launch iperf + ping logging on remote client via SSH")
    run(ssh_cmd, check=True)

    if args.client_start_lead_sec > 0:
        print(f"[wait] sleep {args.client_start_lead_sec:.3f}s before replay")
        time.sleep(args.client_start_lead_sec)

    print(f"[2/2] Start tc replay on router (mode={args.replay_mode})")
    run(replay_cmd, check=True)

    print("Done.")
    print("Remote files:")
    print(f"  iperf json : {args.client_user}@{args.client_host}:{remote_iperf_json_path}")
    print(f"  ping log   : {args.client_user}@{args.client_host}:{remote_ping_log_path}")
    print(f"  shell log  : {args.client_user}@{args.client_host}:{remote_shell_log_path}")


if __name__ == "__main__":
    main()
