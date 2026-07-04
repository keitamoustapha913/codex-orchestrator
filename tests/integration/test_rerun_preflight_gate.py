from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import read_json


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def test_auto_new_repo_starts_new_workflow(git_repo: Path):
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode == 0
    assert (git_repo / ".codex-orchestrator" / "workflow_identity.json").exists()
    assert read_json(git_repo / ".codex-orchestrator" / "rerun_preflight_result.json")["decision"] == "START_NEW_WORKFLOW"


def test_auto_existing_done_same_fingerprint_returns_existing_done_with_explicit_message(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode == 0
    assert "Existing workflow is already DONE" in result.stderr
    assert read_json(git_repo / ".codex-orchestrator" / "rerun_preflight_result.json")["decision"] == "RETURN_EXISTING_DONE"


def test_auto_existing_done_changed_master_prompt_refuses_without_new_run(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other_prompt.md"
    other.write_text("Make app return me and prove it.\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode != 0
    preflight = read_json(git_repo / ".codex-orchestrator" / "rerun_preflight_result.json")
    assert preflight["decision"] == "REFUSE_REQUIRES_NEW_RUN"
    assert "master_prompt_path" in preflight["changed_fields"]


def test_auto_existing_done_changed_master_prompt_content_refuses_without_new_run(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    (git_repo / "master_prompt.md").write_text("Make app return changed.\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--allow-dirty-target"], cwd=git_repo)
    assert result.returncode != 0
    assert "master_prompt_sha256" in read_json(git_repo / ".codex-orchestrator" / "rerun_preflight_result.json")["changed_fields"]


def test_auto_existing_done_dirty_target_refuses_without_policy(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    (git_repo / "app.py").write_text("dirty\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode != 0
    assert read_json(git_repo / ".codex-orchestrator" / "rerun_preflight_result.json")["decision"] == "REFUSE_DIRTY_TARGET"


def test_auto_existing_active_same_fingerprint_resumes(git_repo: Path):
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "PATCHLETS_READY", "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode == 0
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "PATCHLETS_READY", "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode == 0


def test_auto_existing_active_different_fingerprint_refuses(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "PATCHLETS_READY", "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other.md"
    other.write_text("Different.\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode != 0
    assert read_json(git_repo / ".codex-orchestrator" / "rerun_preflight_result.json")["decision"] == "REFUSE_REQUIRES_NEW_RUN"


def test_auto_existing_done_without_identity_refuses_ambiguous(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    (git_repo / ".codex-orchestrator" / "workflow_identity.json").unlink()
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode != 0
    assert read_json(git_repo / ".codex-orchestrator" / "rerun_preflight_result.json")["decision"] == "REFUSE_AMBIGUOUS_TERMINAL_WORKFLOW"


def test_rerun_preflight_result_written(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    assert (git_repo / ".codex-orchestrator" / "rerun_preflight_result.json").exists()


def test_rerun_preflight_result_records_changed_fields(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other.md"
    other.write_text("Different.\n", encoding="utf-8")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    assert read_json(git_repo / ".codex-orchestrator" / "rerun_preflight_result.json")["changed_fields"]


def test_rerun_preflight_result_includes_recommended_commands(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other.md"
    other.write_text("Different.\n", encoding="utf-8")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--until", "DONE", "--worker-mode", "mock"], cwd=git_repo)
    assert read_json(git_repo / ".codex-orchestrator" / "rerun_preflight_result.json")["recommended_commands"]
