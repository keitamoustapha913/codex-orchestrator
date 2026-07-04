from __future__ import annotations

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
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path):
    prompt = git_repo / "master_prompt_me.md"
    prompt.write_text("Make app return me and prove it.\n", encoding="utf-8")
    run(["git", "add", "master_prompt_me.md"], git_repo)
    run(["git", "commit", "-m", "add semantic prompt"], git_repo)
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


def test_patchlet_index_includes_semantic_criterion_id(git_repo: Path):
    patchlet = read_json(_ctx(git_repo).paths.patchlet_index)["patchlets"][0]
    assert patchlet["semantic_criteria"] == ["SGC001"]


def test_patchlet_index_includes_expected_behavior(git_repo: Path):
    behavior = read_json(_ctx(git_repo).paths.patchlet_index)["patchlets"][0]["expected_behavior"]
    assert behavior["expected_value"] == "me"


def test_patchlet_title_mentions_expected_return_value(git_repo: Path):
    assert "return 'me'" in read_json(_ctx(git_repo).paths.patchlet_index)["patchlets"][0]["title"]


def test_subprompt_includes_semantic_acceptance_criteria(git_repo: Path):
    ctx = _ctx(git_repo)
    text = (ctx.root / read_json(ctx.paths.patchlet_index)["patchlets"][0]["subprompt_path"]).read_text(encoding="utf-8")
    assert "## Semantic acceptance criteria" in text
    assert "Expected return value: 'me'" in text


def test_worker_prompt_includes_expected_return_value(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/codex_task_prompt.md").read_text(encoding="utf-8")
    assert "app.main() must return 'me'" in text


def test_worker_prompt_says_ok_does_not_satisfy_me_goal(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/codex_task_prompt.md").read_text(encoding="utf-8")
    assert "returns 'ok' does not satisfy this goal" in text


def test_worker_prompt_forbids_verified_no_change_without_semantic_pass(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert "Before reporting VERIFIED_NO_CHANGE_NEEDED" in (ctx.paths.runs_dir / "P0001_attempt1/codex_task_prompt.md").read_text(encoding="utf-8")


def test_worker_memory_writes_semantic_goal_contract(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/SEMANTIC_GOAL_CONTRACT.md").exists()


def test_task_contract_references_semantic_goal_contract(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert "SEMANTIC_GOAL_CONTRACT.md" in (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/TASK_CONTRACT.md").read_text(encoding="utf-8")


def test_live_memory_references_semantic_goal_contract(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert "SEMANTIC_GOAL_CONTRACT.md" in (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/LIVE_MEMORY.md").read_text(encoding="utf-8")


def test_write_these_files_references_semantic_goal_contract(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert "SEMANTIC_GOAL_CONTRACT.md" in (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/WRITE_THESE_FILES.md").read_text(encoding="utf-8")


def test_prompt_index_records_semantic_goal_contract_artifact(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    prompts = read_json(ctx.paths.workflow_dir / "prompt_index.json")["prompts"]
    worker = [prompt for prompt in prompts if prompt["kind"] == "patchlet_worker_prompt"][-1]
    assert any("SEMANTIC_GOAL_CONTRACT.md" in path for path in worker["artifact_paths"])
