from __future__ import annotations

from typing import Any


def evaluate_goal_coverage_gate(
    *,
    proof_obligations: dict[str, Any],
    probe_plan: dict[str, Any],
    independent_probe_rerun_result: dict[str, Any],
    patchlet_id: str,
    attempt_id: str,
) -> dict[str, Any]:
    required = [row for row in proof_obligations.get("obligations", []) if row.get("required") is True]
    required_ids = [row["obligation_id"] for row in required]
    selected = list(independent_probe_rerun_result.get("selected_obligation_ids") or [])
    if not selected:
        selected = [
            oid
            for oid in required_ids
            if oid in set(independent_probe_rerun_result.get("proven_obligation_ids", []))
            or oid in set(independent_probe_rerun_result.get("failed_obligation_ids", []))
        ] or required_ids
    selected_set = set(selected)
    proven = set(independent_probe_rerun_result.get("proven_obligation_ids", []))
    failed = set(independent_probe_rerun_result.get("failed_obligation_ids", []))
    current_required = [row for row in required if row["obligation_id"] in selected_set]
    future_required = [row for row in required if row["obligation_id"] not in selected_set]
    covered_obligations = [row["obligation_id"] for row in required if row["obligation_id"] in proven]
    unproven = [row["obligation_id"] for row in required if row["obligation_id"] not in proven and row["obligation_id"] not in failed]
    failed_ids = [row["obligation_id"] for row in required if row["obligation_id"] in failed]
    proven_current = [row["obligation_id"] for row in current_required if row["obligation_id"] in proven]
    failed_current = [row["obligation_id"] for row in current_required if row["obligation_id"] in failed]
    unproven_current = [row["obligation_id"] for row in current_required if row["obligation_id"] not in proven and row["obligation_id"] not in failed]
    future_obligation_ids = [row["obligation_id"] for row in future_required]
    future_goal_item_ids = sorted({gid for row in future_required for gid in row.get("goal_item_ids", [])})
    covered_goal_items = sorted({gid for row in required if row["obligation_id"] in proven for gid in row.get("goal_item_ids", [])})
    required_goal_items = sorted({gid for row in required for gid in row.get("goal_item_ids", [])})
    uncovered_goal_items = [gid for gid in required_goal_items if gid not in covered_goal_items]
    current_goal_item_ids = sorted({gid for row in current_required for gid in row.get("goal_item_ids", [])})
    accepted_for_patchlet_progress = (
        bool(current_required)
        and not failed_current
        and not unproven_current
        and independent_probe_rerun_result.get("accepted") is True
    )
    accepted_for_done = bool(required) and not unproven and not failed_ids and not uncovered_goal_items
    accepted = accepted_for_patchlet_progress
    if accepted_for_done:
        status = "PASSED"
        patchlet_status = "PATCHLET_COVERED"
        workflow_status = "PROVEN"
    elif accepted_for_patchlet_progress:
        status = "PARTIAL"
        patchlet_status = "PATCHLET_PARTIAL_ACCEPTED" if future_obligation_ids else "PATCHLET_COVERED"
        workflow_status = "PARTIALLY_PROVEN"
    elif failed_current:
        status = "FAILED"
        patchlet_status = "PATCHLET_FAILED"
        workflow_status = "FAILED"
    elif covered_obligations:
        status = "PARTIAL"
        patchlet_status = "PATCHLET_PARTIAL_ACCEPTED"
        workflow_status = "PARTIALLY_PROVEN"
    elif failed_ids:
        status = "FAILED"
        patchlet_status = "PATCHLET_FAILED"
        workflow_status = "FAILED"
    else:
        status = "BLOCKED"
        patchlet_status = "PATCHLET_BLOCKED"
        workflow_status = "UNPROVEN"
    failure_signature = None if accepted_for_patchlet_progress else "goal_coverage_failed"
    return {
        "schema_version": "1.0",
        "kind": "goal_coverage_gate_result",
        "workflow_id": proof_obligations.get("workflow_id"),
        "run_id": proof_obligations.get("run_id"),
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "master_prompt_sha256": proof_obligations.get("master_prompt_sha256"),
        "accepted": accepted,
        "coverage_scope": "patchlet",
        "accepted_for_patchlet_progress": accepted_for_patchlet_progress,
        "accepted_for_done": accepted_for_done,
        "coverage_status": status,
        "patchlet_coverage_status": patchlet_status,
        "covered_goal_item_ids": covered_goal_items,
        "covered_obligation_ids": covered_obligations,
        "uncovered_goal_item_ids": uncovered_goal_items,
        "unproven_obligation_ids": unproven,
        "failed_obligation_ids": failed_ids,
        "current_goal_item_ids": current_goal_item_ids,
        "current_obligation_ids": selected,
        "proven_current_obligation_ids": proven_current,
        "failed_current_obligation_ids": failed_current,
        "future_goal_item_ids": future_goal_item_ids,
        "future_obligation_ids": future_obligation_ids,
        "workflow_goal_status_after_patchlet": workflow_status,
        "blocked_obligation_ids": [],
        "evidence_paths": [f".codex-orchestrator/runs/{attempt_id}/gates/independent_probe_rerun_result.json"],
        "failure_signature": failure_signature,
    }
