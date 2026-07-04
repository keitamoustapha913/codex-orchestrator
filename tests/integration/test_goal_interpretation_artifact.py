from __future__ import annotations

from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _normalized(git_repo: Path, prompt_text: str = "Make app return me and prove it."):
    (git_repo / "app.py").write_text("def main():\n    return 'ok'\n", encoding="utf-8")
    prompt = git_repo / "master_prompt.md"
    prompt.write_text(prompt_text + "\n", encoding="utf-8")
    run(["git", "add", "app.py", "master_prompt.md"], git_repo)
    run(["git", "commit", "-m", "setup"], git_repo)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=prompt, invocation_argv=["cxor", "init"])
    write_workflow_identity(ctx, build_workflow_identity(ctx, master=prompt, worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001"))
    normalize_master_prompt(ctx)
    return ctx


def test_goal_interpretation_written_after_master_prompt_freeze(git_repo: Path):
    ctx = _normalized(git_repo)
    assert (ctx.paths.workflow_dir / "master_prompt_frozen.json").exists()
    assert (ctx.paths.workflow_dir / "goal_interpretation.json").exists()
    assert (ctx.paths.workflow_dir / "goal_interpretation/model_request.json").exists()
    assert (ctx.paths.workflow_dir / "goal_interpretation/model_response.raw.json").exists()


def test_goal_interpretation_references_master_prompt_hash(git_repo: Path):
    ctx = _normalized(git_repo)
    frozen = read_json(ctx.paths.workflow_dir / "master_prompt_frozen.json")
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation.json")
    assert interpretation["master_prompt_sha256"] == frozen["sha256"]


def test_goal_item_references_master_prompt_span(git_repo: Path):
    ctx = _normalized(git_repo)
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation.json")
    assert interpretation["goal_items"][0]["source_span_ids"] == ["MPS001"]


def test_goal_interpretation_records_goal_summary(git_repo: Path):
    ctx = _normalized(git_repo)
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation.json")
    assert interpretation["goal_summary"]


def test_goal_interpretation_records_ambiguity(git_repo: Path):
    ctx = _normalized(git_repo, "Make the project delightful.")
    validation = read_json(ctx.paths.workflow_dir / "goal_interpretation/validation_result.json")
    assert validation["accepted"] is False
    assert read_json(ctx.paths.workflow_dir / "provability/provability_result.json")["can_start_product_patchlets"] is False


def test_goal_interpretation_schema_validates(git_repo: Path):
    ctx = _normalized(git_repo)
    assert validate_json_file(ctx.paths.workflow_dir / "goal_interpretation.json", "goal_interpretation.schema.json") == []


def test_goal_interpretation_does_not_mark_goal_proven(git_repo: Path):
    ctx = _normalized(git_repo)
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation.json")
    assert interpretation["proof_not_claimed_here"] is True
    assert "proven" not in interpretation


def test_app_prompt_does_not_create_app_main_semantic_goal_item(git_repo: Path):
    ctx = _normalized(git_repo)
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation.json")
    assert "app.main" not in str(interpretation)
    assert "semantic_criterion_id" not in str(interpretation)


def test_unsupported_semantic_goal_creates_non_proven_interpretation(git_repo: Path):
    ctx = _normalized(git_repo, "Make the project delightful.")
    result = read_json(ctx.paths.workflow_dir / "provability/goal_not_provable_result.json")
    assert result["status"] == "SAFE_FAILURE"


def test_goal_interpretation_authoritative_artifact_is_stage_scoped(git_repo: Path):
    ctx = _normalized(git_repo)
    assert read_json(ctx.paths.workflow_dir / "goal_interpretation.json") == read_json(
        ctx.paths.workflow_dir / "goal_interpretation/goal_interpretation.json"
    )
