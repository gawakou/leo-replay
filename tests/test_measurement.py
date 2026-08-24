from __future__ import annotations

import json
from pathlib import Path

from leo_replay.measurement import (
    CommandResult,
    PingSample,
    TracerouteHop,
    create_measurement_manifest,
    parse_ping_output,
    parse_traceroute_output,
    verify_measurement_snapshot,
    write_ping_csv,
    write_traceroute_json,
)


def test_parse_ping_output_supports_rtt_and_timeout() -> None:
    text = """
64 bytes from 127.0.0.1: icmp_seq=0 ttl=64 time=0.123 ms
Request timeout for icmp_seq 1
64 bytes from 127.0.0.1: icmp_seq=2 ttl=64 time<1 ms
"""
    samples = parse_ping_output(text)
    assert [sample.sequence for sample in samples] == [0, 1, 2]
    assert samples[0].rtt_ms == 0.123
    assert samples[0].timeout is False
    assert samples[1].rtt_ms is None
    assert samples[1].timeout is True
    assert samples[2].rtt_ms == 1.0


def test_parse_traceroute_output_ignores_header() -> None:
    text = """
traceroute to example.net (192.0.2.1), 30 hops max
 1  192.0.2.254  1.000 ms  1.100 ms  1.200 ms
 2  * * *
"""
    hops = parse_traceroute_output(text)
    assert hops == [
        TracerouteHop(hop=1, raw="1  192.0.2.254  1.000 ms  1.100 ms  1.200 ms"),
        TracerouteHop(hop=2, raw="2  * * *"),
    ]


def _write_valid_snapshot(tmp_path: Path) -> Path:
    ping_path = tmp_path / "ping.csv"
    write_ping_csv(ping_path, [PingSample(sequence=0, rtt_ms=1.25, timeout=False, raw="ok")])
    result = CommandResult(
        command=["ping", "example.net"],
        started_at_utc="2026-08-19T00:00:00Z",
        finished_at_utc="2026-08-19T00:00:01Z",
        returncode=0,
        stdout="",
        stderr="",
    )
    create_measurement_manifest(
        tmp_path,
        kind="ping",
        target="example.net",
        command_result=result,
        data_files=[ping_path],
    )
    return ping_path


def test_manifest_verification_detects_tampering(tmp_path: Path) -> None:
    ping_path = tmp_path / "ping.csv"
    trace_path = tmp_path / "traceroute.json"
    write_ping_csv(ping_path, [PingSample(sequence=0, rtt_ms=1.25, timeout=False, raw="ok")])
    write_traceroute_json(trace_path, [TracerouteHop(hop=1, raw="1 192.0.2.1 1 ms")])

    result = CommandResult(
        command=["ping", "example.net"],
        started_at_utc="2026-08-19T00:00:00Z",
        finished_at_utc="2026-08-19T00:00:01Z",
        returncode=0,
        stdout="",
        stderr="",
    )
    create_measurement_manifest(
        tmp_path,
        kind="ping",
        target="example.net",
        command_result=result,
        data_files=[ping_path, trace_path],
    )
    assert verify_measurement_snapshot(tmp_path) == []

    ping_path.write_text("tampered\n", encoding="utf-8")
    assert verify_measurement_snapshot(tmp_path) == ["size mismatch: ping.csv"]


def test_manifest_verification_rejects_path_escape_and_duplicate_names(tmp_path: Path) -> None:
    _write_valid_snapshot(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["files"][0]
    manifest["files"] = [entry, dict(entry), {**entry, "name": "../outside.txt"}]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = verify_measurement_snapshot(tmp_path)
    assert "duplicate file entry: ping.csv" in errors
    assert "manifest file entry has an invalid name" in errors


def test_manifest_verification_rejects_invalid_metadata(tmp_path: Path) -> None:
    _write_valid_snapshot(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "2.0"
    manifest["files"][0]["sha256"] = "not-a-sha"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert verify_measurement_snapshot(tmp_path) == [
        "unsupported manifest schema_version",
        "invalid sha256: ping.csv",
    ]


def test_manifest_verification_rejects_symlinked_data_file(tmp_path: Path) -> None:
    ping_path = _write_valid_snapshot(tmp_path)
    real_path = tmp_path / "real.csv"
    ping_path.rename(real_path)
    ping_path.symlink_to(real_path.name)

    assert verify_measurement_snapshot(tmp_path) == ["symbolic link not allowed: ping.csv"]
