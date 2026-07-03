from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from conftest import read_json

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.state import sha256_file
from codex_orchestrator.target_repo import resolve_target_repo


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def _ctx_with_integrated_change(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}) + "\n",
        encoding="utf-8",
    )
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    return ctx


def test_apply_results_patch_writes_final_diff_without_mutating_product_files(git_repo: Path):
    from codex_orchestrator.apply_results import apply_results

    ctx = _ctx_with_integrated_change(git_repo)
    before = sha256_file(git_repo / "app.py")

    result = apply_results(ctx, mode="patch")

    assert result["mode"] == "patch"
    assert result["mutated_working_tree"] is False
    assert ctx.paths.final_diff_path.exists()
    assert sha256_file(git_repo / "app.py") == before


def test_apply_results_branch_creates_result_branch_without_checkout(git_repo: Path):
    from codex_orchestrator.apply_results import apply_results

    ctx = _ctx_with_integrated_change(git_repo)
    current_branch = _git(git_repo, "branch", "--show-current").stdout.strip()

    result = apply_results(ctx, mode="branch")

    assert result["created_branch"].startswith("cxor/results/")
    assert _git(git_repo, "rev-parse", result["created_branch"]).stdout.strip() == result["integration_sha"]
    assert _git(git_repo, "branch", "--show-current").stdout.strip() == current_branch


def test_apply_results_working_tree_requires_clean_target(git_repo: Path):
    from codex_orchestrator.apply_results import apply_results

    ctx = _ctx_with_integrated_change(git_repo)
    (git_repo / "app.py").write_text("def main():\n    return 'dirty'\n", encoding="utf-8")

    with pytest.raises(StagePreconditionError, match="clean target"):
        apply_results(ctx, mode="working-tree")


def test_apply_results_working_tree_applies_final_diff(git_repo: Path):
    from codex_orchestrator.apply_results import apply_results

    ctx = _ctx_with_integrated_change(git_repo)

    result = apply_results(ctx, mode="working-tree")

    assert result["mutated_working_tree"] is True
    assert "# cxor mock allowed product change" in (git_repo / "app.py").read_text(encoding="utf-8")


def test_apply_results_records_apply_result_json(git_repo: Path):
    from codex_orchestrator.apply_results import apply_results

    ctx = _ctx_with_integrated_change(git_repo)

    result = apply_results(ctx, mode="patch")

    result_path = ctx.paths.integration_dir / "apply_results" / "patch_result.json"
    assert result_path.exists()
    assert read_json(result_path)["integration_sha"] == result["integration_sha"]


def test_apply_results_runs_result_schema_validation(git_repo: Path):
    from codex_orchestrator.apply_results import apply_results

    ctx = _ctx_with_integrated_change(git_repo)

    apply_results(ctx, mode="patch")

    validation_path = ctx.paths.integration_dir / "apply_results" / "patch_validation_result.json"
    validation = read_json(validation_path)
    assert validation["kind"] == "integration_artifact_validation"
    assert validation["valid"] is True


def test_apply_results_missing_integration_state_reports_structured_error(git_repo: Path):
    from codex_orchestrator.apply_results import apply_results

    ctx = resolve_target_repo(repo=git_repo)

    with pytest.raises(StagePreconditionError, match="integration_state.json"):
        apply_results(ctx, mode="patch")


def test_apply_results_patch_mode_is_default_if_project_accepts_default_mode(git_repo: Path):
    from codex_orchestrator.apply_results import apply_results

    ctx = _ctx_with_integrated_change(git_repo)

    result = apply_results(ctx)

    assert result["mode"] == "patch"
