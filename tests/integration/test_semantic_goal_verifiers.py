from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.stages.verify_global import verify_global
from codex_orchestrator.stages.verify_group import verify_group
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path, *, app_value: str = "me", prompt_value: str = "me"):
    (git_repo / "app.py").write_text(f"def main():\n    return {app_value!r}\n", encoding="utf-8")
    prompt = git_repo / "master_prompt_semantic.md"
    prompt.write_text(f"Make app return {prompt_value} and prove it.\n", encoding="utf-8")
    run(["git", "add", "app.py", "master_prompt_semantic.md"], git_repo)
    run(["git", "commit", "-m", "semantic setup"], git_repo)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=prompt, invocation_argv=["cxor", "init"])
    write_workflow_identity(ctx, build_workflow_identity(ctx, master=prompt, worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001"))
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _scenario(ctx, payload: dict):
    path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_transaction_group_passes_when_semantic_goal_passes(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    result = verify_group(ctx, transaction_group_id="TG001")
    gate = read_json(ctx.paths.workflow_dir / "transaction_groups/TG001/gates/group_gate_result.json")
    assert result["status"] == "PASSED"
    assert gate["semantic_goal_status"] == "PASSED"


def test_transaction_group_fails_when_semantic_goal_fails(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_value="me")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    result = verify_group(ctx, transaction_group_id="TG001")
    gate = read_json(ctx.paths.workflow_dir / "transaction_groups/TG001/gates/group_gate_result.json")
    assert result["status"] == "FAILED"
    assert gate["failed_semantic_criteria"] == ["SGC001"]


def test_global_verifier_done_requires_semantic_goal_pass(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    result = verify_global(ctx)
    assert result.done is True
    assert read_json(ctx.paths.final_verification_json)["semantic_goal_status"] == "PASSED"


def test_global_verifier_refuses_done_when_semantic_goal_failed(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_value="me")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    result = verify_global(ctx)
    assert result.done is False
    assert read_json(ctx.paths.final_verification_json)["semantic_goal_status"] == "FAILED"


def test_global_verifier_refuses_done_when_semantic_goal_unproven(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    # Mark patchlet structurally accepted without running semantic checks.
    index = read_json(ctx.paths.patchlet_index)
    index["patchlets"][0]["status"] = "VERIFIED_NO_CHANGE_NEEDED"
    from codex_orchestrator.jsonio import write_json

    write_json(ctx.paths.patchlet_index, index)
    result = verify_global(ctx)
    assert result.done is False
    assert read_json(ctx.paths.final_verification_json)["semantic_goal_status"] == "BLOCKED"


def test_final_verification_includes_semantic_goal_status(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    verify_global(ctx)
    assert "semantic_goal_status" in read_json(ctx.paths.final_verification_json)


def test_final_verification_includes_failed_semantic_criterion_ids(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_value="me")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    verify_global(ctx)
    assert read_json(ctx.paths.final_verification_json)["failed_semantic_criterion_ids"] == ["SGC001"]


def test_verification_matrix_includes_semantic_goals(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    verify_global(ctx)
    matrix = read_json(ctx.paths.workflow_dir / "global_verification/verification_matrix.json")
    assert matrix["semantic_goals"][0]["criterion_id"] == "SGC001"


def test_workflow_done_event_not_emitted_when_semantic_goal_fails(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_value="me")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    verify_global(ctx)
    assert not any(event["event_type"] == "workflow_done" for event in read_operator_events(ctx.root))


def test_workflow_safe_failed_event_emitted_when_semantic_goal_fails(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_value="me")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    verify_global(ctx)
    assert any(event["event_type"] == "workflow_safe_failed" for event in read_operator_events(ctx.root))
