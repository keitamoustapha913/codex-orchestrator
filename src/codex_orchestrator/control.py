from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext


def request_stop(ctx: TargetRepoContext, *, mode: str = "after_current_attempt") -> dict[str, Any]:
    if mode not in {"after_current_attempt", "now"}:
        raise ValueError(f"unsupported stop mode: {mode}")
    path = ctx.paths.workflow_dir / "control" / "stop_requested.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "kind": "stop_requested",
        "created_at": now_iso(),
        "requested_mode": mode,
        "reason": "operator_requested",
        "requested_by": "operator",
    }
    write_json(path, payload)
    append_operator_event(
        ctx.root,
        event_type="stop_requested",
        severity="warning",
        stage="CONTROL",
        summary=f"Stop requested mode={mode}.",
        artifact_paths=[".codex-orchestrator/control/stop_requested.json"],
        details=payload,
    )
    return payload


def stop_requested(ctx: TargetRepoContext) -> dict[str, Any] | None:
    path = ctx.paths.workflow_dir / "control" / "stop_requested.json"
    return read_json(path) if path.exists() else None


def honor_stop_if_requested(ctx: TargetRepoContext, *, stop_stage: str) -> bool:
    request = stop_requested(ctx)
    if not request:
        return False
    write_stop_result(ctx, stop_stage=stop_stage)
    state = load_state(ctx)
    transition(ctx, state, "STOPPED", reason="operator stop requested")
    return True


def write_stop_result(ctx: TargetRepoContext, *, stop_stage: str) -> dict[str, Any]:
    latest_checkpoint = _latest_checkpoint(ctx)
    state = load_state(ctx)
    accepted_patchlet_ids = _accepted_patchlet_ids(ctx)
    latest_accepted_patchlet_id = _checkpoint_patchlet_id(latest_checkpoint)
    latest_accepted_attempt_id = _latest_accepted_attempt_id(ctx, latest_accepted_patchlet_id)
    current_patchlet_id = state.current_patchlet_id
    current_attempt_id = (
        f"{current_patchlet_id}_attempt{state.attempts[current_patchlet_id]}"
        if current_patchlet_id and state.attempts.get(current_patchlet_id)
        else None
    )
    payload = {
        "schema_version": "1.0",
        "kind": "stop_result",
        "stopped": True,
        "stopped_at": now_iso(),
        "stop_stage": stop_stage,
        "stop_mode": stop_requested(ctx).get("requested_mode", "after_current_attempt") if stop_requested(ctx) else "after_current_attempt",
        "honored": True,
        "honored_at_safe_point": True,
        "stopped_after_patchlet_id": current_patchlet_id,
        "stopped_after_attempt_id": current_attempt_id,
        "latest_accepted_integration_ref": _integration_ref(ctx),
        "latest_accepted_checkpoint_ref": _integration_ref(ctx),
        "latest_accepted_checkpoint": latest_checkpoint,
        "latest_accepted_patchlet_id": latest_accepted_patchlet_id,
        "latest_accepted_attempt_id": latest_accepted_attempt_id,
        "accepted_patchlet_ids": accepted_patchlet_ids,
        "pending_patchlet_ids": list(state.pending_patchlets),
        "failed_patchlet_ids": list(state.failed_patchlets),
        "goal_progress_path": ".codex-orchestrator/goal_progress.json",
        "applyable_progress": bool(latest_checkpoint),
        "allow_partial_apply": bool(latest_checkpoint),
        "workflow_goal_status": _workflow_goal_status(ctx),
        "done_eligible": state.stage == "DONE",
        "reason": "stop_requested_after_current_attempt" if latest_checkpoint else "no_accepted_checkpoint",
        "unaccepted_attempts_preserved": [],
    }
    path = ctx.paths.workflow_dir / "control" / "stop_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)
    append_operator_event(
        ctx.root,
        event_type="workflow_stopped",
        severity="warning",
        stage="STOPPED",
        summary="Workflow stopped at a safe point.",
        artifact_paths=[".codex-orchestrator/control/stop_result.json"],
        details=payload,
    )
    return payload


def _latest_checkpoint(ctx: TargetRepoContext) -> str | None:
    checkpoints = sorted(
        path
        for path in ctx.paths.integration_checkpoints_dir.glob("P*.json")
        if not path.name.endswith("_cleanliness.json")
    )
    if not checkpoints:
        return None
    return checkpoints[-1].relative_to(ctx.root).as_posix()


def _integration_ref(ctx: TargetRepoContext) -> str | None:
    if not ctx.paths.integration_state.exists():
        return None
    return read_json(ctx.paths.integration_state).get("integration_ref")


def _accepted_patchlet_ids(ctx: TargetRepoContext) -> list[str]:
    if not ctx.paths.integration_state.exists():
        return []
    accepted = read_json(ctx.paths.integration_state).get("accepted_patchlets", [])
    return list(accepted) if isinstance(accepted, list) else []


def _checkpoint_patchlet_id(path: str | None) -> str | None:
    if not path:
        return None
    return Path(path).stem


def _latest_accepted_attempt_id(ctx: TargetRepoContext, patchlet_id: str | None) -> str | None:
    if not patchlet_id:
        return None
    checkpoint = ctx.paths.integration_checkpoints_dir / f"{patchlet_id}.json"
    if not checkpoint.exists():
        return None
    attempt = read_json(checkpoint).get("attempt_id")
    return str(attempt) if attempt else None


def _workflow_goal_status(ctx: TargetRepoContext) -> str:
    path = ctx.paths.workflow_dir / "goal_progress.json"
    if not path.exists():
        return "UNKNOWN"
    status = read_json(path).get("overall_goal_status")
    return str(status) if status else "UNKNOWN"
