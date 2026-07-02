from __future__ import annotations

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext


def _action_for_classification(classification_value: str) -> tuple[str, str, dict[str, bool]]:
    if classification_value == "OUTSIDE_KNOWN_GRAPH":
        return (
            "PARTIAL_REDISCOVERY_REQUIRED",
            "PARTIAL_REDISCOVERY_REQUIRED",
            {
                "requires_partial_rediscovery": True,
                "requires_full_rediscovery": False,
                "requires_inventory_rebuild": False,
                "requires_patchlet_regeneration": False,
            },
        )
    if classification_value == "INVENTORY_CONTRADICTION":
        return (
            "INVENTORY_REBUILD_REQUIRED",
            "INVENTORY_REBUILD_REQUIRED",
            {
                "requires_partial_rediscovery": False,
                "requires_full_rediscovery": False,
                "requires_inventory_rebuild": True,
                "requires_patchlet_regeneration": False,
            },
        )
    if classification_value in {"MASTER_GOAL_CHANGED", "EXCESSIVE_IMPACTED_SCOPE"}:
        return (
            "FULL_REDISCOVERY_REQUIRED",
            "FULL_REDISCOVERY_REQUIRED",
            {
                "requires_partial_rediscovery": False,
                "requires_full_rediscovery": True,
                "requires_inventory_rebuild": False,
                "requires_patchlet_regeneration": False,
            },
        )
    if classification_value == "REPEATED_REPAIR_FAILURE":
        return (
            "ESCALATED_REPAIR_REQUIRED",
            "ORCHESTRATOR_ABORTED",
            {
                "requires_partial_rediscovery": False,
                "requires_full_rediscovery": False,
                "requires_inventory_rebuild": False,
                "requires_patchlet_regeneration": False,
            },
        )
    if classification_value == "NO_FAILURES":
        return (
            "GLOBAL_REVERIFY",
            "GLOBAL_REVERIFY_REQUIRED",
            {
                "requires_partial_rediscovery": False,
                "requires_full_rediscovery": False,
                "requires_inventory_rebuild": False,
                "requires_patchlet_regeneration": False,
            },
        )
    return (
        "GENERATE_REPAIR_PATCHLETS",
        "REPAIR_PLAN_READY",
        {
            "requires_partial_rediscovery": False,
            "requires_full_rediscovery": False,
            "requires_inventory_rebuild": False,
            "requires_patchlet_regeneration": True,
        },
    )


def plan_repair(ctx: TargetRepoContext) -> dict:
    classification_path = ctx.paths.failures_dir / "classification.json"
    classification = read_json(classification_path) if classification_path.exists() else {"failures": []}
    existing = sorted(ctx.paths.repair_plans_dir.glob("RP*.json"))
    plan_id = f"RP{len(existing) + 1:04d}"
    failures = [f for f in classification.get("failures", []) if f.get("failure_id")]
    failure_ids = [f["failure_id"] for f in failures]
    primary_failure = failures[0] if failures else None
    classification_value = primary_failure.get("classification", "INSIDE_KNOWN_GRAPH") if primary_failure else "NO_FAILURES"
    recommended_action, next_stage, requirement_flags = _action_for_classification(classification_value)
    why = "No classified failures available for repair planning."
    if primary_failure is not None:
        observed_failure = str(primary_failure.get("observed_failure", "")).strip()
        if observed_failure:
            why = f"{classification_value} requires targeted follow-up; recorded failure was: {observed_failure}"
        else:
            why = f"{classification_value} requires targeted follow-up without blind retry."
    impacted_goal_ids = primary_failure.get("goal_ids", []) if primary_failure else []
    impacted_invariant_ids = primary_failure.get("blocking_invariant_ids", []) if primary_failure else []
    impacted_graph_node_ids = primary_failure.get("graph_node_ids", []) if primary_failure else []
    impacted_files = primary_failure.get("changed_paths", []) if primary_failure else []
    if classification_value == "INSIDE_KNOWN_GRAPH":
        impacted_goal_ids = []
        impacted_invariant_ids = []
        impacted_graph_node_ids = []
        impacted_files = []
    plan = {
        "schema_version": "1.0",
        "kind": "repair_plan",
        "repair_plan_id": plan_id,
        "source_failure_ids": failure_ids,
        "classification": classification_value,
        "recommended_action": recommended_action,
        "impacted_goal_ids": impacted_goal_ids,
        "impacted_invariant_ids": impacted_invariant_ids,
        "impacted_graph_node_ids": impacted_graph_node_ids,
        "impacted_files": impacted_files,
        "generated_patchlet_ids": [],
        **requirement_flags,
        "why": why,
        "acceptance_criteria": [],
        "created_at": now_iso(),
    }
    write_json(ctx.paths.repair_plans_dir / f"{plan_id}.json", plan)
    (ctx.paths.repair_plans_dir / f"{plan_id}.md").write_text(f"# {plan_id}\n\n{plan['why']}\n", encoding="utf-8")
    state = load_state(ctx)
    transition(ctx, state, next_stage, reason="repair plan created")
    return plan
