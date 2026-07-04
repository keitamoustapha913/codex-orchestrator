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
    proven = set(independent_probe_rerun_result.get("proven_obligation_ids", []))
    failed = set(independent_probe_rerun_result.get("failed_obligation_ids", []))
    covered_obligations = [row["obligation_id"] for row in required if row["obligation_id"] in proven]
    unproven = [row["obligation_id"] for row in required if row["obligation_id"] not in proven and row["obligation_id"] not in failed]
    failed_ids = [row["obligation_id"] for row in required if row["obligation_id"] in failed]
    covered_goal_items = sorted({gid for row in required if row["obligation_id"] in proven for gid in row.get("goal_item_ids", [])})
    required_goal_items = sorted({gid for row in required for gid in row.get("goal_item_ids", [])})
    uncovered_goal_items = [gid for gid in required_goal_items if gid not in covered_goal_items]
    accepted = bool(required) and not unproven and not failed_ids and not uncovered_goal_items and independent_probe_rerun_result.get("accepted") is True
    if accepted:
        status = "PASSED"
    elif covered_obligations:
        status = "PARTIAL"
    elif failed_ids:
        status = "FAILED"
    else:
        status = "BLOCKED"
    return {
        "schema_version": "1.0",
        "kind": "goal_coverage_gate_result",
        "workflow_id": proof_obligations.get("workflow_id"),
        "run_id": proof_obligations.get("run_id"),
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "master_prompt_sha256": proof_obligations.get("master_prompt_sha256"),
        "accepted": accepted,
        "coverage_status": status,
        "covered_goal_item_ids": covered_goal_items,
        "covered_obligation_ids": covered_obligations,
        "uncovered_goal_item_ids": uncovered_goal_items,
        "unproven_obligation_ids": unproven,
        "failed_obligation_ids": failed_ids,
        "blocked_obligation_ids": [],
        "evidence_paths": [f".codex-orchestrator/runs/{attempt_id}/gates/independent_probe_rerun_result.json"],
        "failure_signature": None if accepted else "goal_coverage_failed",
    }
