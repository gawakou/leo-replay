from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Iterable

from .directional_profile import LinkCondition


class TcBackendError(RuntimeError):
    """Raised when a tc/ip command fails."""


@dataclass
class CommandRunner:
    dry_run: bool = False
    verbose: bool = False

    def run(self, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str] | None:
        print("$ " + shlex.join(command))
        if self.dry_run:
            return None
        process = subprocess.run(command, capture_output=True, text=True)
        if self.verbose and process.stdout:
            print(process.stdout, end="")
        if process.returncode != 0 and check:
            if process.stderr:
                print(process.stderr, end="", file=os.sys.stderr)
            raise TcBackendError(f"command failed ({process.returncode}): {shlex.join(command)}")
        return process

    def run_many(self, commands: Iterable[list[str]], *, check: bool = True) -> None:
        for command in commands:
            self.run(command, check=check)


def require_linux_root(*, dry_run: bool) -> None:
    if dry_run:
        return
    if os.name != "posix" or not os.path.exists("/proc"):
        raise PermissionError("tc replay requires Linux; use --dry-run on other platforms")
    if os.geteuid() != 0:
        raise PermissionError("tc replay requires root privileges; use --dry-run for validation")


def build_netem_command(device: str, condition: LinkCondition) -> list[str]:
    condition.validate(path=f"device[{device}]")
    command = ["tc", "qdisc", "replace", "dev", device, "root", "netem"]
    if condition.delay_ms > 0 or condition.jitter_ms > 0:
        command.extend(["delay", f"{condition.delay_ms:.6f}ms"])
        if condition.jitter_ms > 0:
            command.append(f"{condition.jitter_ms:.6f}ms")
            if condition.correlation_pct > 0:
                command.append(f"{condition.correlation_pct:.3f}%")
    if condition.loss_pct > 0:
        command.extend(["loss", f"{condition.loss_pct:.6f}%"])
        if condition.correlation_pct > 0:
            command.append(f"{condition.correlation_pct:.3f}%")
    if condition.rate_mbit is not None and condition.rate_mbit > 0:
        command.extend(["rate", f"{condition.rate_mbit:.6f}mbit"])
    if condition.reorder_pct > 0:
        command.extend(["reorder", f"{condition.reorder_pct:.6f}%"])
        if condition.correlation_pct > 0:
            command.append(f"{condition.correlation_pct:.3f}%")
    return command


def clear_root_qdisc(runner: CommandRunner, device: str) -> None:
    runner.run(["tc", "qdisc", "del", "dev", device, "root"], check=False)


def clear_ingress_qdisc(runner: CommandRunner, device: str) -> None:
    runner.run(["tc", "qdisc", "del", "dev", device, "ingress"], check=False)


def setup_ifb(runner: CommandRunner, *, physical_device: str, ifb_device: str) -> None:
    runner.run(["modprobe", "ifb"], check=False)
    if runner.dry_run:
        print(f"# ensure IFB device {ifb_device} exists")
        runner.run(["ip", "link", "add", ifb_device, "type", "ifb"], check=False)
    else:
        exists = subprocess.run(
            ["ip", "link", "show", "dev", ifb_device], capture_output=True, text=True
        ).returncode == 0
        if not exists:
            runner.run(["ip", "link", "add", ifb_device, "type", "ifb"])
    runner.run(["ip", "link", "set", "dev", ifb_device, "up"])
    runner.run(
        ["tc", "qdisc", "replace", "dev", physical_device, "handle", "ffff:", "ingress"]
    )
    runner.run(
        [
            "tc",
            "filter",
            "replace",
            "dev",
            physical_device,
            "parent",
            "ffff:",
            "protocol",
            "all",
            "u32",
            "match",
            "u32",
            "0",
            "0",
            "action",
            "mirred",
            "egress",
            "redirect",
            "dev",
            ifb_device,
        ]
    )


def cleanup_ifb(
    runner: CommandRunner,
    *,
    physical_device: str,
    ifb_device: str,
    delete_device: bool = False,
) -> None:
    clear_ingress_qdisc(runner, physical_device)
    clear_root_qdisc(runner, ifb_device)
    if delete_device:
        runner.run(["ip", "link", "set", "dev", ifb_device, "down"], check=False)
        runner.run(["ip", "link", "delete", ifb_device, "type", "ifb"], check=False)
