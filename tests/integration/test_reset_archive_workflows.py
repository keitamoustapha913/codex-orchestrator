from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _complete(git_repo: Path) -> None:
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode == 0


def test_archive_command_exists(tmp_path: Path):
    result = _run_cli(["archive", "--help"], cwd=tmp_path)
    assert result.returncode == 0


def test_archive_preserves_workflow_artifacts(git_repo: Path):
    _complete(git_repo)
    result = _run_cli(["archive", "--repo", str(git_repo)], cwd=git_repo)
    assert result.returncode == 0
    assert list((git_repo / ".codex-orchestrator" / "archives").glob("*/snapshot/state.json"))


def test_archive_marks_workflow_archived(git_repo: Path):
    _complete(git_repo)
    _run_cli(["archive", "--repo", str(git_repo)], cwd=git_repo)
    registry = git_repo / ".codex-orchestrator" / "workflows" / "registry.json"
    assert '"status": "ARCHIVED"' in registry.read_text(encoding="utf-8")


def test_reset_archive_moves_or_marks_current_workflow(git_repo: Path):
    _complete(git_repo)
    result = _run_cli(["reset", "--repo", str(git_repo), "--archive"], cwd=git_repo)
    assert result.returncode == 0
    assert not (git_repo / ".codex-orchestrator" / "state.json").exists()
    assert list((git_repo / ".codex-orchestrator" / "archives").glob("*/archive_result.json"))


def test_reset_archive_allows_new_auto_after_reset(git_repo: Path):
    _complete(git_repo)
    _run_cli(["reset", "--repo", str(git_repo), "--archive"], cwd=git_repo)
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY"], cwd=git_repo)
    assert result.returncode == 0


def test_reset_hard_delete_requires_explicit_flag(git_repo: Path):
    _complete(git_repo)
    result = _run_cli(["reset", "--repo", str(git_repo)], cwd=git_repo)
    assert result.returncode != 0


def test_reset_hard_delete_refuses_dirty_product_files(git_repo: Path):
    _complete(git_repo)
    (git_repo / "app.py").write_text("dirty\n", encoding="utf-8")
    result = _run_cli(["reset", "--repo", str(git_repo), "--hard-delete-artifacts"], cwd=git_repo)
    assert result.returncode != 0


def test_workflows_lists_archived_and_active_workflows(git_repo: Path):
    _complete(git_repo)
    _run_cli(["archive", "--repo", str(git_repo)], cwd=git_repo)
    result = _run_cli(["workflows", "--repo", str(git_repo)], cwd=git_repo)
    assert result.returncode == 0
    assert "ARCHIVED" in result.stdout


def test_workflows_json_outputs_registry(git_repo: Path):
    _complete(git_repo)
    result = _run_cli(["workflows", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert result.returncode == 0
    assert '"kind": "workflow_registry"' in result.stdout


def test_archive_does_not_delete_probe_evidence_without_record(git_repo: Path):
    _complete(git_repo)
    _run_cli(["archive", "--repo", str(git_repo)], cwd=git_repo)
    assert (git_repo / ".artifacts").exists()
    assert list((git_repo / ".codex-orchestrator" / "archives").glob("*/archive_result.json"))
