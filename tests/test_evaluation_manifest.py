from __future__ import annotations

import json
from pathlib import Path

from leo_replay.evaluation_manifest import (
    MANIFEST_NAME,
    create_evaluation_manifest,
    verify_evaluation_manifest,
)


def test_evaluation_manifest_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    (tmp_path / "environment.txt").write_text("git_commit=abc123\n", encoding="utf-8")
    (tmp_path / "summary.json").write_text('{"runs": 1}\n', encoding="utf-8")
    (run_dir / "profile-execution.jsonl").write_text('{"lateness_ms": 1.0}\n', encoding="utf-8")

    manifest = create_evaluation_manifest(tmp_path)
    paths = [entry["path"] for entry in manifest["files"]]

    assert paths == ["environment.txt", "run-001/profile-execution.jsonl", "summary.json"]
    assert verify_evaluation_manifest(tmp_path) == []
    assert json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8"))["kind"] == "leo-replay-evaluation-artifacts"

    (run_dir / "profile-execution.jsonl").write_text('{"lateness_ms": 9.0}\n', encoding="utf-8")
    errors = verify_evaluation_manifest(tmp_path)
    assert "sha256 mismatch: run-001/profile-execution.jsonl" in errors


def test_evaluation_manifest_detects_untracked_file(tmp_path: Path) -> None:
    (tmp_path / "summary.json").write_text("{}\n", encoding="utf-8")
    create_evaluation_manifest(tmp_path)
    (tmp_path / "late-note.txt").write_text("changed after collection\n", encoding="utf-8")

    assert verify_evaluation_manifest(tmp_path) == ["untracked file: late-note.txt"]
