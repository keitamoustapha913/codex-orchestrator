from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import read_json


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _run_auto(git_repo: Path):
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--use-worktree", "--until", "DONE", "--live-progress"], git_repo)
    assert result.returncode == 0
    return result


def test_decomposition_cli_human_output(git_repo: Path):
    _run_auto(git_repo)
    result = _run_cli(["decomposition", "--repo", str(git_repo)], git_repo)
    assert result.returncode == 0
    assert "decomposition strategy:" in result.stdout


def test_decomposition_cli_json_output(git_repo: Path):
    _run_auto(git_repo)
    result = _run_cli(["decomposition", "--repo", str(git_repo), "--json"], git_repo)
    assert json.loads(result.stdout)["kind"] == "decomposition_status"


def test_decomposition_cli_patchlets_output(git_repo: Path):
    _run_auto(git_repo)
    result = _run_cli(["decomposition", "--repo", str(git_repo), "--patchlets"], git_repo)
    assert "P0001 ->" in result.stdout


def test_decomposition_cli_dependencies_output(git_repo: Path):
    _run_auto(git_repo)
    result = _run_cli(["decomposition", "--repo", str(git_repo), "--dependencies"], git_repo)
    assert "topological order:" in result.stdout


def test_status_json_includes_decomposition_summary(git_repo: Path):
    _run_auto(git_repo)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], git_repo)
    assert json.loads(result.stdout)["decomposition"]["patchlet_count"] >= 1


def test_monitor_shows_work_decomposition_planned_event(git_repo: Path):
    _run_auto(git_repo)
    result = _run_cli(["monitor", "--repo", str(git_repo), "--event-type", "work_decomposition_planned"], git_repo)
    assert "work_decomposition_planned" in result.stdout


def test_live_progress_prints_decomposition_summary(git_repo: Path):
    result = _run_auto(git_repo)
    assert "decomposition planned:" in result.stderr


def test_goal_progress_includes_decomposition_counts(git_repo: Path):
    _run_auto(git_repo)
    progress = read_json(git_repo / ".codex-orchestrator/goal_progress.json")
    assert progress["decomposition"]["patchlet_count"] >= 1
