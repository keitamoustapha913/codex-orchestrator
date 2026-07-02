from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.state import sha256_file
from codex_orchestrator.target_repo import resolve_target_repo


def run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "codex_orchestrator", *args]
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def setup_initialized_repo(git_repo: Path) -> Path:
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return git_repo


def setup_done_repo(git_repo: Path) -> Path:
    ctx = resolve_target_repo(repo=git_repo)
    result = run_auto(
        ctx,
        master=git_repo / "master_prompt.md",
        until="DONE",
        worker_mode="mock",
        max_iterations=50,
    )
    assert result.stage == "DONE"
    return git_repo


def test_doctor_repo_reports_valid_initialized_repo(git_repo: Path, tmp_path: Path):
    repo = setup_initialized_repo(git_repo)

    result = run_cli(["doctor", "--repo", str(repo)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["target_repo"] == str(repo)
    assert payload["target_is_git_repo"] is True
    assert payload["workflow_initialized"] is True


def test_validate_state_cli_succeeds_for_initialized_repo(git_repo: Path, tmp_path: Path):
    repo = setup_initialized_repo(git_repo)

    result = run_cli(["validate-state", "--repo", str(repo)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "VALID"


def test_verify_global_cli_succeeds_after_mock_done(git_repo: Path, tmp_path: Path):
    repo = setup_done_repo(git_repo)
    app_hash_before = sha256_file(repo / "app.py")

    result = run_cli(["verify-global", "--repo", str(repo)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["done"] is True
    assert payload["artifact_path"].endswith("final_verification.json")
    assert sha256_file(repo / "app.py") == app_hash_before


def test_auto_resume_ci_only_after_done_is_read_only(git_repo: Path, tmp_path: Path):
    repo = setup_done_repo(git_repo)
    workflow = repo / ".codex-orchestrator"
    state_hash_before = sha256_file(workflow / "state.json")
    final_hash_before = sha256_file(workflow / "final_verification.json")
    patchlet_index_hash_before = sha256_file(workflow / "patchlets" / "patchlet_index.json")
    app_hash_before = sha256_file(repo / "app.py")

    result = run_cli([
        "auto",
        "--repo", str(repo),
        "--resume",
        "--until", "DONE",
        "--worker-mode", "ci_only",
        "--max-iterations", "10",
    ], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout
    assert sha256_file(workflow / "state.json") == state_hash_before
    assert sha256_file(workflow / "final_verification.json") == final_hash_before
    assert sha256_file(workflow / "patchlets" / "patchlet_index.json") == patchlet_index_hash_before
    assert sha256_file(repo / "app.py") == app_hash_before


def test_auto_resume_ci_only_before_done_reports_structured_precondition_or_non_done(git_repo: Path, tmp_path: Path):
    repo = setup_initialized_repo(git_repo)
    workflow = repo / ".codex-orchestrator"
    state_hash_before = sha256_file(workflow / "state.json")
    app_hash_before = sha256_file(repo / "app.py")

    result = run_cli([
        "auto",
        "--repo", str(repo),
        "--resume",
        "--until", "DONE",
        "--worker-mode", "ci_only",
        "--max-iterations", "10",
    ], cwd=tmp_path)

    assert result.returncode != 0
    assert "precondition" in result.stderr.lower() or "ci_only" in result.stderr.lower() or "done" in result.stderr.lower()
    assert sha256_file(workflow / "state.json") == state_hash_before
    assert sha256_file(repo / "app.py") == app_hash_before
