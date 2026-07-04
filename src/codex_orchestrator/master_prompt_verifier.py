from __future__ import annotations

from typing import Any


def evaluate_master_prompt_concordance(
    *,
    master_prompt_frozen: dict[str, Any],
    goal_interpretation: dict[str, Any],
    proof_obligations: dict[str, Any],
) -> dict[str, Any]:
    span_ids = [span["span_id"] for span in master_prompt_frozen.get("source_spans", [])]
    goal_span_ids = sorted({sid for item in goal_interpretation.get("goal_items", []) for sid in item.get("source_span_ids", [])})
    obligation_goal_ids = sorted({gid for row in proof_obligations.get("obligations", []) for gid in row.get("goal_item_ids", [])})
    required_goal_ids = [item["goal_item_id"] for item in goal_interpretation.get("goal_items", []) if item.get("required") is True]
    uncovered_goal_ids = [gid for gid in required_goal_ids if gid not in obligation_goal_ids]
    uncovered_spans = [sid for sid in span_ids[:1] if sid not in goal_span_ids]
    accepted = (
        goal_interpretation.get("interpretation_status") == "CONCORDANT"
        and not uncovered_spans
        and not uncovered_goal_ids
        and bool(proof_obligations.get("obligations"))
    )
    return {
        "schema_version": "1.0",
        "kind": "master_prompt_concordance_result",
        "workflow_id": master_prompt_frozen.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id"),
        "master_prompt_sha256": master_prompt_frozen.get("sha256"),
        "accepted": accepted,
        "coverage_status": "PASSED" if accepted else "FAILED",
        "covered_source_span_ids": goal_span_ids,
        "uncovered_source_span_ids": uncovered_spans,
        "covered_goal_item_ids": obligation_goal_ids,
        "uncovered_goal_item_ids": uncovered_goal_ids,
        "contradictions": [] if accepted else ["master_prompt_concordance_failed"],
        "ambiguities": goal_interpretation.get("ambiguities", []),
        "evidence_paths": [
            ".codex-orchestrator/master_prompt_frozen.json",
            ".codex-orchestrator/goal_interpretation.json",
            ".codex-orchestrator/proof_obligations.json",
        ],
        "failure_signature": None if accepted else "master_prompt_concordance_failed",
    }


def evaluate_master_prompt_satisfaction(
    *,
    master_prompt_frozen: dict[str, Any],
    proof_obligations: dict[str, Any],
    goal_progress: dict[str, Any],
    coverage_results: list[dict[str, Any]],
) -> dict[str, Any]:
    required = [row for row in proof_obligations.get("obligations", []) if row.get("required") is True]
    proven = sorted({oid for result in coverage_results for oid in result.get("covered_obligation_ids", []) if result.get("accepted") is True})
    failed = sorted({oid for result in coverage_results for oid in result.get("failed_obligation_ids", [])})
    required_ids = [row["obligation_id"] for row in required]
    unproven = [oid for oid in required_ids if oid not in proven and oid not in failed]
    accepted = bool(required) and not failed and not unproven
    return {
        "schema_version": "1.0",
        "kind": "master_prompt_satisfaction_result",
        "workflow_id": master_prompt_frozen.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id"),
        "master_prompt_sha256": master_prompt_frozen.get("sha256"),
        "accepted": accepted,
        "satisfaction_status": "SATISFIED" if accepted else ("PARTIALLY_SATISFIED" if proven else "NOT_SATISFIED"),
        "proven_obligation_ids": proven,
        "failed_obligation_ids": failed,
        "unproven_obligation_ids": unproven,
        "blocked_obligation_ids": [],
        "goal_progress_path": ".codex-orchestrator/goal_progress.json",
        "independent_probe_evidence": [path for result in coverage_results for path in result.get("evidence_paths", [])],
        "operator_summary": (
            "The accepted integration state satisfies all required proof obligations derived from the frozen master prompt."
            if accepted
            else "The accepted integration state does not satisfy all required proof obligations derived from the frozen master prompt."
        ),
        "failure_signature": None if accepted else "master_prompt_not_satisfied",
    }
