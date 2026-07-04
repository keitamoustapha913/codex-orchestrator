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
from codex_orchestrator.stages.status import status
from codex_orchestrator.stages.verify_global import verify_global
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path, *, app_value: str = "ok", prompt_text: str = "Make app return me and prove it."):
    (git_repo / "app.py").write_text(f"def main():\n    return {app_value!r}\n", encoding="utf-8")
    prompt = git_repo / "master_prompt_semantic.md"
    prompt.write_text(prompt_text + "\n", encoding="utf-8")
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


def test_false_verified_no_change_for_me_goal_is_blocked(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"


def test_false_verified_no_change_creates_semantic_goal_unsatisfied_failure(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert read_json(ctx.paths.failures_dir / "F0001.json")["failure_signature"] == "semantic_goal_unsatisfied"


def test_false_verified_no_change_does_not_emit_workflow_done(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    verify_global(ctx)
    assert not any(event["event_type"] == "workflow_done" for event in read_operator_events(ctx.root))


def test_false_verified_no_change_final_verification_not_done(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"disable_semantic_autofix": True})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert verify_global(ctx).done is False


def test_correct_no_change_needed_for_me_goal_reaches_done(git_repo: Path):
    ctx = _ctx(git_repo, app_value="me")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert verify_global(ctx).done is True


def test_correct_complete_edit_for_me_goal_reaches_done(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"status": "COMPLETE", "allowed_product_content": "def main():\n    return 'me'\n"})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert verify_global(ctx).done is True


def test_correct_complete_edit_final_diff_contains_ok_to_me(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok")
    _scenario(ctx, {"status": "COMPLETE", "allowed_product_content": "def main():\n    return 'me'\n"})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    verify_global(ctx)
    diff = ctx.paths.final_diff_path.read_text(encoding="utf-8")
    assert "-    return 'ok'" in diff
    assert "+    return 'me'" in diff


def test_unsupported_prompt_records_unsupported_semantic_goal(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_text="Make the app delightful.")
    spec = read_json(ctx.paths.workflow_dir / "semantic_goal_spec.json")
    assert spec["semantic_mode"] == "unsupported"


def test_unsupported_prompt_status_does_not_claim_semantic_pass(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_text="Make the app delightful.")
    assert status(ctx)["semantic_goal"]["status"] == "UNSUPPORTED"


def test_regression_ok_goal_still_passes_when_app_returns_ok(git_repo: Path):
    ctx = _ctx(git_repo, app_value="ok", prompt_text="Make app return ok and prove it.")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert verify_global(ctx).done is True
