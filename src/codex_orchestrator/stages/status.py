from __future__ import annotations

from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import TargetRepoContext


def status(ctx: TargetRepoContext) -> dict:
    state = load_state(ctx)
    return {
        "workflow_id": state.workflow_id,
        "stage": state.stage,
        "target_repo": str(ctx.root),
        "pending_patchlets": state.pending_patchlets,
        "completed_patchlets": state.completed_patchlets,
        "verified_no_change_needed": state.verified_no_change_needed,
        "failed_patchlets": state.failed_patchlets,
        "current_loop_iteration": state.current_loop_iteration,
    }
