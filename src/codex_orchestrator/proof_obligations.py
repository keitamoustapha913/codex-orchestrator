from __future__ import annotations

from typing import Any

from codex_orchestrator.state import now_iso


def build_proof_obligations(
    *,
    master_prompt_frozen: dict[str, Any],
    goal_interpretation: dict[str, Any],
    semantic_goal_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    obligations: list[dict[str, Any]] = []
    criteria = (semantic_goal_spec or {}).get("criteria", [])
    if criteria and goal_interpretation.get("interpretation_status") == "CONCORDANT":
        criterion = criteria[0]
        obligations.append(
            {
                "obligation_id": "PO001",
                "goal_item_ids": ["GI001"],
                "source_span_ids": goal_interpretation["goal_items"][0].get("source_span_ids", []),
                "obligation_type": "behavioral_runtime_claim",
                "statement": "The accepted integration state satisfies the requested runtime behavior.",
                "required": True,
                "proof_kind": "executable_probe",
                "evidence_requirements": ["direct_probe", "expected_actual_record", "orchestrator_rerun"],
                "acceptance_rule": {"type": "expected_actual_equal", "expected": criterion.get("expected_value")},
                "status": "UNPROVEN",
                "evidence_paths": [],
                "last_updated_at": None,
                "metadata": {"semantic_criterion_id": criterion.get("criterion_id")},
            }
        )
    return {
        "schema_version": "1.0",
        "kind": "proof_obligations",
        "workflow_id": master_prompt_frozen.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id"),
        "master_prompt_sha256": master_prompt_frozen.get("sha256"),
        "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
        "goal_interpretation_path": ".codex-orchestrator/goal_interpretation.json",
        "obligations": obligations,
    }


def update_obligation_status(
    *,
    obligations: dict[str, Any],
    obligation_id: str,
    status: str,
    evidence_paths: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    updated = dict(obligations)
    rows = [dict(row) for row in obligations.get("obligations", [])]
    for row in rows:
        if row.get("obligation_id") != obligation_id:
            continue
        row["status"] = status
        row["last_updated_at"] = now_iso()
        if evidence_paths is not None:
            row["evidence_paths"] = evidence_paths
        if reason:
            row["reason"] = reason
    updated["obligations"] = rows
    return updated


def summarize_obligation_coverage(obligations: dict[str, Any]) -> dict[str, Any]:
    rows = obligations.get("obligations", [])
    required = [row for row in rows if row.get("required") is True]
    return {
        "required_obligations": len(required),
        "proven": len([row for row in required if row.get("status") == "PROVEN_BY_ORCHESTRATOR"]),
        "failed": len([row for row in required if row.get("status") == "FAILED"]),
        "blocked": len([row for row in required if row.get("status") == "BLOCKED"]),
        "unproven": len([row for row in required if row.get("status") in {"UNPROVEN", "IN_PROGRESS", "PROVEN_BY_WORKER"}]),
    }
