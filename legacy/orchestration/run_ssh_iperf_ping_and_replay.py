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

    iperf_cmd = " ".join(shlex.quote(x) for x in iperf_parts) + f" > {shlex.quote(iperf_json_path)}"

    ping_parts: list[str] = [
        "ping",
        "-i", str(ping_interval),
        "-n",
    ]
    if ipv6:
        ping_parts.append("-6")
    ping_parts.append(iperf_host)

    ping_cmd = " ".join(shlex.quote(x) for x in ping_parts) + f" > {shlex.quote(ping_log_path)}"
    wrapped_ping_cmd = f"timeout {duration + 5.0}s bash -lc {shlex.quote(ping_cmd)}"

    remote_dir = str(Path(iperf_json_path).parent)

    body = f"""set -e
mkdir -p {shlex.quote(remote_dir)}
{iperf_cmd} &
IPERF_PID=$!
{wrapped_ping_cmd} &
PING_PID=$!
wait "$IPERF_PID"
wait "$PING_PID" || true
"""

    remote_cmd = (
        f"nohup bash -lc {shlex.quote(body)} "
        f"> {shlex.quote(shell_log_path)} 2>&1 < /dev/null &"
    )
    return remote_cmd


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

    ap.add_argument("--replay-script", required=True, type=Path, help="Path to tc_event_replay.py on router")
    ap.add_argument("--events-json", required=True, type=Path)
    ap.add_argument("--iface", required=True)
    ap.add_argument("--default-rate-mbps", type=float, default=260.0)
    ap.add_argument("--default-delay-ms", type=float, default=15.0)
    ap.add_argument("--default-loss-pct", type=float, default=0.0)
    ap.add_argument("--default-jitter-ms", type=float, default=0.1)
    ap.add_argument("--burst-kbit", type=int, default=32)
    ap.add_argument("--tbf-latency-ms", type=int, default=400)
    ap.add_argument("--backhaul-extra-delay-ms", type=float, default=8.0)
    ap.add_argument("--handover-extra-delay-ms", type=float, default=20.0)
    ap.add_argument("--handover-loss-pct", type=float, default=5.0)
    ap.add_argument("--outage-loss-pct", type=float, default=99.0)
    ap.add_argument("--obstruction-loss-pct", type=float, default=10.0)
    ap.add_argument("--time-scale", type=float, default=1.0)
    ap.add_argument("--restore-default-between-events", action="store_true")
    ap.add_argument("--start-delay-sec", type=float, default=0.0)
    ap.add_argument("--event-offset-sec", type=float, default=0.0)
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

    ssh_cmd = ["ssh", "-p", str(args.client_port)]
    if args.client_identity_file:
        ssh_cmd += ["-i", args.client_identity_file]
    if args.client_known_hosts:
        ssh_cmd += ["-o", f"UserKnownHostsFile={args.client_known_hosts}"]
    ssh_cmd += [f"{args.client_user}@{args.client_host}", remote_cmd]

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
        #"--backhaul-extra-delay-ms", str(args.backhaul_extra_delay_ms),
        #"--handover-extra-delay-ms", str(args.handover_extra_delay_ms),
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

    print("[1/2] Launch iperf + ping logging on remote client via SSH")
    run(ssh_cmd, check=True)

    if args.client_start_lead_sec > 0:
        print(f"[wait] sleep {args.client_start_lead_sec:.3f}s before replay")
        time.sleep(args.client_start_lead_sec)

    print("[2/2] Start tc replay on router")
    run(replay_cmd, check=True)

    print("Done.")
    print("Remote files:")
    print(f"  iperf json : {args.client_user}@{args.client_host}:{remote_iperf_json_path}")
    print(f"  ping log   : {args.client_user}@{args.client_host}:{remote_ping_log_path}")
    print(f"  shell log  : {args.client_user}@{args.client_host}:{remote_shell_log_path}")


if __name__ == "__main__":
    main()
