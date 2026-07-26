from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.orbit.snapshot import (
    OrbitSnapshotError,
    SnapshotPart,
    verify_snapshot,
    write_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/orbit/iss-omm.example.json"


def test_snapshot_round_trip_and_tamper_detection(tmp_path):
    output = tmp_path / "snapshot"
    request = {
        "provider": "fixture",
        "query": {"NORAD_CAT_ID": "25544"},
        "format": "json",
    }
    result = write_snapshot(
        output,
        provider="fixture",
        request=request,
        output_format="json",
        parts=[
            SnapshotPart(
                body=EXAMPLE.read_bytes(),
                headers={"Content-Type": "application/json"},
                source_uri="https://example.invalid/orbit.json",
            )
        ],
    )
    assert result.manifest["record_count"] == 1
    verified = verify_snapshot(output)
    assert verified["status"] == "pass"
    assert verified["record_count"] == 1
    assert (output / "orbit.json").is_file()
    assert (output / "request.json").is_file()
    assert (output / "raw/part-0001.json").is_file()

    payload = json.loads((output / "orbit.json").read_text(encoding="utf-8"))
    payload[0]["OBJECT_NAME"] = "TAMPERED"
    (output / "orbit.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(OrbitSnapshotError, match="SHA-256 mismatch"):
        verify_snapshot(output)


def test_snapshot_rejects_non_omm_json(tmp_path):
    with pytest.raises(OrbitSnapshotError, match="missing EPOCH"):
        write_snapshot(
            tmp_path / "bad",
            provider="fixture",
            request={"provider": "fixture"},
            output_format="json",
            parts=[SnapshotPart(body=b'[{"NORAD_CAT_ID": 25544}]', headers={}, source_uri="fixture")],
        )


def test_snapshot_merges_csv_parts(tmp_path):
    csv_body = (ROOT / "examples/orbit/iss-omm.example.csv").read_bytes()
    output = tmp_path / "csv-snapshot"
    result = write_snapshot(
        output,
        provider="fixture",
        request={"provider": "fixture", "format": "csv", "parts": 2},
        output_format="csv",
        parts=[
            SnapshotPart(csv_body, {}, "fixture://csv/1"),
            SnapshotPart(csv_body, {}, "fixture://csv/2"),
        ],
    )
    assert result.manifest["record_count"] == 2
    assert verify_snapshot(output)["part_count"] == 2


def test_snapshot_merges_tle_parts(tmp_path):
    tle_body = (ROOT / "examples/orbit/iss-tle.example.tle").read_bytes()
    output = tmp_path / "tle-snapshot"
    result = write_snapshot(
        output,
        provider="fixture",
        request={"provider": "fixture", "format": "tle", "parts": 2},
        output_format="tle",
        parts=[
            SnapshotPart(tle_body, {}, "fixture://tle/1"),
            SnapshotPart(tle_body, {}, "fixture://tle/2"),
        ],
    )
    assert result.manifest["record_count"] == 2
    assert verify_snapshot(output)["record_count"] == 2


def test_snapshot_verifier_rejects_path_escape(tmp_path):
    output = tmp_path / "snapshot"
    write_snapshot(
        output,
        provider="fixture",
        request={"provider": "fixture", "format": "json"},
        output_format="json",
        parts=[SnapshotPart(EXAMPLE.read_bytes(), {}, "fixture://iss")],
    )
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["combined_body_file"] = "../outside.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(OrbitSnapshotError, match="escapes"):
        verify_snapshot(output)
