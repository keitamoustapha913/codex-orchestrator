from __future__ import annotations

import re

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import TargetRepoContext


def _next_patchlet_id(index: dict) -> str:
    numbers = [
        int(patchlet["patchlet_id"][1:])
        for patchlet in index.get("patchlets", [])
        if isinstance(patchlet.get("patchlet_id"), str) and re.fullmatch(r"P\d{4}", patchlet["patchlet_id"])
    ]
    return f"P{(max(numbers) if numbers else 0) + 1:04d}"


def _next_transaction_group_id(index: dict) -> str:
    numbers = [
        int(patchlet["transaction_group_id"][2:])
        for patchlet in index.get("patchlets", [])
        if isinstance(patchlet.get("transaction_group_id"), str) and re.fullmatch(r"TG\d{3}", patchlet["transaction_group_id"])
    ]
    return f"TG{(max(numbers) if numbers else 0) + 1:03d}"


def _latest_repair_plan_path(ctx: TargetRepoContext):
    plans = sorted(
        path
        for path in ctx.paths.repair_plans_dir.glob("RP*.json")
        if not path.name.endswith("_application.json")
    )
    if not plans:
        raise FileNotFoundError(f"No repair plans found in {ctx.paths.repair_plans_dir}")
    return plans[-1]


def regenerate_patchlets(ctx: TargetRepoContext, *, from_repair_plan: str = "latest") -> dict:
    state = load_state(ctx)
    if state.stage == "DONE":
        return {"status": "DONE_NOOP", "repair_plan_id": None, "patchlet_ids": []}
    if state.stage == "REPAIR_PLAN_READY":
        raise StagePreconditionError(
            "regenerate-patchlets",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="missing repair application",
        )
    if state.stage not in {"PATCHLET_REGENERATION_REQUIRED", "PATCHLETS_READY"}:
        raise StagePreconditionError(
            "regenerate-patchlets",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="wrong non-terminal state",
        )

    if from_repair_plan != "latest":
        raise ValueError(f"Unsupported repair plan selector: {from_repair_plan}")

    try:
        plan_path = _latest_repair_plan_path(ctx)
    except FileNotFoundError as exc:
        raise StagePreconditionError(
            "regenerate-patchlets",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="missing repair plan",
        ) from exc
    plan = read_json(plan_path)
    repair_plan_id = plan["repair_plan_id"]
    application_path = ctx.paths.repair_plans_dir / f"{repair_plan_id}_application.json"
    if not application_path.exists():
        raise StagePreconditionError(
            "regenerate-patchlets",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="missing repair application",
        )
    index = read_json(ctx.paths.patchlet_index)

    existing = next(
        (patchlet for patchlet in index.get("patchlets", []) if patchlet.get("repair_plan_id") == repair_plan_id),
        None,
    )
    if existing is None:
        failure_id = plan["source_failure_ids"][0]
        failure = read_json(ctx.paths.failures_dir / f"{failure_id}.json")
        source_patchlet_id = failure["source_id"]
        source_patchlet = next(
            patchlet for patchlet in index.get("patchlets", [])
            if patchlet.get("patchlet_id") == source_patchlet_id
        )
        patchlet_id = _next_patchlet_id(index)
        transaction_group_id = _next_transaction_group_id(index)
        subprompt_rel = f".codex-orchestrator/subprompts/{patchlet_id[1:]}_repair.md"
        repair_patchlet = {
            "schema_version": "1.0",
            "kind": "patchlet",
            "patchlet_id": patchlet_id,
            "subprompt_path": subprompt_rel,
            "master_goal_ids": [],
            "invariant_ids": [],
            "evidence_ids": [],
            "graph_node_ids": [],
            "allowed_product_runtime_file": source_patchlet["allowed_product_runtime_file"],
            "allowed_artifact_dirs": [
                ".artifacts/probes/",
                ".codex-orchestrator/reports/",
                ".codex-orchestrator/runs/",
            ],
            "transaction_group_id": transaction_group_id,
            "depends_on": [],
            "status": "PENDING",
            "is_repair_patchlet": True,
            "repair_plan_id": repair_plan_id,
            "source_failure_ids": plan["source_failure_ids"],
        }
        index.setdefault("patchlets", []).append(repair_patchlet)
        write_json(ctx.paths.patchlet_index, index)
        subprompt = ctx.root / subprompt_rel
        subprompt.parent.mkdir(parents=True, exist_ok=True)
        subprompt.write_text(
            f"# Repair Patchlet {patchlet_id}\n\n"
            f"Repair plan: {repair_plan_id}\n"
            f"Source failure: {failure_id}\n"
            f"Allowed product/runtime file: `{source_patchlet['allowed_product_runtime_file']}`\n\n"
            "This repair patchlet addresses an unauthorized diff that crossed the allowed-file boundary.\n"
            "Do not blind retry.\n\n"
            "## ROOT-CAUSE PROBE-ONLY INVESTIGATION\n\n"
            "First prove the root cause with a direct probe before any product/runtime edit.\n",
            encoding="utf-8",
        )
        patchlet_ids = [patchlet_id]
    else:
        patchlet_ids = [existing["patchlet_id"]]

    existing_cycle = next(
        (cycle for cycle in state.repair_cycles if cycle.get("repair_plan_id") == repair_plan_id),
        None,
    )
    if existing_cycle is None:
        existing_cycle = {
            "repair_plan_id": repair_plan_id,
            "source_failure_ids": plan.get("source_failure_ids", []),
            "generated_patchlet_ids": [],
        }
        state.repair_cycles.append(existing_cycle)
    existing_cycle["generated_patchlet_ids"] = patchlet_ids
    for patchlet_id in patchlet_ids:
        if patchlet_id not in state.pending_patchlets:
            state.pending_patchlets.append(patchlet_id)
    transition(ctx, state, "PATCHLETS_READY", reason=f"{repair_plan_id} regenerated repair patchlets")
    return {"repair_plan_id": repair_plan_id, "patchlet_ids": patchlet_ids}
