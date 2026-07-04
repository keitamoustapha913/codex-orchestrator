from __future__ import annotations

from pathlib import Path

import pytest

from conftest import read_json, run

from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(repo: Path, prompt: str):
    (repo / "service.txt").write_text("ready\n", encoding="utf-8")
    (repo / "master_prompt.md").write_text(prompt + "\n", encoding="utf-8")
    run(["git", "add", "service.txt", "master_prompt.md"], repo)
    run(["git", "commit", "-m", "setup"], repo)
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


def test_pipeline_prompt_does_not_create_app_main_semantic_spec(git_repo: Path):
    ctx = _ctx(git_repo, "Make the app pipeline return ok through the entrypoint and prove it.")
    normalize_master_prompt(ctx)
    assert not (ctx.paths.workflow_dir / "semantic_goal_spec.json").exists()
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation/goal_interpretation.json")
    assert "app.main" not in str(interpretation)
    assert interpretation["proof_not_claimed_here"] is True


def test_app_prompt_does_not_use_regex_fast_path(git_repo: Path):
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    normalize_master_prompt(ctx)
    request = read_json(ctx.paths.workflow_dir / "goal_interpretation/model_request.json")
    assert request["instructions"]["do_not_assume_app_py"] is True
    assert request["instructions"]["do_not_assume_python"] is True
    assert not (ctx.paths.workflow_dir / "semantic_goal_spec.json").exists()


def test_missing_model_goal_interpretation_safe_fails_before_workers(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CXOR_PLANNING_MODEL_STUB", raising=False)
    monkeypatch.delenv("CXOR_PLANNING_MODEL_RESPONSES_DIR", raising=False)
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    normalize_master_prompt(ctx)
    assert not (ctx.paths.workflow_dir / "goal_interpretation/goal_interpretation.json").exists()
    provability = read_json(ctx.paths.workflow_dir / "provability/provability_result.json")
    assert provability["can_start_product_patchlets"] is False
    assert not list(ctx.paths.runs_dir.glob("*"))


def test_invalid_model_goal_interpretation_safe_fails_before_workers(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    responses = tmp_path / "responses"
    responses.mkdir()
    (responses / "goal_interpretation.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("CXOR_PLANNING_MODEL_RESPONSES_DIR", str(responses))
    monkeypatch.delenv("CXOR_PLANNING_MODEL_STUB", raising=False)
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    normalize_master_prompt(ctx)
    assert (ctx.paths.workflow_dir / "goal_interpretation/model_response.raw.json").read_text(encoding="utf-8") == "{not json"
    assert not (ctx.paths.workflow_dir / "goal_interpretation/goal_interpretation.json").exists()
    assert not list(ctx.paths.runs_dir.glob("*"))


def test_no_product_patchlets_when_goal_interpretation_missing(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CXOR_PLANNING_MODEL_STUB", raising=False)
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    normalize_master_prompt(ctx)
    assert compile_patchlets(ctx)["patchlets"] == []
    assert not list(ctx.paths.runs_dir.glob("*"))
