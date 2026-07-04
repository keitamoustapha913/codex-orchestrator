from __future__ import annotations

from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path, prompt_name: str = "master_prompt.md"):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / prompt_name, invocation_argv=["cxor", "init"])
    identity = build_workflow_identity(ctx, master=git_repo / prompt_name, worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001")
    write_workflow_identity(ctx, identity)
    normalize_master_prompt(ctx)
    return ctx


def test_init_writes_semantic_goal_spec_for_main_return_prompt(git_repo: Path):
    ctx = _ctx(git_repo)
    spec = read_json(ctx.paths.workflow_dir / "semantic_goal_spec.json")
    assert spec["semantic_mode"] == "structured"
    assert spec["criteria"][0]["expected_value"] == "ok"


def test_init_records_semantic_goal_summary_in_goal_spec(git_repo: Path):
    ctx = _ctx(git_repo)
    goal = read_json(ctx.paths.goal_spec)
    assert goal["semantic_goal_spec_path"] == ".codex-orchestrator/semantic_goal_spec.json"
    assert goal["semantic_criteria_count"] == 1


def test_workflow_identity_links_semantic_goal_spec(git_repo: Path):
    ctx = _ctx(git_repo)
    identity = read_json(ctx.paths.workflow_dir / "workflow_identity.json")
    assert identity["semantic_goal_spec_path"] == ".codex-orchestrator/semantic_goal_spec.json"
    assert identity["semantic_mode"] == "structured"


def test_prompt_index_master_prompt_links_semantic_goal_spec(git_repo: Path):
    ctx = _ctx(git_repo)
    prompts = read_json(ctx.paths.workflow_dir / "prompt_index.json")["prompts"]
    master = [prompt for prompt in prompts if prompt["kind"] == "master_prompt"][-1]
    assert master["semantic_goal_spec_path"] == ".codex-orchestrator/semantic_goal_spec.json"


def test_semantic_goal_fingerprint_is_stable(git_repo: Path):
    first = read_json(_ctx(git_repo).paths.workflow_dir / "semantic_goal_spec.json")["semantic_goal_fingerprint"]
    second = read_json(_ctx(git_repo).paths.workflow_dir / "semantic_goal_spec.json")["semantic_goal_fingerprint"]
    assert second == first


def test_semantic_goal_fingerprint_changes_when_expected_value_changes(git_repo: Path):
    first = read_json(_ctx(git_repo).paths.workflow_dir / "semantic_goal_spec.json")["semantic_goal_fingerprint"]
    other = git_repo / "master_prompt_me.md"
    other.write_text("Make app return me and prove it.\n", encoding="utf-8")
    ctx = _ctx(git_repo, "master_prompt_me.md")
    second = read_json(ctx.paths.workflow_dir / "semantic_goal_spec.json")["semantic_goal_fingerprint"]
    assert second != first


def test_unsupported_prompt_writes_unsupported_semantic_goal_spec(git_repo: Path):
    other = git_repo / "unsupported.md"
    other.write_text("Make the app delightful.\n", encoding="utf-8")
    ctx = _ctx(git_repo, "unsupported.md")
    spec = read_json(ctx.paths.workflow_dir / "semantic_goal_spec.json")
    assert spec["semantic_mode"] == "unsupported"
    assert spec["semantic_status"] == "UNSUPPORTED"


def test_existing_goal_spec_consumers_still_work(git_repo: Path):
    goal = normalize_master_prompt(_ctx(git_repo))
    assert goal["success_goals"][0]["goal_id"] == "G001"
