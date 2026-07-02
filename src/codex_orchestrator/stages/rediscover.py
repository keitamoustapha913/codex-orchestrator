from __future__ import annotations

import shutil
from pathlib import Path

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.paths import relative_to_repo
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext

from .census import run_census
from .classify_evidence import classify_evidence


def _next_rediscovery_id(ctx: TargetRepoContext) -> str:
    existing = sorted((ctx.paths.workflow_dir / "rediscovery").glob("RD*.json"))
    return f"RD{len(existing) + 1:04d}"


def _latest_repair_plan(ctx: TargetRepoContext) -> dict:
    plans = sorted(
        path for path in ctx.paths.repair_plans_dir.glob("RP*.json")
        if not path.name.endswith("_application.json")
    )
    if not plans:
        raise FileNotFoundError(f"No repair plans found in {ctx.paths.repair_plans_dir}")
    return read_json(plans[-1])


def rediscover(ctx: TargetRepoContext, *, scope: str) -> dict:
    state = load_state(ctx)
    if state.stage not in {"PARTIAL_REDISCOVERY_REQUIRED", "FULL_REDISCOVERY_REQUIRED"}:
        raise StagePreconditionError(
            "rediscover",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="wrong non-terminal state",
        )
    if scope not in {"impacted", "full"}:
        raise ValueError(f"Unsupported rediscovery scope: {scope}")
    if scope == "impacted" and state.stage != "PARTIAL_REDISCOVERY_REQUIRED":
        raise StagePreconditionError(
            "rediscover",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="impacted rediscovery requires PARTIAL_REDISCOVERY_REQUIRED",
        )
    if scope == "full" and state.stage != "FULL_REDISCOVERY_REQUIRED":
        raise StagePreconditionError(
            "rediscover",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="full rediscovery requires FULL_REDISCOVERY_REQUIRED",
        )

    plan = _latest_repair_plan(ctx)
    rediscovery_id = _next_rediscovery_id(ctx)
    rediscovery_dir = ctx.paths.workflow_dir / "rediscovery"
    rediscovery_dir.mkdir(parents=True, exist_ok=True)

    run_census(ctx)
    classify_evidence(ctx)

    snapshot_dir = ctx.paths.census_dir / f"rediscovery_{rediscovery_id}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for source in [
        ctx.paths.census_repo_files,
        ctx.paths.census_git_status,
        ctx.paths.census_rg_files,
        ctx.paths.census_commands,
        ctx.paths.census_tool_availability,
    ]:
        if source.exists():
            shutil.copy2(source, snapshot_dir / source.name)

    record = {
        "schema_version": "1.0",
        "kind": "rediscovery_record",
        "rediscovery_id": rediscovery_id,
        "scope": scope,
        "source_repair_plan_id": plan["repair_plan_id"],
        "source_failure_ids": plan.get("source_failure_ids", []),
        "impacted_files": plan.get("impacted_files", []),
        "impacted_goal_ids": plan.get("impacted_goal_ids", []),
        "impacted_invariant_ids": plan.get("impacted_invariant_ids", []),
        "outputs": {
            "census_dir": relative_to_repo(ctx.root, snapshot_dir),
            "evidence_rows": relative_to_repo(ctx.root, ctx.paths.search_evidence_jsonl),
            "inventory_graph": relative_to_repo(ctx.root, ctx.paths.inventory_graph),
        },
        "next_stage": "INVENTORY_REBUILD_REQUIRED",
        "created_at": now_iso(),
    }
    write_json(rediscovery_dir / f"{rediscovery_id}.json", record)
    (rediscovery_dir / f"{rediscovery_id}.md").write_text(
        f"# {rediscovery_id}\n\nScope: {scope}\n\nRepair plan: {plan['repair_plan_id']}\n",
        encoding="utf-8",
    )
    state = load_state(ctx)
    transition(ctx, state, "INVENTORY_REBUILD_REQUIRED", reason=f"{rediscovery_id} rediscovery complete")
    return record
