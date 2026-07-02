from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.stages.verify_global import verify_global
from codex_orchestrator.stages.verify_group import verify_all_groups
from codex_orchestrator.target_repo import resolve_target_repo


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _seed_repair_plan(ctx, *, repair_plan_id: str = "RP0001", source_failure_id: str = "F0001") -> None:
    ctx.paths.repair_plans_dir.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema_version": "1.0",
        "kind": "repair_plan",
        "repair_plan_id": repair_plan_id,
        "source_failure_ids": [source_failure_id],
        "classification": "INSIDE_KNOWN_GRAPH",
        "recommended_action": "GLOBAL_REVERIFY",
        "impacted_goal_ids": ["G001"],
        "impacted_invariant_ids": ["I001"],
        "impacted_graph_node_ids": ["N001"],
        "impacted_files": [],
        "generated_patchlet_ids": ["P0001"],
        "requires_partial_rediscovery": False,
        "requires_full_rediscovery": False,
        "requires_inventory_rebuild": False,
        "requires_patchlet_regeneration": False,
        "why": "seeded for matrix coverage",
        "acceptance_criteria": [],
    }
    application = {
        "schema_version": "1.0",
        "kind": "repair_application",
        "repair_plan_id": repair_plan_id,
        "source_failure_ids": [source_failure_id],
        "applied_action": "REQUEST_PATCHLET_REGENERATION",
        "generated_patchlet_ids": ["P0001"],
        "next_stage": "PATCHLET_REGENERATION_REQUIRED",
        "product_runtime_files_changed": [],
        "artifact_files_changed": [],
        "blind_retry": False,
        "why": "seeded for matrix coverage",
    }
    (ctx.paths.repair_plans_dir / f"{repair_plan_id}.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ctx.paths.repair_plans_dir / f"{repair_plan_id}_application.json").write_text(json.dumps(application, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_verify_global_writes_verification_matrix_before_final_verification(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)

    verify_global(ctx)

    final = read_json(ctx.paths.final_verification_json)
    assert Path(final["verification_matrix"]).exists()


def test_verification_matrix_links_goals_invariants_groups_patchlets_and_failures(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)

    verify_global(ctx)
    matrix = read_json(ctx.paths.workflow_dir / "global_verification" / "verification_matrix.json")

    assert matrix["goals"][0]["goal_id"] == "G001"
    assert matrix["invariants"][0]["invariant_id"] == "I001"
    assert matrix["transaction_groups"][0]["transaction_group_id"] == "TG001"
    assert matrix["patchlets"][0]["patchlet_id"] == "P0001"
    assert matrix["failures"] == []


def test_verification_matrix_links_repair_plans(git_repo: Path):
    ctx = _ctx(git_repo)
    _seed_repair_plan(ctx)

    verify_global(ctx)
    matrix = read_json(ctx.paths.workflow_dir / "global_verification" / "verification_matrix.json")

    assert matrix["repair_plans"][0]["repair_plan_id"] == "RP0001"
    assert matrix["repair_plans"][0]["application_exists"] is True
    assert matrix["repair_plans"][0]["next_stage"] == "PATCHLET_REGENERATION_REQUIRED"


def test_global_gate_result_blocks_done_when_matrix_has_unresolved_failures(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)
    failure = {
        "schema_version": "1.0",
        "kind": "failure_record",
        "failure_id": "F0001",
        "source": "MANUAL_TEST",
        "source_id": "manual",
        "observed_failure": "unresolved failure",
        "blocking_invariant_ids": ["I001"],
        "evidence_ids": [],
        "graph_node_ids": [],
        "changed_paths": [],
        "suspected_scope": "inside_known_graph",
        "required_next_step": "classify",
    }
    ctx.paths.failures_dir.mkdir(parents=True, exist_ok=True)
    (ctx.paths.failures_dir / "F0001.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verify_global(ctx)
    gate = read_json(ctx.paths.workflow_dir / "global_verification" / "gates" / "global_gate_result.json")

    assert gate["accepted"] is False
    assert "F0001" in gate["reasons"]


def test_global_gate_result_blocks_done_when_patchlet_wrapper_gate_failed(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)
    gate_path = ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json"
    gate = read_json(gate_path)
    gate["accepted"] = False
    gate_path.write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_global(ctx)
    global_gate = read_json(ctx.paths.workflow_dir / "global_verification" / "gates" / "global_gate_result.json")

    assert result.done is False
    assert global_gate["accepted"] is False


def test_final_verification_is_conclusion_over_verification_matrix(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)

    verify_global(ctx)
    final = read_json(ctx.paths.final_verification_json)

    assert final["status"] == "DONE"
    assert final["verification_matrix"].endswith("verification_matrix.json")
    assert final["global_gate_result"].endswith("global_gate_result.json")


def test_verify_global_is_read_only_for_product_files(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)
    before = (git_repo / "app.py").read_text(encoding="utf-8")

    verify_global(ctx)

    assert (git_repo / "app.py").read_text(encoding="utf-8") == before
