from __future__ import annotations

from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.proof_obligations import update_obligation_status
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path, prompt: str = "Make app return me and prove it."):
    (git_repo / "app.py").write_text("def main():\n    return 'ok'\n", encoding="utf-8")
    (git_repo / "master_prompt.md").write_text(prompt + "\n", encoding="utf-8")
    run(["git", "add", "app.py", "master_prompt.md"], git_repo)
    run(["git", "commit", "-m", "setup"], git_repo)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(ctx, build_workflow_identity(ctx, master=git_repo / "master_prompt.md", worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001"))
    normalize_master_prompt(ctx)
    return ctx


def test_proof_obligations_written_for_structured_goal(git_repo: Path):
    ctx = _ctx(git_repo)
    assert (ctx.paths.workflow_dir / "proof_obligations.json").exists()


def test_proof_obligations_reference_master_prompt_hash(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "proof_obligations.json")["master_prompt_sha256"] == read_json(ctx.paths.workflow_dir / "master_prompt_frozen.json")["sha256"]


def test_every_goal_item_has_required_obligation(git_repo: Path):
    ctx = _ctx(git_repo)
    obligations = read_json(ctx.paths.workflow_dir / "proof_obligations.json")["obligations"]
    assert obligations[0]["goal_item_ids"] == ["GI001"]
    assert obligations[0]["required"] is True


def test_obligation_references_source_span(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "proof_obligations.json")["obligations"][0]["source_span_ids"] == ["MPS001"]


def test_obligation_records_evidence_requirements(git_repo: Path):
    ctx = _ctx(git_repo)
    assert "orchestrator_rerun_or_validation" in read_json(ctx.paths.workflow_dir / "proof_obligations.json")["obligations"][0]["evidence_requirements"]


def test_obligation_status_lifecycle_unproven_to_worker_to_orchestrator(git_repo: Path):
    ctx = _ctx(git_repo)
    obligations = read_json(ctx.paths.workflow_dir / "proof_obligations.json")
    worker = update_obligation_status(obligations=obligations, obligation_id="PO001", status="PROVEN_BY_WORKER")
    orch = update_obligation_status(obligations=worker, obligation_id="PO001", status="PROVEN_BY_ORCHESTRATOR", evidence_paths=["evidence.json"])
    assert orch["obligations"][0]["status"] == "PROVEN_BY_ORCHESTRATOR"


def test_model_mediated_goal_maps_to_proof_obligation(git_repo: Path):
    ctx = _ctx(git_repo)
    obligation = read_json(ctx.paths.workflow_dir / "proof_obligations.json")["obligations"][0]
    assert obligation["proof_strategy"] == "executable_probe"
    assert obligation["goal_item_ids"] == ["GI001"]


def test_missing_obligation_blocks_provability(git_repo: Path):
    ctx = _ctx(git_repo, "Make the project delightful.")
    assert read_json(ctx.paths.workflow_dir / "provability/provability_result.json")["can_start_product_patchlets"] is False


def test_required_obligation_cannot_be_waived_without_policy(git_repo: Path):
    ctx = _ctx(git_repo)
    obligation = read_json(ctx.paths.workflow_dir / "proof_obligations.json")["obligations"][0]
    assert obligation["required"] is True
    assert obligation["status"] != "WAIVED_BY_POLICY"


def test_proof_obligations_schema_validates(git_repo: Path):
    ctx = _ctx(git_repo)
    assert validate_json_file(ctx.paths.workflow_dir / "proof_obligations.json", "proof_obligations.schema.json") == []
