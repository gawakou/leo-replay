from __future__ import annotations

import json
from pathlib import Path

from leo_replay import measure_cli
from leo_replay.measurement import CommandResult


def _result(stdout: str, returncode: int = 0) -> CommandResult:
    return CommandResult(
        command=["dummy"],
        started_at_utc="2026-08-19T00:00:00Z",
        finished_at_utc="2026-08-19T00:00:01Z",
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_ping_command_writes_verifiable_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(measure_cli, "_require_tool", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        measure_cli,
        "run_command",
        lambda command, timeout_sec=None: _result(
            "64 bytes from 127.0.0.1: icmp_seq=0 ttl=64 time=0.123 ms\n"
        ),
    )
    output = tmp_path / "ping"
    assert measure_cli.main([
        "ping", "--target", "127.0.0.1", "--count", "1",
        "--output-dir", str(output),
    ]) == 0
    assert (output / "ping.csv").exists()
    assert (output / "ping.txt").exists()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "ping"
    assert measure_cli.main(["verify", "--input-dir", str(output)]) == 0


def test_traceroute_command_writes_verifiable_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(measure_cli, "_require_tool", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        measure_cli,
        "run_command",
        lambda command, timeout_sec=None: _result(
            "traceroute to localhost (127.0.0.1), 30 hops max\n"
            " 1  127.0.0.1  0.100 ms  0.110 ms  0.120 ms\n"
        ),
    )
    output = tmp_path / "trace"
    assert measure_cli.main([
        "traceroute", "--target", "127.0.0.1", "--output-dir", str(output),
    ]) == 0
    hops = json.loads((output / "traceroute.json").read_text(encoding="utf-8"))
    assert hops[0]["hop"] == 1
    assert measure_cli.main(["verify", "--input-dir", str(output)]) == 0


def test_nonempty_output_directory_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("do not overwrite\n", encoding="utf-8")
    assert measure_cli.main([
        "ping", "--target", "127.0.0.1", "--count", "1",
        "--output-dir", str(output),
    ]) == 2
