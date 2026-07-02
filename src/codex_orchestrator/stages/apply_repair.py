from __future__ import annotations

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext


def apply_repair(ctx: TargetRepoContext) -> str:
    state = load_state(ctx)
    if state.stage == "DONE":
        return "DONE_NOOP"
    if state.stage not in {"REPAIR_PLAN_READY", "PATCHLET_REGENERATION_REQUIRED"}:
        raise StagePreconditionError(
            "apply-repair",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="wrong non-terminal state",
        )

    repair_plans = sorted(
        path
        for path in ctx.paths.repair_plans_dir.glob("RP*.json")
        if not path.name.endswith("_application.json")
    )
    if not repair_plans:
        raise StagePreconditionError(
            "apply-repair",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="missing repair plan",
        )
    latest_plan = read_json(repair_plans[-1])
    repair_plan_id = latest_plan["repair_plan_id"]
    application_path = ctx.paths.repair_plans_dir / f"{repair_plan_id}_application.json"
    if state.stage == "PATCHLET_REGENERATION_REQUIRED" and application_path.exists():
        return "PATCHLET_REGENERATION_REQUIRED"
    application = {
        "schema_version": "1.0",
        "kind": "repair_application",
        "repair_plan_id": repair_plan_id,
        "source_failure_ids": latest_plan.get("source_failure_ids", []),
        "applied_action": "REQUEST_PATCHLET_REGENERATION",
        "generated_patchlet_ids": [],
        "next_stage": "PATCHLET_REGENERATION_REQUIRED",
        "product_runtime_files_changed": [],
        "artifact_files_changed": [],
        "blind_retry": False,
        "why": (
            "Unauthorized diff crossed the allowed-file boundary; "
            "repair patchlet regeneration is required instead of blind retry."
        ),
        "created_at": now_iso(),
    }
    write_json(application_path, application)
    existing_cycle = next(
        (cycle for cycle in state.repair_cycles if cycle.get("repair_plan_id") == repair_plan_id),
        None,
    )
    if existing_cycle is None:
        state.repair_cycles.append({
            "repair_plan_id": repair_plan_id,
            "source_failure_ids": latest_plan.get("source_failure_ids", []),
            "application_artifact": f".codex-orchestrator/repair_plans/{repair_plan_id}_application.json",
            "generated_patchlet_ids": [],
        })
    transition(
        ctx,
        state,
        "PATCHLET_REGENERATION_REQUIRED",
        reason=f"{repair_plan_id} requests repair patchlet regeneration",
    )
    return "PATCHLET_REGENERATION_REQUIRED"
