import json
from pathlib import Path

from leo_replay.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_directionalize_and_dual_egress_dry_run(tmp_path: Path, capsys):
    directional = tmp_path / "directional.csv"
    metadata = tmp_path / "directional.meta.json"
    assert main([
        "profile", "directionalize", "--mode", "timeseries",
        "--input", str(ROOT / "examples/profile.example.csv"),
        "--output", str(directional),
        "--metadata-output", str(metadata),
    ]) == 0
    assert directional.exists()
    assert json.loads(metadata.read_text())["states"] == 6

    log = tmp_path / "execution.jsonl"
    assert main([
        "replay", "--mode", "timeseries",
        "--direction-mode", "dual-egress",
        "--input", str(directional),
        "--forward-dev", "eth-forward",
        "--reverse-dev", "eth-reverse",
        "--dry-run", "--setup-only",
        "--execution-log", str(log),
    ]) == 0
    output = capsys.readouterr().out
    assert "dev eth-forward root netem" in output
    assert "dev eth-reverse root netem" in output
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert {record["direction"] for record in records} == {"forward", "reverse"}


def test_ifb_dry_run_prepares_ingress_redirect(capsys):
    assert main([
        "replay", "--mode", "timeseries",
        "--direction-mode", "ifb",
        "--input", str(ROOT / "examples/profile.example.csv"),
        "--forward-dev", "eth-physical",
        "--ifb-dev", "ifb-test",
        "--dry-run", "--setup-only",
    ]) == 0
    output = capsys.readouterr().out
    assert "ip link add ifb-test type ifb" in output
    assert "mirred egress redirect dev ifb-test" in output
    assert "dev eth-physical root netem" in output
    assert "dev ifb-test root netem" in output


def test_directional_event_dual_egress_dry_run(tmp_path: Path, capsys):
    directional = tmp_path / "events-directional.json"
    assert main([
        "profile", "directionalize", "--mode", "event",
        "--input", str(ROOT / "examples/events-v1.example.json"),
        "--output", str(directional),
    ]) == 0
    assert main([
        "replay", "--mode", "event",
        "--direction-mode", "dual-egress",
        "--input", str(directional),
        "--forward-dev", "eth-forward",
        "--reverse-dev", "eth-reverse",
        "--dry-run",
    ]) == 0
    output = capsys.readouterr().out
    assert "[EVENT] EV-0001 handover_suspected" in output
    assert "dev eth-forward root netem" in output
    assert "dev eth-reverse root netem" in output
