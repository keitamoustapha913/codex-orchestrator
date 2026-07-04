from __future__ import annotations

import subprocess
import sys
import json
from pathlib import Path

from conftest import read_json
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.stages.verify_global import verify_global
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity
from codex_orchestrator.workflow_lifecycle import record_active_workflow


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _done(git_repo: Path) -> None:
    ctx = resolve_target_repo(repo=git_repo)
    state = init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    identity = write_workflow_identity(
        ctx,
        build_workflow_identity(
            ctx,
            master=git_repo / "master_prompt.md",
            worker_mode="mock",
            use_worktree=True,
            until="DONE",
            workflow_id=state.workflow_id,
        ),
    )
    record_active_workflow(ctx, identity)
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
    verify_global(ctx)


def test_apply_results_working_tree_includes_rerun_guidance(git_repo: Path):
    _done(git_repo)
    result = _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "working-tree"], cwd=git_repo)
    assert result.returncode == 0
    assert "rerun_guidance" in result.stdout


def test_apply_results_records_working_tree_mutated(git_repo: Path):
    _done(git_repo)
    _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "working-tree"], cwd=git_repo)
    latest = read_json(git_repo / ".codex-orchestrator" / "apply_results" / "latest_apply_result.json")
    assert latest["rerun_guidance"]["working_tree_mutated"] is True


def test_auto_after_apply_results_dirty_target_refuses_without_allow_dirty(git_repo: Path):
    _done(git_repo)
    _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "working-tree"], cwd=git_repo)
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock"], cwd=git_repo)
    assert result.returncode != 0
    assert "dirty" in result.stderr


def test_auto_after_committed_apply_results_can_new_run(git_repo: Path):
    _done(git_repo)
    _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "working-tree"], cwd=git_repo)
    subprocess.run(["git", "-C", str(git_repo), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-m", "apply result"], check=True, stdout=subprocess.PIPE)
    other = git_repo / "other_prompt.md"
    other.write_text("Different.\n", encoding="utf-8")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(other), "--worker-mode", "mock", "--new-run", "--until", "PATCHLETS_READY"], cwd=git_repo)
    assert result.returncode == 0


def test_status_reports_latest_apply_results_guidance(git_repo: Path):
    _done(git_repo)
    _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "working-tree"], cwd=git_repo)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert "latest_apply_result" in result.stdout
    assert "commit applied results" in result.stdout
