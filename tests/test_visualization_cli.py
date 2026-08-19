from __future__ import annotations

from pathlib import Path

from leo_replay.cli import main
from test_visualization_bundle import write_fixture


def test_visualization_build_cli(tmp_path: Path, capsys):
    source = write_fixture(tmp_path)
    output = tmp_path / "bundle"
    result = main(
        [
            "viz",
            "build",
            "--selection", str(source["selection"]),
            "--site", str(source["site"]),
            "--profile", str(source["profile"]),
            "--events", str(source["events"]),
            "--output-dir", str(output),
        ]
    )
    assert result == 0
    assert (output / "index.html").is_file()
    assert '"status": "built"' in capsys.readouterr().out


def test_visualization_help(capsys):
    try:
        main(["viz", "build", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "--selection" in capsys.readouterr().out
