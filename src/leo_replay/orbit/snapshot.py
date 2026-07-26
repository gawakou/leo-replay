from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from leo_replay import __version__

from .models import OrbitDataError, iso_utc, parse_utc, sha256_file, utc_now_iso


class OrbitSnapshotError(OrbitDataError):
    """Raised when an orbit snapshot cannot be created or verified."""


@dataclass(frozen=True)
class SnapshotPart:
    body: bytes
    headers: Mapping[str, str]
    source_uri: str
    status: int = 200


@dataclass(frozen=True)
class SnapshotWriteResult:
    output_dir: Path
    manifest: dict[str, Any]
    reused: bool = False



SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
}


def sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in headers.items()
        if str(key).strip().lower() not in SENSITIVE_HEADER_NAMES
    }

FORMAT_EXTENSIONS = {
    "json": ".json",
    "csv": ".csv",
    "tle": ".tle",
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def request_fingerprint(request: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(request))).hexdigest()


def _json_records(body: bytes) -> list[dict[str, Any]]:
    try:
        value = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OrbitSnapshotError(f"invalid JSON orbit response: {exc}") from exc
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        value = value["data"]
    elif isinstance(value, dict):
        value = [value]
    if not isinstance(value, list) or not value:
        raise OrbitSnapshotError("JSON orbit response contains no records")
    if not all(isinstance(row, dict) for row in value):
        raise OrbitSnapshotError("JSON orbit response records must be objects")
    rows = [dict(row) for row in value]
    _validate_omm_fields(rows[0])
    return rows


def _csv_records(body: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise OrbitSnapshotError(f"invalid CSV encoding: {exc}") from exc
    reader = csv.DictReader(text.splitlines())
    rows = list(reader)
    if not reader.fieldnames or not rows:
        raise OrbitSnapshotError("CSV orbit response contains no records")
    _validate_omm_fields(rows[0])
    return list(reader.fieldnames), rows


def _tle_record_count(body: bytes) -> int:
    try:
        lines = body.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise OrbitSnapshotError(f"invalid TLE encoding: {exc}") from exc
    line1 = [line for line in lines if line.startswith("1 ")]
    line2 = [line for line in lines if line.startswith("2 ")]
    if not line1 or len(line1) != len(line2):
        raise OrbitSnapshotError("TLE response does not contain matching line 1/line 2 records")
    return len(line1)


def _validate_omm_fields(row: Mapping[str, Any]) -> None:
    required = {"NORAD_CAT_ID", "EPOCH"}
    missing = sorted(key for key in required if row.get(key) in (None, ""))
    if missing:
        raise OrbitSnapshotError(
            "orbit response does not look like OMM-compatible data; missing " + ", ".join(missing)
        )


def record_count(body: bytes, output_format: str) -> int:
    if output_format == "json":
        return len(_json_records(body))
    if output_format == "csv":
        return len(_csv_records(body)[1])
    if output_format == "tle":
        return _tle_record_count(body)
    raise OrbitSnapshotError(f"unsupported snapshot format: {output_format}")


def merge_parts(parts: Iterable[SnapshotPart], output_format: str) -> tuple[bytes, int]:
    values = list(parts)
    if not values:
        raise OrbitSnapshotError("no response parts were provided")
    if output_format == "json":
        merged: list[dict[str, Any]] = []
        for part in values:
            merged.extend(_json_records(part.body))
        body = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        return body, len(merged)
    if output_format == "csv":
        fieldnames: list[str] = []
        rows: list[dict[str, str]] = []
        for part in values:
            current_fields, current_rows = _csv_records(part.body)
            for field in current_fields:
                if field not in fieldnames:
                    fieldnames.append(field)
            rows.extend(current_rows)
        from io import StringIO

        output = StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode("utf-8"), len(rows)
    if output_format == "tle":
        chunks = []
        count = 0
        for part in values:
            count += _tle_record_count(part.body)
            chunks.append(part.body.rstrip() + b"\n")
        return b"".join(chunks), count
    raise OrbitSnapshotError(f"unsupported snapshot format: {output_format}")


def _snapshot_member(output_dir: Path, relative: str) -> Path:
    candidate = (output_dir / relative).resolve()
    try:
        candidate.relative_to(output_dir.resolve())
    except ValueError as exc:
        raise OrbitSnapshotError(f"snapshot path escapes the snapshot directory: {relative}") from exc
    return candidate


def load_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "manifest.json"
    if not path.is_file():
        raise OrbitSnapshotError(f"snapshot manifest not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OrbitSnapshotError(f"invalid snapshot manifest: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise OrbitSnapshotError("snapshot manifest must be a JSON object")
    return value


def existing_snapshot_matches(output_dir: Path, request: Mapping[str, Any]) -> bool:
    if not (output_dir / "manifest.json").is_file():
        return False
    manifest = load_manifest(output_dir)
    return manifest.get("request_fingerprint") == request_fingerprint(request)


def snapshot_age_seconds(output_dir: Path, *, now: datetime | None = None) -> float:
    manifest = load_manifest(output_dir)
    timestamp = manifest.get("retrieved_at_utc")
    if not isinstance(timestamp, str):
        raise OrbitSnapshotError("snapshot manifest has no retrieved_at_utc")
    current = now or datetime.now(timezone.utc)
    return max(0.0, (current - parse_utc(timestamp)).total_seconds())


def write_snapshot(
    output_dir: Path,
    *,
    provider: str,
    request: Mapping[str, Any],
    output_format: str,
    parts: Iterable[SnapshotPart],
    retrieved_at_utc: str | None = None,
    force: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> SnapshotWriteResult:
    if output_format not in FORMAT_EXTENSIONS:
        raise OrbitSnapshotError(f"unsupported snapshot format: {output_format}")
    output_dir = output_dir.resolve()
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists() and not force:
        raise OrbitSnapshotError(
            f"snapshot directory already exists: {output_dir}; use a new directory or --force"
        )

    values = list(parts)
    combined_body, count = merge_parts(values, output_format)
    retrieved = iso_utc(parse_utc(retrieved_at_utc)) if retrieved_at_utc else utc_now_iso()
    extension = FORMAT_EXTENSIONS[output_format]
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=parent))
    try:
        raw_dir = temp_dir / "raw"
        raw_dir.mkdir(parents=True)
        part_documents = []
        for index, part in enumerate(values, start=1):
            filename = f"part-{index:04d}{extension}"
            body_path = raw_dir / filename
            body_path.write_bytes(part.body)
            headers_path = raw_dir / f"part-{index:04d}.headers.json"
            safe_headers = sanitize_headers(part.headers)
            headers_path.write_text(
                json.dumps(safe_headers, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            part_documents.append(
                {
                    "index": index,
                    "status": part.status,
                    "source_uri": part.source_uri,
                    "body_file": str(body_path.relative_to(temp_dir)),
                    "headers_file": str(headers_path.relative_to(temp_dir)),
                    "sha256": sha256_file(body_path),
                    "bytes": body_path.stat().st_size,
                    "record_count": record_count(part.body, output_format),
                    "sensitive_headers_removed": len(part.headers) - len(safe_headers),
                }
            )

        combined_path = temp_dir / f"orbit{extension}"
        combined_path.write_bytes(combined_body)
        request_document = dict(request)
        request_path = temp_dir / "request.json"
        request_path.write_text(
            json.dumps(request_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        manifest = {
            "schema_version": "1.0",
            "manifest_type": "orbit_snapshot",
            "generated_at_utc": utc_now_iso(),
            "retrieved_at_utc": retrieved,
            "generator": f"leo-replay {__version__}",
            "provider": provider,
            "request_fingerprint": request_fingerprint(request_document),
            "request_file": "request.json",
            "format": output_format,
            "combined_body_file": combined_path.name,
            "combined_sha256": sha256_file(combined_path),
            "record_count": count,
            "part_count": len(part_documents),
            "parts": part_documents,
            "metadata": dict(metadata or {}),
        }
        (temp_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        verify_snapshot(temp_dir)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        temp_dir.rename(output_dir)
        return SnapshotWriteResult(output_dir=output_dir, manifest=manifest, reused=False)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def verify_snapshot(output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    manifest = load_manifest(output_dir)
    if manifest.get("manifest_type") != "orbit_snapshot":
        raise OrbitSnapshotError("manifest_type is not orbit_snapshot")
    request_file = _snapshot_member(
        output_dir, str(manifest.get("request_file", "request.json"))
    )
    if not request_file.is_file():
        raise OrbitSnapshotError(f"snapshot request file not found: {request_file}")
    request = json.loads(request_file.read_text(encoding="utf-8"))
    expected_request_hash = request_fingerprint(request)
    if expected_request_hash != manifest.get("request_fingerprint"):
        raise OrbitSnapshotError("snapshot request fingerprint mismatch")

    combined = _snapshot_member(output_dir, str(manifest.get("combined_body_file", "")))
    if not combined.is_file():
        raise OrbitSnapshotError(f"combined orbit file not found: {combined}")
    if sha256_file(combined) != manifest.get("combined_sha256"):
        raise OrbitSnapshotError("combined orbit file SHA-256 mismatch")
    output_format = str(manifest.get("format", ""))
    actual_count = record_count(combined.read_bytes(), output_format)
    if actual_count != manifest.get("record_count"):
        raise OrbitSnapshotError(
            f"combined orbit record count mismatch: expected {manifest.get('record_count')}, got {actual_count}"
        )

    parts = manifest.get("parts")
    if not isinstance(parts, list) or not parts:
        raise OrbitSnapshotError("snapshot manifest contains no parts")
    for part in parts:
        if not isinstance(part, dict):
            raise OrbitSnapshotError("snapshot part metadata must be an object")
        body_path = _snapshot_member(output_dir, str(part.get("body_file", "")))
        headers_path = _snapshot_member(output_dir, str(part.get("headers_file", "")))
        if not body_path.is_file() or not headers_path.is_file():
            raise OrbitSnapshotError(f"snapshot part files are missing for part {part.get('index')}")
        if sha256_file(body_path) != part.get("sha256"):
            raise OrbitSnapshotError(f"snapshot part SHA-256 mismatch for part {part.get('index')}")
        if record_count(body_path.read_bytes(), output_format) != part.get("record_count"):
            raise OrbitSnapshotError(f"snapshot part record count mismatch for part {part.get('index')}")

    return {
        "status": "pass",
        "snapshot_dir": str(output_dir),
        "provider": manifest.get("provider"),
        "format": output_format,
        "record_count": actual_count,
        "part_count": len(parts),
        "combined_body_file": str(combined),
        "retrieved_at_utc": manifest.get("retrieved_at_utc"),
    }
