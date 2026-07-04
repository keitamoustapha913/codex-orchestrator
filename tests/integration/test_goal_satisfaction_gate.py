from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path, *, app_value: str = "ok", prompt_value: str = "me"):
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


def test_goal_satisfaction_gate_passes_when_semantic_runner_passes(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me", prompt_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/goal_satisfaction_gate_result.json")
    assert gate["accepted"] is True


def test_goal_satisfaction_gate_fails_when_app_returns_ok_but_goal_expects_me(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_value="me")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/goal_satisfaction_gate_result.json")
    assert gate["accepted"] is False
    assert gate["failed_criteria"] == ["SGC001"]


def test_goal_satisfaction_gate_blocks_verified_no_change_false_positive(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_value="me")
    _scenario(ctx, {"disable_semantic_autofix": True})
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"


def test_goal_satisfaction_gate_blocks_complete_false_positive(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_value="me")
    _scenario(ctx, {"status": "COMPLETE", "allowed_product_content": "def main():\n    return 'ok'\n"})
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"


def test_goal_satisfaction_gate_writes_result_json(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.runs_dir / "P0001_attempt1/gates/goal_satisfaction_gate_result.json").exists()


def test_goal_satisfaction_gate_result_schema_validates(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert validate_json_file(ctx.paths.runs_dir / "P0001_attempt1/gates/goal_satisfaction_gate_result.json", "goal_satisfaction_gate_result.schema.json") == []


def test_goal_satisfaction_gate_emits_passed_operator_event(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert any(event["event_type"] == "goal_satisfaction_gate_passed" for event in read_operator_events(ctx.root))


def test_goal_satisfaction_gate_emits_failed_operator_event(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert any(event["event_type"] == "goal_satisfaction_gate_failed" for event in read_operator_events(ctx.root))


def test_goal_satisfaction_failure_creates_failure_record(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.failures_dir / "F0001.json").exists()


def test_goal_satisfaction_failure_signature_semantic_goal_unsatisfied(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert read_json(ctx.paths.failures_dir / "F0001.json")["failure_signature"] == "semantic_goal_unsatisfied"


def test_goal_satisfaction_failure_not_classified_network_error(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert failure["failure_signature"] != "network_or_api_error"
