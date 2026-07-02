from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.classify_failures import classify_failures
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.plan_repair import plan_repair
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return ctx


def _write_failure(ctx, *, failure_id: str = "F0001", suspected_scope: str, source: str = "MANUAL_TEST", observed_failure: str = "failure observed", extra: dict | None = None):
    record = {
        "schema_version": "1.0",
        "kind": "failure_record",
        "failure_id": failure_id,
        "source": source,
        "source_id": "manual-source",
        "observed_failure": observed_failure,
        "blocking_invariant_ids": ["I001"],
        "evidence_ids": ["E001"],
        "graph_node_ids": ["N001"],
        "changed_paths": ["app.py"],
        "suspected_scope": suspected_scope,
        "required_next_step": "classify",
    }
    if extra:
        record.update(extra)
    ctx.paths.failures_dir.mkdir(parents=True, exist_ok=True)
    (ctx.paths.failures_dir / f"{failure_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def test_plan_repair_inside_known_graph_generates_repair_patchlet_action(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_failure(ctx, suspected_scope="inside_known_graph")

    classify_failures(ctx)
    plan = plan_repair(ctx)

    assert plan["classification"] == "INSIDE_KNOWN_GRAPH"
    assert plan["recommended_action"] == "GENERATE_REPAIR_PATCHLETS"
    assert plan["requires_patchlet_regeneration"] is True
    assert load_state(ctx).stage == "REPAIR_PLAN_READY"


def test_plan_repair_outside_known_graph_requests_partial_rediscovery(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_failure(ctx, suspected_scope="outside_known_graph")

    classify_failures(ctx)
    plan = plan_repair(ctx)

    assert plan["classification"] == "OUTSIDE_KNOWN_GRAPH"
    assert plan["recommended_action"] == "PARTIAL_REDISCOVERY_REQUIRED"
    assert plan["requires_partial_rediscovery"] is True
    assert load_state(ctx).stage == "PARTIAL_REDISCOVERY_REQUIRED"


def test_plan_repair_inventory_contradiction_requests_inventory_rebuild(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_failure(ctx, suspected_scope="inventory_contradiction")

    classify_failures(ctx)
    plan = plan_repair(ctx)

    assert plan["classification"] == "INVENTORY_CONTRADICTION"
    assert plan["recommended_action"] == "INVENTORY_REBUILD_REQUIRED"
    assert plan["requires_inventory_rebuild"] is True
    assert load_state(ctx).stage == "INVENTORY_REBUILD_REQUIRED"


def test_plan_repair_repeated_repair_failure_requests_escalated_repair_or_abort(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_failure(
        ctx,
        suspected_scope="repeated_repair_failure",
        extra={"repeat_count": 2, "repair_plan_id": "RP0001"},
    )

    classify_failures(ctx)
    plan = plan_repair(ctx)

    assert plan["classification"] == "REPEATED_REPAIR_FAILURE"
    assert plan["recommended_action"] in {"ESCALATED_REPAIR_REQUIRED", "ORCHESTRATOR_ABORTED"}
    assert load_state(ctx).stage == "ORCHESTRATOR_ABORTED"


def test_plan_repair_master_goal_changed_requests_full_rediscovery(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_failure(ctx, suspected_scope="master_goal_changed", source="MASTER_PROMPT_CHANGED")

    classify_failures(ctx)
    plan = plan_repair(ctx)

    assert plan["classification"] == "MASTER_GOAL_CHANGED"
    assert plan["recommended_action"] == "FULL_REDISCOVERY_REQUIRED"
    assert plan["requires_full_rediscovery"] is True
    assert load_state(ctx).stage == "FULL_REDISCOVERY_REQUIRED"


def test_plan_repair_excessive_impacted_scope_requests_full_rediscovery(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_failure(ctx, suspected_scope="excessive_impacted_scope")

    classify_failures(ctx)
    plan = plan_repair(ctx)

    assert plan["classification"] == "EXCESSIVE_IMPACTED_SCOPE"
    assert plan["recommended_action"] == "FULL_REDISCOVERY_REQUIRED"
    assert plan["requires_full_rediscovery"] is True
    assert load_state(ctx).stage == "FULL_REDISCOVERY_REQUIRED"


def test_same_prompt_retry_is_not_allowed_without_infrastructure_failure_evidence(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_failure(ctx, suspected_scope="inside_known_graph")

    classify_failures(ctx)
    plan = plan_repair(ctx)

    assert plan["recommended_action"] != "SAME_PROMPT_RETRY"
    assert "retry" not in plan["why"].lower() or "no blind retry" in plan["why"].lower()


def test_repair_plan_schema_rejects_unknown_classification(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_failure(ctx, suspected_scope="inside_known_graph")

    classify_failures(ctx)
    plan_repair(ctx)
    plan_path = ctx.paths.repair_plans_dir / "RP0001.json"
    plan = read_json(plan_path)
    plan["classification"] = "UNKNOWN_CLASSIFICATION"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert validate_json_file(plan_path, "repair_plan.schema.json") != []
