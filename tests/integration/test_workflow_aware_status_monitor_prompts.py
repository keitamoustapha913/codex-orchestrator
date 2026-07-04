from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import read_json


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _start(git_repo: Path) -> dict:
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY"], cwd=git_repo)
    assert result.returncode == 0
    return read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")


def test_status_reports_workflow_identity(git_repo: Path):
    identity = _start(git_repo)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert identity["workflow_id"] in result.stdout


def test_status_reports_goal_fingerprint(git_repo: Path):
    identity = _start(git_repo)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert identity["goal_fingerprint"] in result.stdout


def test_status_reports_master_prompt_hash(git_repo: Path):
    identity = _start(git_repo)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert identity["master_prompt_sha256"] in result.stdout


def test_status_reports_current_target_dirty_status(git_repo: Path):
    _start(git_repo)
    (git_repo / "app.py").write_text("dirty\n", encoding="utf-8")
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert "current_target_dirty_status" in result.stdout
    assert "app.py" in result.stdout


def test_status_reports_last_rerun_preflight(git_repo: Path):
    _start(git_repo)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert "latest_rerun_preflight" in result.stdout


def test_monitor_filters_by_workflow(git_repo: Path):
    identity = _start(git_repo)
    result = _run_cli(["monitor", "--repo", str(git_repo), "--workflow", identity["workflow_id"], "--json"], cwd=git_repo)
    assert result.returncode == 0


def test_prompts_filters_by_workflow(git_repo: Path):
    identity = _start(git_repo)
    result = _run_cli(["prompts", "--repo", str(git_repo), "--workflow", identity["workflow_id"], "--json"], cwd=git_repo)
    assert result.returncode == 0
    assert "prompt_list" in result.stdout


def test_workflows_lists_active_and_archived(git_repo: Path):
    identity = _start(git_repo)
    result = _run_cli(["workflows", "--repo", str(git_repo)], cwd=git_repo)
    assert result.returncode == 0
    assert identity["workflow_id"] in result.stdout
