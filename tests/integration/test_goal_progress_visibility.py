from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import read_json, run


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _auto(git_repo: Path, until: str = "DONE"):
    return _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--use-worktree", "--until", until, "--live-progress"], git_repo)


def test_goal_progress_json_written_after_provability(git_repo: Path):
    result = _auto(git_repo, "PATCHLETS_READY")
    assert result.returncode == 0
    assert (git_repo / ".codex-orchestrator/goal_progress.json").exists()


def test_goal_progress_updates_after_patchlet_attempt(git_repo: Path):
    _auto(git_repo)
    assert read_json(git_repo / ".codex-orchestrator/goal_progress.json")["counts"]["proven"] == 1


def test_goal_progress_updates_after_goal_coverage_gate(git_repo: Path):
    _auto(git_repo)
    assert (git_repo / ".codex-orchestrator/runs/P0001_attempt1/gates/goal_coverage_gate_result.json").exists()


def test_goal_progress_jsonl_is_append_only(git_repo: Path):
    _auto(git_repo)
    lines = (git_repo / ".codex-orchestrator/goal_progress.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2


def test_goal_progress_records_counts(git_repo: Path):
    _auto(git_repo)
    assert read_json(git_repo / ".codex-orchestrator/goal_progress.json")["counts"]["required_obligations"] == 1


def test_goal_progress_records_latest_accepted_checkpoint(git_repo: Path):
    _auto(git_repo)
    progress = read_json(git_repo / ".codex-orchestrator/goal_progress.json")
    assert progress["latest_accepted_checkpoint"] is None or "checkpoints" in progress["latest_accepted_checkpoint"]


def test_goal_progress_records_applyable_progress(git_repo: Path):
    _auto(git_repo)
    assert "applyable_progress" in read_json(git_repo / ".codex-orchestrator/goal_progress.json")


def test_status_json_includes_goal_progress_summary(git_repo: Path):
    _auto(git_repo, "PATCHLETS_READY")
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], git_repo)
    assert "goal_progress" in json.loads(result.stdout)


def test_monitor_shows_goal_progress_updated_events(git_repo: Path):
    _auto(git_repo, "PATCHLETS_READY")
    result = _run_cli(["monitor", "--repo", str(git_repo)], git_repo)
    assert "goal_progress_updated" in result.stdout


def test_live_progress_prints_goal_progress_summary(git_repo: Path):
    result = _auto(git_repo, "PATCHLETS_READY")
    assert "goal progress:" in result.stderr


def test_goal_progress_cli_human_output(git_repo: Path):
    _auto(git_repo, "PATCHLETS_READY")
    result = _run_cli(["goal-progress", "--repo", str(git_repo)], git_repo)
    assert "overall goal status" in result.stdout


def test_goal_progress_cli_json_output(git_repo: Path):
    _auto(git_repo, "PATCHLETS_READY")
    result = _run_cli(["goal-progress", "--repo", str(git_repo), "--json"], git_repo)
    assert json.loads(result.stdout)["kind"] == "goal_progress"


def test_goal_progress_cli_watch_outputs_updates(git_repo: Path):
    _auto(git_repo, "PATCHLETS_READY")
    result = _run_cli(["goal-progress", "--repo", str(git_repo), "--watch", "--max-iterations", "1"], git_repo)
    assert "overall goal status" in result.stdout
