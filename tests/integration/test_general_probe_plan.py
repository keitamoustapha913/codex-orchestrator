from __future__ import annotations

from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.probe_plan import validate_probe_plan_for_required_obligations
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path):
    (git_repo / "app.py").write_text("def main():\n    return 'ok'\n", encoding="utf-8")
    (git_repo / "master_prompt.md").write_text("Make app return me and prove it.\n", encoding="utf-8")
    run(["git", "add", "app.py", "master_prompt.md"], git_repo)
    run(["git", "commit", "-m", "setup"], git_repo)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(ctx, build_workflow_identity(ctx, master=git_repo / "master_prompt.md", worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001"))
    normalize_master_prompt(ctx)
    return ctx


def test_probe_plan_written_for_required_obligation(git_repo: Path):
    ctx = _ctx(git_repo)
    assert (ctx.paths.workflow_dir / "probe_plan.json").exists()


def test_probe_plan_references_master_prompt_hash(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "probe_plan.json")["master_prompt_sha256"] == read_json(ctx.paths.workflow_dir / "master_prompt_frozen.json")["sha256"]


def test_probe_plan_references_obligation_ids(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "probe_plan.json")["probes"][0]["obligation_ids"] == ["PO001"]


def test_probe_plan_requires_rerunnable_by_orchestrator_for_required_goal(git_repo: Path):
    ctx = _ctx(git_repo)
    obligations = read_json(ctx.paths.workflow_dir / "proof_obligations.json")
    plan = read_json(ctx.paths.workflow_dir / "probe_plan.json")
    plan["probes"][0]["rerunnable_by_orchestrator"] = False
    assert validate_probe_plan_for_required_obligations(proof_obligations=obligations, probe_plan=plan)["accepted"] is False


def test_probe_plan_records_side_effect_policy(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "probe_plan.json")["probes"][0]["side_effect_policy"] == "no_product_mutation"


def test_probe_plan_records_expected_outputs(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "probe_plan.json")["probes"][0]["expected_outputs"][0]["expected"] == "me"


def test_worker_proposed_probe_is_not_enough_to_prove_obligation(git_repo: Path):
    ctx = _ctx(git_repo)
    obligations = read_json(ctx.paths.workflow_dir / "proof_obligations.json")
    plan = read_json(ctx.paths.workflow_dir / "probe_plan.json")
    plan["probes"][0]["owner"] = "worker_proposed"
    plan["probes"][0]["rerunnable_by_orchestrator"] = False
    assert validate_probe_plan_for_required_obligations(proof_obligations=obligations, probe_plan=plan)["accepted"] is False


def test_orchestrator_generated_probe_can_cover_required_obligation(git_repo: Path):
    ctx = _ctx(git_repo)
    assert read_json(ctx.paths.workflow_dir / "probe_plan.json")["probes"][0]["owner"] == "orchestrator_generated"


def test_invalid_probe_plan_blocks_goal_coverage(git_repo: Path):
    ctx = _ctx(git_repo)
    obligations = read_json(ctx.paths.workflow_dir / "proof_obligations.json")
    plan = {"probes": []}
    assert validate_probe_plan_for_required_obligations(proof_obligations=obligations, probe_plan=plan)["missing_obligation_ids"] == ["PO001"]


def test_probe_plan_schema_validates(git_repo: Path):
    ctx = _ctx(git_repo)
    assert validate_json_file(ctx.paths.workflow_dir / "probe_plan.json", "probe_plan.schema.json") == []
