from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import read_json


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def test_auto_help_includes_resume_new_run_force_new_run_flags(tmp_path: Path):
    result = _run_cli(["auto", "--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert "--resume" in result.stdout
    assert "--new-run" in result.stdout
    assert "--force-new-run" in result.stdout
    assert "--allow-dirty-target" in result.stdout
    assert "--archive-existing" in result.stdout


def test_auto_changed_prompt_exits_nonzero_without_new_run(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other_prompt.md"
    other.write_text("Make app return me and prove it.\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode != 0
    assert "different goal" in result.stderr


def test_auto_changed_prompt_error_message_shows_existing_and_requested_prompt(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock"], cwd=git_repo)
    assert str(other) in result.stderr
    assert "master_prompt_path" in result.stderr


def test_auto_changed_prompt_with_new_run_starts_new_workflow(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    old_archive_root = git_repo / ".codex-orchestrator" / "archives"
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--new-run", "--until", "PATCHLETS_READY"], cwd=git_repo)
    assert result.returncode == 0
    identity = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")
    assert identity["master_prompt_path"] == str(other.resolve())
    assert old_archive_root.exists()


def test_auto_same_prompt_existing_done_returns_existing_done_message(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode == 0
    assert "Existing workflow is already DONE" in result.stderr


def test_auto_resume_requires_existing_workflow(git_repo: Path):
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--resume"], cwd=git_repo)
    assert result.returncode != 0
    assert "Cannot resume" in result.stderr


def test_auto_resume_refuses_changed_goal(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--resume"], cwd=git_repo)
    assert result.returncode != 0
    assert "different goal" in result.stderr


def test_auto_force_new_run_archives_terminal_workflow(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--force-new-run", "--until", "PATCHLETS_READY"], cwd=git_repo)
    assert result.returncode == 0
    assert list((git_repo / ".codex-orchestrator" / "archives").glob("*"))


def test_auto_force_new_run_does_not_delete_evidence(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--force-new-run", "--until", "PATCHLETS_READY"], cwd=git_repo)
    snapshots = list((git_repo / ".codex-orchestrator" / "archives").glob("*/snapshot/operator_events.jsonl"))
    assert snapshots


def test_auto_allow_dirty_target_records_dirty_status(git_repo: Path):
    (git_repo / "app.py").write_text("dirty\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--allow-dirty-target", "--until", "PATCHLETS_READY"], cwd=git_repo)
    assert result.returncode == 0
    identity = read_json(git_repo / ".codex-orchestrator" / "workflow_identity.json")
    assert any("app.py" in line for line in identity["target_dirty_status_at_start"])


def test_auto_dirty_target_without_allow_refuses(git_repo: Path):
    (git_repo / "app.py").write_text("dirty\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode != 0
    assert "dirty" in result.stderr
