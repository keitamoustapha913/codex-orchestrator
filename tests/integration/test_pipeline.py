from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.classify_failures import classify_failures
from codex_orchestrator.stages.apply_repair import apply_repair
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.plan_repair import plan_repair
from codex_orchestrator.stages.regenerate_patchlets import regenerate_patchlets
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.stages.verify_global import verify_global
from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.state import load_state, sha256_file
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.validators.schema_validator import validate_json_file
import pytest


def init_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return ctx


def setup_unauthorized_diff_failure_ctx(git_repo: Path):
    ctx = init_ctx(git_repo)
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet_index = read_json(ctx.paths.patchlet_index)
    patchlet_index["patchlets"][0]["required_allowed_product_change"] = True
    ctx.paths.patchlet_index.write_text(json.dumps(patchlet_index), encoding="utf-8")
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True)
    (mock_dir / "next_patchlet_result.json").write_text(json.dumps({
        "status": "COMPLETE",
    }), encoding="utf-8")
    result = run_next_patchlet(ctx, worker_mode="mock")
    assert result.status == "FAILED_WITH_EVIDENCE"
    return ctx


def setup_repair_plan_ready_ctx(git_repo: Path):
    ctx = setup_unauthorized_diff_failure_ctx(git_repo)
    classify_failures(ctx)
    plan_repair(ctx)
    assert load_state(ctx).stage == "REPAIR_PLAN_READY"
    return ctx


def setup_patchlet_regeneration_required_ctx(git_repo: Path):
    ctx = setup_repair_plan_ready_ctx(git_repo)
    apply_repair(ctx)
    assert load_state(ctx).stage == "PATCHLET_REGENERATION_REQUIRED"
    return ctx


def setup_repair_patchlet_ready_ctx(git_repo: Path):
    ctx = setup_patchlet_regeneration_required_ctx(git_repo)
    regenerate_patchlets(ctx, from_repair_plan="latest")
    assert load_state(ctx).stage == "PATCHLETS_READY"
    return ctx


def setup_compiled_patchlets_ctx(git_repo: Path):
    ctx = init_ctx(git_repo)
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    assert load_state(ctx).stage == "PATCHLETS_READY"
    return ctx


def setup_done_ctx(git_repo: Path):
    ctx = setup_compiled_patchlets_ctx(git_repo)
    patchlet_index = read_json(ctx.paths.patchlet_index)
    patchlet_index["patchlets"][0]["required_allowed_product_change"] = True
    ctx.paths.patchlet_index.write_text(json.dumps(patchlet_index), encoding="utf-8")
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(json.dumps({
        "status": "COMPLETE",
        "consume_after_run": True,
    }), encoding="utf-8")
    result = run_auto(ctx, until="DONE", worker_mode="mock", max_iterations=50)
    assert result.stage == "DONE"
    assert load_state(ctx).stage == "DONE"
    return ctx


def test_census_records_commands_and_outputs(git_repo: Path):
    ctx = init_ctx(git_repo)

    run_census(ctx)

    assert ctx.paths.census_repo_files.read_text(encoding="utf-8").strip().splitlines() == ["app.py", "master_prompt.md"]
    assert ctx.paths.census_git_status.exists()
    assert ctx.paths.census_commands.exists()
    commands = ctx.paths.census_commands.read_text(encoding="utf-8").strip().splitlines()
    assert any("git ls-files" in line for line in commands)
    assert read_json(ctx.paths.census_tool_availability)["git"]["available"] is True


def test_normalize_writes_goal_spec(git_repo: Path):
    ctx = init_ctx(git_repo)

    normalize_master_prompt(ctx)

    goal = read_json(ctx.paths.goal_spec)
    assert goal["kind"] == "goal_spec"
    assert goal["success_goals"][0]["goal_id"] == "G001"
    assert "root-cause" in " ".join(goal["proof_requirements"]).lower()


def test_compile_patchlets_generates_one_file_patchlet(git_repo: Path):
    ctx = init_ctx(git_repo)
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)

    compile_patchlets(ctx)

    patchlet_index = read_json(ctx.paths.patchlet_index)
    patchlet = patchlet_index["patchlets"][0]
    assert patchlet["patchlet_id"] == "P0001"
    assert patchlet["allowed_product_runtime_file"] == "app.py"
    assert (ctx.root / patchlet["subprompt_path"]).exists()
    assert "ROOT-CAUSE PROBE-ONLY INVESTIGATION" in (ctx.root / patchlet["subprompt_path"]).read_text(encoding="utf-8")


def test_mock_run_next_creates_valid_report_and_updates_state(git_repo: Path):
    ctx = init_ctx(git_repo)
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)

    result = run_next_patchlet(ctx, worker_mode="mock")

    assert result.patchlet_id == "P0001"
    assert result.status == "VERIFIED_NO_CHANGE_NEEDED"
    assert (ctx.paths.reports_dir / "P0001.json").exists()
    state = load_state(ctx)
    assert "P0001" in state.verified_no_change_needed


def test_mock_patchlet_execution_writes_durable_probe_artifacts_and_valid_report_refs(git_repo: Path):
    ctx = setup_compiled_patchlets_ctx(git_repo)

    result = run_next_patchlet(ctx, worker_mode="mock")

    probe_root = ctx.paths.probe_dir / result.patchlet_id
    run_root = probe_root / "run_001"
    report = read_json(ctx.paths.reports_dir / f"{result.patchlet_id}.json")

    assert probe_root.exists()
    assert (probe_root / "probe.py").exists()
    assert (run_root / "row_ledger.jsonl").exists()
    assert (run_root / "trace_ledger.jsonl").exists()
    assert (run_root / "before_state.json").exists()
    assert (run_root / "after_state.json").exists()
    assert (run_root / "cleanup_proof.json").exists()
    assert report["probe_artifact_refs"] == [{
        "patchlet_id": result.patchlet_id,
        "probe_root": f".artifacts/probes/{result.patchlet_id}",
        "run_id": "run_001",
    }]
    assert validate_json_file(ctx.paths.reports_dir / f"{result.patchlet_id}.json", "patchlet_report.schema.json") == []


def test_global_verifier_marks_done_after_valid_reports(git_repo: Path):
    ctx = init_ctx(git_repo)
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    run_next_patchlet(ctx, worker_mode="mock")

    result = verify_global(ctx)

    assert result.done is True
    assert read_json(ctx.paths.final_verification_json)["status"] == "DONE"
    assert load_state(ctx).stage == "DONE"


def test_auto_mock_runs_until_done(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)

    result = run_auto(ctx, master=git_repo / "master_prompt.md", until="DONE", worker_mode="mock", max_iterations=25)

    assert result.stage == "DONE"
    assert (git_repo / ".codex-orchestrator" / "final_verification.json").exists()
    assert read_json(git_repo / ".codex-orchestrator" / "final_verification.json")["status"] == "DONE"


def test_mock_unauthorized_diff_routes_to_failure_classification(git_repo: Path):
    ctx = setup_unauthorized_diff_failure_ctx(git_repo)
    assert load_state(ctx).stage == "FAILURE_CLASSIFICATION_REQUIRED"
    assert (ctx.paths.failures_dir / "F0001.json").exists()


def test_plan_repair_generates_schema_valid_repair_plan_after_unauthorized_diff_failure(git_repo: Path):
    ctx = setup_unauthorized_diff_failure_ctx(git_repo)
    failure_path = ctx.paths.failures_dir / "F0001.json"
    assert failure_path.exists()

    classification = classify_failures(ctx)

    assert classification["failures"][0]["failure_id"] == "F0001"

    repair_plan = plan_repair(ctx)

    repair_plan_path = ctx.paths.repair_plans_dir / "RP0001.json"
    assert repair_plan_path.exists()
    assert validate_json_file(failure_path, "failure_record.schema.json") == []
    assert validate_json_file(repair_plan_path, "repair_plan.schema.json") == []

    repair_plan = read_json(repair_plan_path)
    assert repair_plan["schema_version"] == "1.0"
    assert repair_plan["kind"] == "repair_plan"
    assert repair_plan["repair_plan_id"] == "RP0001"
    assert repair_plan["source_failure_ids"] == ["F0001"]
    assert repair_plan["classification"] == "INSIDE_KNOWN_GRAPH"
    assert repair_plan["recommended_action"] == "GENERATE_REPAIR_PATCHLETS"
    assert repair_plan["recommended_action"] != "BLIND_RETRY"
    assert repair_plan["impacted_goal_ids"] == []
    assert repair_plan["impacted_invariant_ids"] == []
    assert repair_plan["impacted_graph_node_ids"] == []
    assert repair_plan["impacted_files"] == []
    assert repair_plan["generated_patchlet_ids"] == []
    assert repair_plan["requires_partial_rediscovery"] is False
    assert repair_plan["requires_full_rediscovery"] is False
    assert repair_plan["requires_inventory_rebuild"] is False
    assert repair_plan["requires_patchlet_regeneration"] is True
    assert "unauthorized diff" in repair_plan["why"].lower() or "allowed" in repair_plan["why"].lower()
    assert repair_plan["acceptance_criteria"] == []
    assert load_state(ctx).stage == "REPAIR_PLAN_READY"


def test_apply_repair_records_durable_application_and_requests_patchlet_regeneration(git_repo: Path):
    ctx = setup_repair_plan_ready_ctx(git_repo)

    result = apply_repair(ctx)

    application_path = ctx.paths.repair_plans_dir / "RP0001_application.json"
    assert result == "PATCHLET_REGENERATION_REQUIRED"
    assert load_state(ctx).stage == "PATCHLET_REGENERATION_REQUIRED"
    assert application_path.exists()
    assert validate_json_file(application_path, "repair_application.schema.json") == []

    application = read_json(application_path)
    assert application["schema_version"] == "1.0"
    assert application["kind"] == "repair_application"
    assert application["repair_plan_id"] == "RP0001"
    assert application["source_failure_ids"] == ["F0001"]
    assert application["applied_action"] == "REQUEST_PATCHLET_REGENERATION"
    assert application["generated_patchlet_ids"] == []
    assert application["next_stage"] == "PATCHLET_REGENERATION_REQUIRED"
    assert application["product_runtime_files_changed"] == []
    assert application["artifact_files_changed"] == []
    assert application["blind_retry"] is False
    assert (
        "unauthorized diff" in application["why"].lower()
        or "allowed-file boundary" in application["why"].lower()
        or "repair patchlet regeneration" in application["why"].lower()
    )


def test_apply_repair_is_idempotent_for_existing_repair_application(git_repo: Path):
    ctx = setup_repair_plan_ready_ctx(git_repo)
    app_hash_before = sha256_file(ctx.root / "app.py")

    apply_repair(ctx)
    application_path = ctx.paths.repair_plans_dir / "RP0001_application.json"
    first_hash = sha256_file(application_path)
    first_application = read_json(application_path)

    apply_repair(ctx)
    second_hash = sha256_file(application_path)
    second_application = read_json(application_path)

    assert application_path.exists()
    assert list(ctx.paths.repair_plans_dir.glob("RP0001_application*.json")) == [application_path]
    assert first_hash == second_hash
    assert first_application == second_application
    assert validate_json_file(application_path, "repair_application.schema.json") == []
    assert second_application["blind_retry"] is False
    assert second_application["repair_plan_id"] == "RP0001"
    assert second_application["source_failure_ids"] == ["F0001"]
    assert load_state(ctx).stage == "PATCHLET_REGENERATION_REQUIRED"
    assert sha256_file(ctx.root / "app.py") == app_hash_before


def test_regenerate_patchlets_from_repair_plan_adds_deterministic_repair_patchlet(git_repo: Path):
    ctx = setup_patchlet_regeneration_required_ctx(git_repo)

    result = regenerate_patchlets(ctx, from_repair_plan="latest")

    patchlet_index_path = ctx.paths.patchlet_index
    assert patchlet_index_path.exists()
    assert validate_json_file(patchlet_index_path, "patchlet_index.schema.json") == []

    patchlet_index = read_json(patchlet_index_path)
    repair_patchlet = next(p for p in patchlet_index["patchlets"] if p["patchlet_id"] == "P0002")
    assert result["patchlet_ids"] == ["P0002"]
    assert repair_patchlet["kind"] == "patchlet"
    assert repair_patchlet["status"] == "PENDING"
    assert repair_patchlet["is_repair_patchlet"] is True
    assert repair_patchlet["repair_plan_id"] == "RP0001"
    assert repair_patchlet["source_failure_ids"] == ["F0001"]
    assert repair_patchlet["depends_on"] == []
    assert repair_patchlet["allowed_artifact_dirs"] == [
        ".artifacts/probes/",
        ".codex-orchestrator/reports/",
        ".codex-orchestrator/runs/",
    ]
    assert repair_patchlet["allowed_product_runtime_file"] == "app.py"
    assert validate_json_file(ctx.paths.patchlets_dir / "patchlet_index.json", "patchlet_index.schema.json") == []

    subprompt_path = ctx.root / repair_patchlet["subprompt_path"]
    assert subprompt_path.exists()
    subprompt = subprompt_path.read_text(encoding="utf-8")
    assert "Repair Patchlet" in subprompt
    assert "RP0001" in subprompt
    assert "F0001" in subprompt
    assert "unauthorized diff" in subprompt.lower()
    assert "allowed-file boundary" in subprompt
    assert "ROOT-CAUSE PROBE-ONLY INVESTIGATION" in subprompt
    assert "Do not blind retry" in subprompt
    assert load_state(ctx).stage == "PATCHLETS_READY"


def test_regenerate_patchlets_is_idempotent_for_same_repair_plan(git_repo: Path):
    ctx = setup_patchlet_regeneration_required_ctx(git_repo)

    regenerate_patchlets(ctx, from_repair_plan="latest")
    first_index = read_json(ctx.paths.patchlet_index)
    subprompt_path = ctx.root / ".codex-orchestrator/subprompts/0002_repair.md"
    first_subprompt_hash = sha256_file(subprompt_path)

    regenerate_patchlets(ctx, from_repair_plan="latest")
    second_index = read_json(ctx.paths.patchlet_index)
    second_subprompt_hash = sha256_file(subprompt_path)

    repair_patchlets = [
        patchlet
        for patchlet in second_index["patchlets"]
        if patchlet.get("is_repair_patchlet")
        and patchlet.get("repair_plan_id") == "RP0001"
        and patchlet.get("source_failure_ids") == ["F0001"]
    ]
    assert validate_json_file(ctx.paths.patchlet_index, "patchlet_index.schema.json") == []
    assert len(repair_patchlets) == 1
    assert repair_patchlets[0]["patchlet_id"] == "P0002"
    assert not any(
        patchlet.get("patchlet_id") == "P0003" and patchlet.get("repair_plan_id") == "RP0001"
        for patchlet in second_index["patchlets"]
    )
    assert first_index == second_index
    assert first_subprompt_hash == second_subprompt_hash
    assert repair_patchlets[0]["status"] == "PENDING"
    assert load_state(ctx).stage == "PATCHLETS_READY"


def test_run_generated_repair_patchlet_with_mock_worker_completes_and_preserves_boundaries(git_repo: Path):
    ctx = setup_repair_patchlet_ready_ctx(git_repo)
    (ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json").write_text("{}", encoding="utf-8")

    result = run_next_patchlet(ctx, worker_mode="mock")

    report_path = ctx.paths.reports_dir / "P0002.json"
    assert result.patchlet_id == "P0002"
    assert result.status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
    assert report_path.exists()
    assert validate_json_file(report_path, "patchlet_report.schema.json") == []

    patchlet_index = read_json(ctx.paths.patchlet_index)
    repair_patchlet = next(p for p in patchlet_index["patchlets"] if p["patchlet_id"] == "P0002")
    assert repair_patchlet["status"] in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}

    report = read_json(report_path)
    assert report["status"] in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
    assert report["changed_product_runtime_file"] in {None, "app.py"}
    assert all(
        changed.startswith(".artifacts/probes/") or changed.startswith(".codex-orchestrator/reports/")
        for changed in report["changed_artifact_files"]
    )

    run_manifest = read_json(ctx.paths.run_manifest)
    repair_run = run_manifest["runs"][-1]
    assert repair_run["patchlet_id"] == "P0002"
    assert repair_run["repair_plan_id"] == "RP0001"
    assert repair_run["source_failure_ids"] == ["F0001"]


def test_auto_recovers_from_unauthorized_diff_with_repair_patchlet_until_done(git_repo: Path):
    ctx = setup_done_ctx(git_repo)

    result = load_state(ctx)
    assert result.stage == "DONE"
    assert (ctx.paths.failures_dir / "F0001.json").exists()
    assert (ctx.paths.failures_dir / "classification.json").exists()
    assert (ctx.paths.repair_plans_dir / "RP0001.json").exists()
    assert (ctx.paths.repair_plans_dir / "RP0001_application.json").exists()
    assert (ctx.paths.reports_dir / "P0002.json").exists()
    assert ctx.paths.final_verification_json.exists()

    patchlet_index = read_json(ctx.paths.patchlet_index)
    assert any(p["patchlet_id"] == "P0002" for p in patchlet_index["patchlets"])
    repair_patchlet = next(p for p in patchlet_index["patchlets"] if p["patchlet_id"] == "P0002")
    assert (ctx.root / repair_patchlet["subprompt_path"]).exists()

    final_verification = read_json(ctx.paths.final_verification_json)
    serialized_final = json.dumps(final_verification, sort_keys=True)
    assert "F0001" in serialized_final
    assert "RP0001" in serialized_final
    assert "P0002" in serialized_final
    assert load_state(ctx).stage == "DONE"


def test_auto_resume_after_repair_done_is_idempotent(git_repo: Path):
    ctx = setup_done_ctx(git_repo)

    before_failures = sorted(path.name for path in ctx.paths.failures_dir.glob("F*.json"))
    before_repair_plans = sorted(path.name for path in ctx.paths.repair_plans_dir.glob("RP*.json"))
    before_applications = sorted(path.name for path in ctx.paths.repair_plans_dir.glob("RP*_application*.json"))
    before_patchlet_index = read_json(ctx.paths.patchlet_index)
    before_reports = sorted(path.name for path in ctx.paths.reports_dir.glob("*.json"))
    before_runs_count = len(read_json(ctx.paths.run_manifest)["runs"])
    before_final = read_json(ctx.paths.final_verification_json)
    before_state = read_json(ctx.paths.state)

    resumed = run_auto(ctx, resume=True, until="DONE", worker_mode="mock", max_iterations=10)

    after_patchlet_index = read_json(ctx.paths.patchlet_index)
    after_runs = read_json(ctx.paths.run_manifest)["runs"]
    after_final = read_json(ctx.paths.final_verification_json)
    after_state = read_json(ctx.paths.state)

    assert resumed.stage == "DONE"
    assert load_state(ctx).stage == "DONE"
    assert sorted(path.name for path in ctx.paths.failures_dir.glob("F*.json")) == before_failures
    assert "F0002.json" not in before_failures
    assert sorted(path.name for path in ctx.paths.repair_plans_dir.glob("RP*.json")) == before_repair_plans
    assert "RP0002.json" not in before_repair_plans
    assert sorted(path.name for path in ctx.paths.repair_plans_dir.glob("RP*_application*.json")) == before_applications
    assert "RP0001_application_2.json" not in before_applications
    assert after_patchlet_index == before_patchlet_index
    repair_patchlets = [
        patchlet for patchlet in after_patchlet_index["patchlets"]
        if patchlet.get("is_repair_patchlet") and patchlet.get("repair_plan_id") == "RP0001"
    ]
    assert [patchlet["patchlet_id"] for patchlet in repair_patchlets] == ["P0002"]
    assert sorted(path.name for path in ctx.paths.reports_dir.glob("*.json")) == before_reports
    assert "P0002.json" in before_reports
    assert len(after_runs) == before_runs_count
    assert not any(run.get("patchlet_id") == "P0002" for run in after_runs[before_runs_count:])
    assert after_final == before_final
    assert "F0001" in json.dumps(after_final, sort_keys=True)
    assert "RP0001" in json.dumps(after_final, sort_keys=True)
    assert "P0002" in json.dumps(after_final, sort_keys=True)
    assert after_state["stage"] == before_state["stage"] == "DONE"


def test_apply_repair_after_done_is_terminal_noop(git_repo: Path):
    ctx = setup_done_ctx(git_repo)

    state_hash_before = sha256_file(ctx.paths.state)
    application_path = ctx.paths.repair_plans_dir / "RP0001_application.json"
    application_hash_before = sha256_file(application_path)
    repair_plan_files_before = sorted(path.name for path in ctx.paths.repair_plans_dir.glob("*"))
    patchlet_index_hash_before = sha256_file(ctx.paths.patchlet_index)
    final_hash_before = sha256_file(ctx.paths.final_verification_json)
    app_hash_before = sha256_file(ctx.root / "app.py")

    result = apply_repair(ctx)

    assert load_state(ctx).stage == "DONE"
    assert result in {"DONE", "DONE_NOOP", "ALREADY_DONE_NOOP"}
    assert sha256_file(ctx.paths.state) == state_hash_before
    assert sha256_file(application_path) == application_hash_before
    assert sorted(path.name for path in ctx.paths.repair_plans_dir.glob("*")) == repair_plan_files_before
    assert "RP0002.json" not in repair_plan_files_before
    assert not list(ctx.paths.repair_plans_dir.glob("RP0001_application_*.json"))
    assert sha256_file(ctx.paths.patchlet_index) == patchlet_index_hash_before
    assert sha256_file(ctx.paths.final_verification_json) == final_hash_before
    assert sha256_file(ctx.root / "app.py") == app_hash_before


def test_regenerate_patchlets_after_done_is_terminal_noop(git_repo: Path):
    ctx = setup_done_ctx(git_repo)

    state_hash_before = sha256_file(ctx.paths.state)
    patchlet_index_hash_before = sha256_file(ctx.paths.patchlet_index)
    subprompt_hashes_before = {
        path.name: sha256_file(path)
        for path in sorted(ctx.paths.subprompts_dir.glob("*.md"))
    }
    report_hash_before = sha256_file(ctx.paths.reports_dir / "P0002.json")
    final_hash_before = sha256_file(ctx.paths.final_verification_json)
    app_hash_before = sha256_file(ctx.root / "app.py")

    result = regenerate_patchlets(ctx, from_repair_plan="latest")

    patchlet_index = read_json(ctx.paths.patchlet_index)
    repair_patchlets = [
        patchlet for patchlet in patchlet_index["patchlets"]
        if patchlet.get("is_repair_patchlet") and patchlet.get("repair_plan_id") == "RP0001"
    ]
    subprompt_hashes_after = {
        path.name: sha256_file(path)
        for path in sorted(ctx.paths.subprompts_dir.glob("*.md"))
    }

    assert load_state(ctx).stage == "DONE"
    assert result.get("status") in {"DONE", "DONE_NOOP", "ALREADY_DONE_NOOP"}
    assert sha256_file(ctx.paths.state) == state_hash_before
    assert sha256_file(ctx.paths.patchlet_index) == patchlet_index_hash_before
    assert len(repair_patchlets) == 1
    assert repair_patchlets[0]["patchlet_id"] == "P0002"
    assert not any(
        patchlet.get("patchlet_id") == "P0003" and patchlet.get("repair_plan_id") == "RP0001"
        for patchlet in patchlet_index["patchlets"]
    )
    assert subprompt_hashes_after == subprompt_hashes_before
    assert sha256_file(ctx.paths.reports_dir / "P0002.json") == report_hash_before
    assert sha256_file(ctx.paths.final_verification_json) == final_hash_before
    assert sha256_file(ctx.root / "app.py") == app_hash_before


def test_apply_repair_missing_repair_plan_reports_structured_precondition_error(git_repo: Path):
    ctx = setup_repair_plan_ready_ctx(git_repo)
    plan_path = ctx.paths.repair_plans_dir / "RP0001.json"
    state_hash_before = sha256_file(ctx.paths.state)
    app_hash_before = sha256_file(ctx.root / "app.py")
    plan_path.unlink()

    with pytest.raises(StagePreconditionError, match="precondition.*missing repair plan.*REPAIR_PLAN_READY"):
        apply_repair(ctx)

    assert load_state(ctx).stage == "REPAIR_PLAN_READY"
    assert sha256_file(ctx.paths.state) == state_hash_before
    assert sha256_file(ctx.root / "app.py") == app_hash_before
    assert not (ctx.paths.repair_plans_dir / "RP0001_application.json").exists()


def test_apply_repair_wrong_nonterminal_state_reports_structured_error(git_repo: Path):
    ctx = setup_compiled_patchlets_ctx(git_repo)
    state_hash_before = sha256_file(ctx.paths.state)

    with pytest.raises(StagePreconditionError, match="precondition.*apply-repair.*PATCHLETS_READY"):
        apply_repair(ctx)

    assert load_state(ctx).stage == "PATCHLETS_READY"
    assert sha256_file(ctx.paths.state) == state_hash_before
    assert not list(ctx.paths.repair_plans_dir.glob("RP*.json"))


def test_regenerate_patchlets_missing_repair_application_reports_structured_precondition_error(git_repo: Path):
    ctx = setup_repair_plan_ready_ctx(git_repo)
    state_hash_before = sha256_file(ctx.paths.state)
    app_hash_before = sha256_file(ctx.root / "app.py")

    with pytest.raises(StagePreconditionError, match="precondition.*missing repair application.*REPAIR_PLAN_READY"):
        regenerate_patchlets(ctx, from_repair_plan="latest")

    assert load_state(ctx).stage == "REPAIR_PLAN_READY"
    assert sha256_file(ctx.paths.state) == state_hash_before
    assert sha256_file(ctx.root / "app.py") == app_hash_before
    assert not (ctx.paths.subprompts_dir / "0002_repair.md").exists()


def test_regenerate_patchlets_wrong_nonterminal_state_reports_structured_error(git_repo: Path):
    ctx = setup_unauthorized_diff_failure_ctx(git_repo)
    state_hash_before = sha256_file(ctx.paths.state)

    with pytest.raises(StagePreconditionError, match="precondition.*regenerate-patchlets.*FAILURE_CLASSIFICATION_REQUIRED"):
        regenerate_patchlets(ctx, from_repair_plan="latest")

    assert load_state(ctx).stage == "FAILURE_CLASSIFICATION_REQUIRED"
    assert sha256_file(ctx.paths.state) == state_hash_before
    assert not ctx.paths.patchlet_index.with_name("patchlet_index.json.tmp").exists()
