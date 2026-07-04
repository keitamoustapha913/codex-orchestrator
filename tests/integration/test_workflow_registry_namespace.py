from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import read_json


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def test_registry_created_for_first_workflow(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    assert (git_repo / ".codex-orchestrator" / "workflows" / "registry.json").exists()


def test_registry_records_active_workflow(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    registry = read_json(git_repo / ".codex-orchestrator" / "workflows" / "registry.json")
    identity = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")
    assert registry["active_workflow_id"] == identity["workflow_id"]


def test_new_run_creates_new_workflow_id(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    first = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")["workflow_id"]
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--new-run", "--until", "PATCHLETS_READY"], cwd=git_repo)
    second = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")["workflow_id"]
    assert second != first


def test_new_run_does_not_reuse_old_run_id(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    first = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")["run_id"]
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--new-run", "--until", "PATCHLETS_READY"], cwd=git_repo)
    second = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")["run_id"]
    assert second != first


def test_new_run_does_not_overwrite_old_operator_events(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--new-run", "--until", "PATCHLETS_READY"], cwd=git_repo)
    assert list((git_repo / ".codex-orchestrator" / "archives").glob("*/snapshot/operator_events.jsonl"))


def test_new_run_does_not_overwrite_old_prompt_index(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--new-run", "--until", "PATCHLETS_READY"], cwd=git_repo)
    assert list((git_repo / ".codex-orchestrator" / "archives").glob("*/snapshot/prompt_index.json"))


def test_current_workflow_pointer_updates(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--new-run", "--until", "PATCHLETS_READY"], cwd=git_repo)
    registry = read_json(git_repo / ".codex-orchestrator" / "workflows" / "registry.json")
    identity = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")
    assert registry["active_workflow_id"] == identity["workflow_id"]


def test_status_reports_active_workflow_id(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert "active_workflow_id" in result.stdout


def test_monitor_can_filter_by_workflow_id(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    identity = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")
    result = _run_cli(["monitor", "--repo", str(git_repo), "--workflow", identity["workflow_id"], "--json"], cwd=git_repo)
    assert result.returncode == 0


def test_prompts_can_filter_by_workflow_id(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    identity = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")
    result = _run_cli(["prompts", "--repo", str(git_repo), "--workflow", identity["workflow_id"], "--json"], cwd=git_repo)
    assert result.returncode == 0
    assert "prompt_list" in result.stdout
