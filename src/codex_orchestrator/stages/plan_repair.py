from __future__ import annotations

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext


def plan_repair(ctx: TargetRepoContext) -> dict:
    classification_path = ctx.paths.failures_dir / "classification.json"
    classification = read_json(classification_path) if classification_path.exists() else {"failures": []}
    existing = sorted(ctx.paths.repair_plans_dir.glob("RP*.json"))
    plan_id = f"RP{len(existing) + 1:04d}"
    failures = [f for f in classification.get("failures", []) if f.get("failure_id")]
    failure_ids = [f["failure_id"] for f in failures]
    primary_failure = failures[0] if failures else None
    classification_value = primary_failure.get("classification", "INSIDE_KNOWN_GRAPH") if primary_failure else "NO_FAILURES"
    why = "No classified failures available for repair planning."
    if primary_failure is not None:
        observed_failure = str(primary_failure.get("observed_failure", "")).strip()
        if observed_failure:
            why = (
                "Unauthorized diff crossed the allowed-file boundary; "
                f"recorded failure was: {observed_failure}"
            )
        else:
            why = "Unauthorized diff crossed the allowed-file boundary and requires targeted repair patchlet regeneration."
    plan = {
        "schema_version": "1.0",
        "kind": "repair_plan",
        "repair_plan_id": plan_id,
        "source_failure_ids": failure_ids,
        "classification": classification_value,
        "recommended_action": "GENERATE_REPAIR_PATCHLETS" if failure_ids else "GLOBAL_REVERIFY",
        "impacted_goal_ids": [],
        "impacted_invariant_ids": [],
        "impacted_graph_node_ids": [],
        "impacted_files": [],
        "generated_patchlet_ids": [],
        "requires_partial_rediscovery": False,
        "requires_full_rediscovery": False,
        "requires_inventory_rebuild": False,
        "requires_patchlet_regeneration": bool(failure_ids),
        "why": why,
        "acceptance_criteria": [],
        "created_at": now_iso(),
    }
    write_json(ctx.paths.repair_plans_dir / f"{plan_id}.json", plan)
    (ctx.paths.repair_plans_dir / f"{plan_id}.md").write_text(f"# {plan_id}\n\n{plan['why']}\n", encoding="utf-8")
    state = load_state(ctx)
    transition(ctx, state, "REPAIR_PLAN_READY", reason="repair plan created")
    return plan
