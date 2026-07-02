from __future__ import annotations

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import TargetRepoContext

from .build_inventory import build_inventory


def rebuild_inventory(ctx: TargetRepoContext, *, scope: str) -> dict:
    state = load_state(ctx)
    if state.stage != "INVENTORY_REBUILD_REQUIRED":
        raise StagePreconditionError(
            "rebuild-inventory",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail="wrong non-terminal state",
        )
    if scope not in {"impacted", "full"}:
        raise ValueError(f"Unsupported inventory rebuild scope: {scope}")

    graph = build_inventory(ctx)
    state = load_state(ctx)
    transition(ctx, state, "PATCHLET_REGENERATION_REQUIRED", reason=f"{scope} inventory rebuild complete")
    return {
        "scope": scope,
        "next_stage": "PATCHLET_REGENERATION_REQUIRED",
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
    }
