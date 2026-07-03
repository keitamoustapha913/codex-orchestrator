from __future__ import annotations

from codex_orchestrator.activity_classifier import classify_activity
from codex_orchestrator.jsonio import read_json
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import TargetRepoContext


def status(ctx: TargetRepoContext) -> dict:
    state = load_state(ctx)
    manifest = read_json(ctx.paths.run_manifest) if ctx.paths.run_manifest.exists() else {"runs": []}
    runs = manifest.get("runs", []) if isinstance(manifest, dict) else []
    latest_run = runs[-1] if runs else {}
    activity = classify_activity(ctx.root)
    return {
        "schema_version": "1.0",
        "kind": "operator_status",
        "workflow_id": state.workflow_id,
        "repo": str(ctx.root),
        "stage": state.stage,
        "target_repo": str(ctx.root),
        "pending_patchlets": state.pending_patchlets,
        "completed_patchlets": state.completed_patchlets,
        "verified_no_change_needed": state.verified_no_change_needed,
        "failed_patchlets": state.failed_patchlets,
        "blocked_patchlets": state.blocked_patchlets,
        "current_patchlet_id": state.current_patchlet_id,
        "current_attempt_id": activity.get("current_attempt_id") or latest_run.get("attempt_id"),
        "current_loop_iteration": state.current_loop_iteration,
        "completed_patchlet_count": len(state.completed_patchlets) + len(state.verified_no_change_needed),
        "failed_patchlet_count": len(state.failed_patchlets),
        "pending_patchlet_count": len(state.pending_patchlets),
        "run_count": len(runs),
        "last_event": activity.get("last_event"),
        "active_prompt_path": activity.get("active_prompt_path"),
        "last_progress_path": activity.get("last_progress_path"),
        "last_progress_age_seconds": activity.get("last_progress_age_seconds"),
        "classification": activity.get("classification"),
        "next_action": activity.get("next_action"),
    }
