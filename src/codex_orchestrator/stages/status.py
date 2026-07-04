from __future__ import annotations

from codex_orchestrator.activity_classifier import classify_activity
from codex_orchestrator.jsonio import read_json
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.workflow_identity import read_workflow_identity
from codex_orchestrator.workflow_lifecycle import read_workflow_registry
import subprocess


def status(ctx: TargetRepoContext) -> dict:
    state = load_state(ctx)
    manifest = read_json(ctx.paths.run_manifest) if ctx.paths.run_manifest.exists() else {"runs": []}
    runs = manifest.get("runs", []) if isinstance(manifest, dict) else []
    latest_run = runs[-1] if runs else {}
    activity = classify_activity(ctx.root)
    identity = read_workflow_identity(ctx.root) or {}
    registry = read_workflow_registry(ctx.root)
    preflight_path = ctx.paths.workflow_dir / "rerun_preflight_result.json"
    latest_preflight = read_json(preflight_path) if preflight_path.exists() else None
    latest_apply_result_path = ctx.paths.workflow_dir / "apply_results" / "latest_apply_result.json"
    latest_apply_result = read_json(latest_apply_result_path) if latest_apply_result_path.exists() else None
    last_report_ingestion = None
    for run in reversed(runs):
        attempt_id = run.get("attempt_id")
        patchlet_id = run.get("patchlet_id")
        if not attempt_id:
            continue
        result_path = ctx.paths.runs_dir / attempt_id / "gates" / "report_ingestion_result.json"
        if result_path.exists():
            result = read_json(result_path)
            last_report_ingestion = {
                "patchlet_id": result.get("patchlet_id") or patchlet_id,
                "attempt_id": result.get("attempt_id") or attempt_id,
                "accepted": result.get("accepted"),
                "normalization_applied": result.get("normalization_applied"),
                "normalized_failure_signature": result.get("normalized_failure_signature"),
                "result_path": f".codex-orchestrator/runs/{attempt_id}/gates/report_ingestion_result.json",
            }
            break
    return {
        "schema_version": "1.0",
        "kind": "operator_status",
        "workflow_id": state.workflow_id,
        "active_workflow_id": registry.get("active_workflow_id") or identity.get("workflow_id") or state.workflow_id,
        "run_id": identity.get("run_id"),
        "goal_fingerprint": identity.get("goal_fingerprint"),
        "master_prompt_path": identity.get("master_prompt_path"),
        "master_prompt_sha256": identity.get("master_prompt_sha256"),
        "target_head_sha_at_start": identity.get("target_head_sha"),
        "target_tree_sha_at_start": identity.get("target_tree_sha"),
        "target_dirty_status_at_start": identity.get("target_dirty_status_at_start", []),
        "current_target_dirty_status": _current_dirty_status(ctx),
        "latest_rerun_preflight": latest_preflight,
        "latest_apply_result": latest_apply_result,
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
        "last_report_ingestion": last_report_ingestion,
    }


def _current_dirty_status(ctx: TargetRepoContext) -> list[str]:
    result = subprocess.run(["git", "-C", str(ctx.root), "status", "--porcelain=v1"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line and not line[3:].startswith((".codex-orchestrator/", ".artifacts/"))]
