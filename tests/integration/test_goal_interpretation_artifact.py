from __future__ import annotations

from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.goal_interpretation import build_goal_interpretation
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
    assert "app.main()" in interpretation["goal_summary"]


def test_goal_interpretation_records_ambiguity(git_repo: Path):
    ctx = _normalized(git_repo, "Make the project delightful.")
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation.json")
    assert interpretation["interpretation_status"] in {"AMBIGUOUS", "INCOMPLETE"}
    assert interpretation["ambiguities"]


def test_goal_interpretation_schema_validates(git_repo: Path):
    ctx = _normalized(git_repo)
    assert validate_json_file(ctx.paths.workflow_dir / "goal_interpretation.json", "goal_interpretation.schema.json") == []


def test_goal_interpretation_does_not_mark_goal_proven(git_repo: Path):
    ctx = _normalized(git_repo)
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation.json")
    assert interpretation["proof_not_claimed_here"] is True
    assert "proven" not in interpretation


def test_app_main_semantic_goal_creates_goal_item(git_repo: Path):
    ctx = _normalized(git_repo)
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation.json")
    assert interpretation["goal_items"][0]["desired_state"] == 'app.main() returns "me"'
    assert interpretation["goal_items"][0]["metadata"]["semantic_criterion_id"] == "SGC001"


def test_unsupported_semantic_goal_creates_non_proven_interpretation(git_repo: Path):
    ctx = _normalized(git_repo, "Make the project delightful.")
    interpretation = read_json(ctx.paths.workflow_dir / "goal_interpretation.json")
    assert interpretation["proof_not_claimed_here"] is True
    assert interpretation["interpretation_status"] != "CONCORDANT"


def test_build_goal_interpretation_is_pure_for_supplied_payload(git_repo: Path):
    ctx = _normalized(git_repo)
    frozen = read_json(ctx.paths.workflow_dir / "master_prompt_frozen.json")
    semantic = read_json(ctx.paths.workflow_dir / "semantic_goal_spec.json")
    interpretation = build_goal_interpretation(master_prompt_frozen=frozen, semantic_goal_spec=semantic)
    assert interpretation["workflow_id"] == "WF000001"
