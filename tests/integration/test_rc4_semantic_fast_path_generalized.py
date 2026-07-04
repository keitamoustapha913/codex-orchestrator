from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json, run

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


def _ctx(git_repo: Path, app_value: str = "ok", prompt: str = "Make app return me and prove it."):
    (git_repo / "app.py").write_text(f"def main():\n    return {app_value!r}\n", encoding="utf-8")
    (git_repo / "master_prompt.md").write_text(prompt + "\n", encoding="utf-8")
    run(["git", "add", "app.py", "master_prompt.md"], git_repo)
    run(["git", "commit", "-m", "setup"], git_repo)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(ctx, build_workflow_identity(ctx, master=git_repo / "master_prompt.md", worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001"))
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _scenario(ctx, payload: dict):
    path = ctx.paths.workflow_dir / "mock/next_patchlet_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_app_main_return_goal_creates_general_goal_interpretation(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "goal_interpretation.json")["goal_items"][0]["goal_item_id"] == "GI001"


def test_app_main_return_goal_creates_general_proof_obligation(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "proof_obligations.json")["obligations"][0]["obligation_id"] == "PO001"


def test_app_main_return_goal_creates_probe_plan(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "probe_plan.json")["probes"][0]["probe_id"] == "GP001"


def test_app_main_return_goal_updates_goal_progress(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert read_json(ctx.paths.workflow_dir / "goal_progress.json")["counts"]["proven"] == 1


def test_app_main_return_goal_satisfaction_result_passes_when_value_matches(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    verify_global(ctx)
    assert read_json(ctx.paths.workflow_dir / "global_verification/master_prompt_satisfaction_result.json")["accepted"] is True


def test_ok_vs_me_false_done_still_blocked_by_general_coverage_gate(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"


def test_ok_vs_me_false_done_master_prompt_satisfaction_fails(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    verify_global(ctx)
    assert read_json(ctx.paths.workflow_dir / "global_verification/master_prompt_satisfaction_result.json")["accepted"] is False


def test_correct_me_goal_still_reaches_done(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert verify_global(ctx).done is True


def test_unsupported_prompt_does_not_claim_master_prompt_satisfaction(git_repo: Path):
    ctx = _ctx(git_repo, prompt="Make the app delightful.")
    assert read_json(ctx.paths.workflow_dir / "provability/provability_result.json")["can_start_product_patchlets"] is False


def test_existing_semantic_goal_false_done_chain_tests_still_pass(git_repo: Path):
    test_ok_vs_me_false_done_still_blocked_by_general_coverage_gate(git_repo)
