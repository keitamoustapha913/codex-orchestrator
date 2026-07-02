from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.target_repo import resolve_target_repo


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", *args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _done_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    run_auto(ctx, master=git_repo / "master_prompt.md", until="DONE", worker_mode="mock", use_worktree=True, max_iterations=50)
    return ctx


def test_cli_inspect_capsule_outputs_capsule_paths(git_repo: Path, tmp_path: Path):
    _done_ctx(git_repo)

    result = _run_cli(["inspect-capsule", "--repo", str(git_repo), "--attempt", "P0001_attempt1"], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "worker_capsule.json" in result.stdout
    assert "worker_memory" in result.stdout
    assert "wrapper_gate_result.json" in result.stdout


def test_cli_validate_capsule_succeeds_for_valid_capsule(git_repo: Path, tmp_path: Path):
    _done_ctx(git_repo)

    result = _run_cli(["validate-capsule", "--repo", str(git_repo), "--attempt", "P0001_attempt1"], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "VALID" in result.stdout


def test_cli_validate_capsule_reports_missing_memory_json(git_repo: Path, tmp_path: Path):
    ctx = _done_ctx(git_repo)
    (ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "LIVE_MEMORY.json").unlink()

    result = _run_cli(["validate-capsule", "--repo", str(git_repo), "--attempt", "P0001_attempt1"], cwd=tmp_path)

    assert result.returncode == 1
    assert "LIVE_MEMORY.json" in result.stdout


def test_cli_validate_capsule_reports_missing_wrapper_gate_result(git_repo: Path, tmp_path: Path):
    ctx = _done_ctx(git_repo)
    (ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json").unlink()

    result = _run_cli(["validate-capsule", "--repo", str(git_repo), "--attempt", "P0001_attempt1"], cwd=tmp_path)

    assert result.returncode == 1
    assert "wrapper_gate_result.json" in result.stdout


def test_cli_capsule_commands_are_read_only_for_product_files(git_repo: Path, tmp_path: Path):
    _done_ctx(git_repo)
    before = (git_repo / "app.py").read_text(encoding="utf-8")

    inspect_result = _run_cli(["inspect-capsule", "--repo", str(git_repo), "--attempt", "P0001_attempt1"], cwd=tmp_path)
    validate_result = _run_cli(["validate-capsule", "--repo", str(git_repo), "--attempt", "P0001_attempt1"], cwd=tmp_path)

    assert inspect_result.returncode == 0, inspect_result.stderr
    assert validate_result.returncode == 0, validate_result.stderr
    assert (git_repo / "app.py").read_text(encoding="utf-8") == before
