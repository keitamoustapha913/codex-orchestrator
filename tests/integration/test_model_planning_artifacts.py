from __future__ import annotations

from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(repo: Path):
    (repo / "module.txt").write_text("before\n", encoding="utf-8")
    (repo / "master_prompt.md").write_text("Change module behavior and prove it.\n", encoding="utf-8")
    run(["git", "add", "module.txt", "master_prompt.md"], repo)
    run(["git", "commit", "-m", "planning setup"], repo)
    ctx = resolve_target_repo(repo=repo)
    init_workflow(ctx, master=repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(
        ctx,
        build_workflow_identity(
            ctx,
            master=repo / "master_prompt.md",
            worker_mode="mock",
            use_worktree=False,
            until="DONE",
            workflow_id="WF000001",
            run_id="R0001",
        ),
    )
    return ctx


def test_goal_interpretation_model_request_written(git_repo: Path):
    ctx = _ctx(git_repo)
    normalize_master_prompt(ctx)
    request = read_json(ctx.paths.workflow_dir / "goal_interpretation/model_request.json")
    assert request["kind"] == "goal_interpretation_model_request"
    assert request["master_prompt_sha256"]


def test_goal_interpretation_raw_response_preserved(git_repo: Path):
    ctx = _ctx(git_repo)
    normalize_master_prompt(ctx)
    raw = (ctx.paths.workflow_dir / "goal_interpretation/model_response.raw.json").read_text(encoding="utf-8")
    assert read_json(ctx.paths.workflow_dir / "goal_interpretation/goal_interpretation.json") == __import__("json").loads(raw)


def test_proof_and_probe_planning_artifacts_written(git_repo: Path):
    ctx = _ctx(git_repo)
    normalize_master_prompt(ctx)
    assert (ctx.paths.workflow_dir / "proof_planning/model_request.json").exists()
    assert (ctx.paths.workflow_dir / "proof_planning/model_response.raw.json").exists()
    assert (ctx.paths.workflow_dir / "proof_planning/proof_obligations.json").exists()
    assert (ctx.paths.workflow_dir / "probe_planning/model_request.json").exists()
    assert (ctx.paths.workflow_dir / "probe_planning/model_response.raw.json").exists()
    assert (ctx.paths.workflow_dir / "probe_planning/probe_plan.json").exists()


def test_planning_model_artifacts_include_repo_agnostic_instruction(git_repo: Path):
    ctx = _ctx(git_repo)
    normalize_master_prompt(ctx)
    for rel in [
        "goal_interpretation/model_request.json",
        "proof_planning/model_request.json",
        "probe_planning/model_request.json",
    ]:
        instructions = read_json(ctx.paths.workflow_dir / rel)["instructions"]
        assert instructions["repo_agnostic"] is True
        assert instructions["language_agnostic"] is True
        assert instructions["do_not_assume_app_py"] is True
        assert instructions["do_not_assume_python"] is True
