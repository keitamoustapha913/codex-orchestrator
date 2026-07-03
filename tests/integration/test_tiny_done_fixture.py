from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import read_json

from codex_orchestrator.apply_results import apply_results
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.integration_artifact_validator import validate_integration_artifacts


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()


def _tiny_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "tiny-target"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "app.py").write_text('def main():\n    return "not ok"\n', encoding="utf-8")
    (repo / "master_prompt.md").write_text("Make app return ok and prove it.\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _ctx_with_accepted_change(tmp_path: Path):
    repo = _tiny_repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)
    init_workflow(ctx, master=repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        '{"change_allowed_product": true, "status": "COMPLETE"}\n',
        encoding="utf-8",
    )
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    return ctx


def test_tiny_mock_done_fixture_reaches_done(tmp_path: Path):
    repo = _tiny_repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)

    state = run_auto(ctx, master=repo / "master_prompt.md", until="DONE", worker_mode="mock", use_worktree=True, max_iterations=50)

    assert state.stage == "DONE"
    assert read_json(ctx.paths.state)["stage"] == "DONE"


def test_tiny_done_fixture_writes_final_verification(tmp_path: Path):
    repo = _tiny_repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)

    run_auto(ctx, master=repo / "master_prompt.md", until="DONE", worker_mode="mock", use_worktree=True, max_iterations=50)

    final = read_json(ctx.paths.final_verification_json)
    assert final["status"] == "DONE"
    assert final["target_working_tree_clean"] is True
    assert final["integration_sha"]


def test_tiny_done_fixture_writes_valid_integration_artifacts(tmp_path: Path):
    repo = _tiny_repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)

    run_auto(ctx, master=repo / "master_prompt.md", until="DONE", worker_mode="mock", use_worktree=True, max_iterations=50)

    validation = validate_integration_artifacts(repo)
    assert validation["valid"] is True


def test_tiny_done_fixture_final_diff_exists(tmp_path: Path):
    repo = _tiny_repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)

    run_auto(ctx, master=repo / "master_prompt.md", until="DONE", worker_mode="mock", use_worktree=True, max_iterations=50)

    assert ctx.paths.final_diff_path.exists()


def test_tiny_done_fixture_target_remains_clean_until_apply_results(tmp_path: Path):
    repo = _tiny_repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)

    run_auto(ctx, master=repo / "master_prompt.md", until="DONE", worker_mode="mock", use_worktree=True, max_iterations=50)

    status = _git(repo, "status", "--porcelain")
    dirty_product = [
        line for line in status.splitlines()
        if not line[3:].startswith(".codex-orchestrator/") and not line[3:].startswith(".artifacts/")
    ]
    assert dirty_product == []


def test_tiny_done_fixture_apply_results_patch_branch_working_tree(tmp_path: Path):
    patch_ctx = _ctx_with_accepted_change(tmp_path / "patch")
    patch_result = apply_results(patch_ctx, mode="patch")

    branch_ctx = _ctx_with_accepted_change(tmp_path / "branch")
    branch_result = apply_results(branch_ctx, mode="branch")

    working_tree_ctx = _ctx_with_accepted_change(tmp_path / "working-tree")
    working_tree_result = apply_results(working_tree_ctx, mode="working-tree")

    assert patch_result["mutated_working_tree"] is False
    assert branch_result["created_branch"].startswith("cxor/results/")
    assert working_tree_result["mutated_working_tree"] is True
