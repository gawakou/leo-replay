from pathlib import Path

import pytest

from leo_replay.paper_bundle import PaperBundleError, _validate_distinct_paths


def _paths(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    return (
        tmp_path / "lab.json",
        tmp_path / "event.json",
        tmp_path / "orbit.json",
        tmp_path / "paper-metrics.tex",
        tmp_path / "paper-provenance.json",
    )


def test_paper_bundle_paths_allow_distinct_artifacts(tmp_path: Path) -> None:
    _validate_distinct_paths(*_paths(tmp_path))


def test_paper_bundle_paths_reject_output_overwriting_input(tmp_path: Path) -> None:
    lab, event, orbit, _output, manifest = _paths(tmp_path)

    with pytest.raises(PaperBundleError, match="lab and output"):
        _validate_distinct_paths(lab, event, orbit, lab, manifest)


def test_paper_bundle_paths_reject_manifest_overwriting_output(tmp_path: Path) -> None:
    lab, event, orbit, output, _manifest = _paths(tmp_path)

    with pytest.raises(PaperBundleError, match="output and manifest"):
        _validate_distinct_paths(lab, event, orbit, output, output)


def test_paper_bundle_paths_reject_relative_aliases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    lab = Path("lab.json")
    event = Path("event.json")
    orbit = Path("orbit.json")
    output = Path("paper-metrics.tex")

    with pytest.raises(PaperBundleError, match="output and manifest"):
        _validate_distinct_paths(lab, event, orbit, output, Path("./paper-metrics.tex"))
