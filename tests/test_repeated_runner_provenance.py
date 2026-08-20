from pathlib import Path
import os
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


def test_repeated_runner_rejects_untracked_runtime_files(tmp_path: Path):
    repo, _ = _prepare_repo(tmp_path)
    runtime_file = repo / "src/leo_replay/local_override.py"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("VALUE = 'uncommitted'\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(repo / "experiments/run_repeated_lab.sh"), "--repetitions", "1"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 2
    assert "untracked runtime files detected" in result.stderr
    assert "src/leo_replay/local_override.py" in result.stderr
    assert "fixed-condition" not in result.stdout


def test_repeated_runner_rejects_existing_result_directory(tmp_path: Path):
    repo, _ = _prepare_repo(tmp_path)
    output_root = tmp_path / "results"
    existing = output_root / "docker-20260821T000000Z"
    existing.mkdir(parents=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_date = fake_bin / "date"
    fake_date.write_text(
        "#!/usr/bin/env bash\nprintf '20260821T000000Z\\n'\n",
        encoding="utf-8",
    )
    fake_date.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = subprocess.run(
        [
            "bash",
            str(repo / "experiments/run_repeated_lab.sh"),
            "--repetitions",
            "1",
            "--output",
            str(output_root),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )

    assert result.returncode == 2
    assert "refusing to mix artifacts" in result.stderr
    assert "fixed-condition" not in result.stdout
