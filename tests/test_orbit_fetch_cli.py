from __future__ import annotations

import json
from pathlib import Path

from leo_replay.cli import main
from leo_replay.orbit.snapshot import SnapshotPart, SnapshotWriteResult, write_snapshot

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/orbit/iss-omm.example.json"


def test_celestrak_fetch_cli_dispatches_and_prints_snapshot(monkeypatch, tmp_path, capsys):
    output = tmp_path / "snapshot"
    manifest = {
        "provider": "celestrak",
        "record_count": 1,
        "part_count": 1,
        "combined_body_file": "orbit.json",
    }
    result = SnapshotWriteResult(output_dir=output, manifest=manifest, reused=False)
    captured = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return result

    monkeypatch.setattr("leo_replay.cli.fetch_celestrak_snapshot", fake_fetch)
    rc = main([
        "orbit", "fetch", "celestrak",
        "--group", "STARLINK",
        "--output-dir", str(output),
    ])
    assert rc == 0
    assert captured["query_type"] == "group"
    assert captured["query_value"] == "STARLINK"
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "fetched"
    assert value["records"] == 1


def test_verify_snapshot_cli(tmp_path, capsys):
    output = tmp_path / "snapshot"
    write_snapshot(
        output,
        provider="fixture",
        request={"provider": "fixture", "format": "json"},
        output_format="json",
        parts=[SnapshotPart(EXAMPLE.read_bytes(), {}, "fixture://iss")],
    )
    rc = main(["orbit", "verify-snapshot", "--input-dir", str(output)])
    assert rc == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "pass"
    assert value["record_count"] == 1
