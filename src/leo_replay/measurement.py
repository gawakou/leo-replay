from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


_PING_TIME_RE = re.compile(r"time[=<]([0-9.]+)\s*ms")
_TRACEROUTE_HOP_RE = re.compile(r"^\s*(\d+)\s+(.+)$")


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    started_at_utc: str
    finished_at_utc: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class PingSample:
    sequence: int
    rtt_ms: float | None
    timeout: bool
    raw: str


@dataclass(frozen=True)
class TracerouteHop:
    hop: int
    raw: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_command(command: Sequence[str], timeout_sec: float | None = None) -> CommandResult:
    started = utc_now_iso()
    completed = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_sec,
    )
    finished = utc_now_iso()
    return CommandResult(
        command=list(command),
        started_at_utc=started,
        finished_at_utc=finished,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def parse_ping_output(text: str) -> list[PingSample]:
    samples: list[PingSample] = []
    sequence = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _PING_TIME_RE.search(stripped)
        if match:
            samples.append(
                PingSample(
                    sequence=sequence,
                    rtt_ms=float(match.group(1)),
                    timeout=False,
                    raw=stripped,
                )
            )
            sequence += 1
            continue
        lower = stripped.lower()
        if "timeout" in lower or "unreachable" in lower:
            samples.append(PingSample(sequence=sequence, rtt_ms=None, timeout=True, raw=stripped))
            sequence += 1
    return samples


def parse_traceroute_output(text: str) -> list[TracerouteHop]:
    hops: list[TracerouteHop] = []
    for line in text.splitlines():
        match = _TRACEROUTE_HOP_RE.match(line)
        if match:
            hops.append(TracerouteHop(hop=int(match.group(1)), raw=line.strip()))
    return hops


def write_ping_csv(path: Path, samples: Iterable[PingSample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sequence", "rtt_ms", "timeout", "raw"])
        writer.writeheader()
        for sample in samples:
            writer.writerow(asdict(sample))


def write_traceroute_json(path: Path, hops: Iterable[TracerouteHop]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(hop) for hop in hops], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def create_measurement_manifest(
    output_dir: Path,
    *,
    kind: str,
    target: str,
    command_result: CommandResult,
    data_files: Iterable[Path],
) -> dict[str, object]:
    files = []
    for path in sorted(data_files, key=lambda item: item.name):
        files.append(
            {
                "name": path.name,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "kind": kind,
        "target": target,
        "started_at_utc": command_result.started_at_utc,
        "finished_at_utc": command_result.finished_at_utc,
        "command": command_result.command,
        "returncode": command_result.returncode,
        "files": files,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def verify_measurement_snapshot(input_dir: Path) -> list[str]:
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.exists():
        return ["manifest.json is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read manifest.json: {exc}"]

    errors: list[str] = []
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict):
            errors.append("invalid file entry in manifest")
            continue
        name = entry.get("name")
        expected = entry.get("sha256")
        if not isinstance(name, str) or not isinstance(expected, str):
            errors.append("manifest file entry is missing name or sha256")
            continue
        path = input_dir / name
        if not path.exists():
            errors.append(f"missing file: {name}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            errors.append(f"sha256 mismatch: {name}")
    return errors
