from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments/run_repeated_lab.sh"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _prepare_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    experiments = repo / "experiments"
    experiments.mkdir(parents=True)
    runner = experiments / "run_repeated_lab.sh"
    shutil.copy2(RUNNER, runner)
    tracked = repo / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")

    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "LEO-Replay test")
    _git(repo, "add", "experiments/run_repeated_lab.sh", "tracked.txt")
    _git(repo, "commit", "-qm", "test fixture")
    return repo, tracked


@pytest.mark.parametrize("staged", [False, True])
def test_repeated_runner_rejects_tracked_worktree_changes(tmp_path: Path, staged: bool):
    repo, tracked = _prepare_repo(tmp_path)
    tracked.write_text("modified\n", encoding="utf-8")
    if staged:
        _git(repo, "add", "tracked.txt")

    result = subprocess.run(
        ["bash", str(repo / "experiments/run_repeated_lab.sh"), "--repetitions", "1"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 2
    assert "tracked Git changes detected" in result.stderr
