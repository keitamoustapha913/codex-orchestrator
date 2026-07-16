from __future__ import annotations

import re
from typing import Any

from codex_orchestrator.boundary_evidence import (
    detect_future_boundary_claim,
    is_vague_worker_claim,
    match_worker_claim_to_current_boundary,
)


WORKER_PROOF_FIELDS = {"criterion_id", "expected_value", "actual_value", "passed", "verification_source"}


def _norm_text(value: str) -> str:
    return re.sub(r"[^a-z0-9=.-]+", " ", value.lower()).strip()


def _goal_item_from(raw_item: dict[str, Any]) -> str | None:
    value = raw_item.get("goal_item_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _proof_obligations_for_goal(
    *,
    goal_item_id: str,
    selected_proof_obligation_ids: list[str],
    proof_obligations: dict[str, Any],
) -> list[str]:
    selected = set(selected_proof_obligation_ids)
    return [
        row["obligation_id"]
        for row in proof_obligations.get("obligations", [])
        if row.get("obligation_id") in selected and goal_item_id in set(row.get("goal_item_ids", []))
    ]


def _probe_for_obligation(proof_obligation_id: str, probe_plan: dict[str, Any]) -> dict[str, Any] | None:
    for probe in probe_plan.get("probes", []):
        if proof_obligation_id in set(probe.get("obligation_ids", [])):
            return probe
    return None


def _reject(raw_item: Any, *, index: int, code: str, message: str, goal_item_id: str | None = None) -> dict[str, Any]:
    return {
        "raw_item": raw_item,
        "raw_item_index": index,
        "raw_shape": "shorthand_goal_item_result" if isinstance(raw_item, dict) else "unsupported",
        "goal_item_id": goal_item_id,
        "error_code": code,
        "message": message,
    }


def _quality_warning(raw_item: Any, *, index: int, code: str, message: str, goal_item_id: str | None = None) -> dict[str, Any]:
    row = _reject(raw_item, index=index, code=code, message=message, goal_item_id=goal_item_id)
    row["severity"] = "WARNING"
    row["blocking"] = False
    if code == "CURRENT_BOUNDARY_NOT_MENTIONED":
        row["warning_code"] = "WORKER_REPORT_SEMANTIC_EVIDENCE_INCOMPLETE"
    return row


def normalize_semantic_goal_results(
    *,
    raw_items: list[dict[str, Any]],
    patchlet_id: str,
    work_slice_id: str,
    selected_goal_item_ids: list[str],
    selected_proof_obligation_ids: list[str],
    proof_obligations: dict[str, Any],
    probe_plan: dict[str, Any],
    slice_change_boundary: dict[str, Any] | None,
    allowed_product_runtime_file: str | None = None,
    actual_diff_text: str | None = None,
) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    quality_warnings: list[dict[str, Any]] = []
    canonical_results: list[dict[str, Any]] = []
    selected_goals = set(selected_goal_item_ids)
    future_goals = set((slice_change_boundary or {}).get("forbidden_future_goal_item_ids", []))
    future_obligations = list((slice_change_boundary or {}).get("forbidden_future_proof_obligation_ids", []))
    future_obligations.extend(
        row.get("obligation_id")
        for row in proof_obligations.get("obligations", [])
        if isinstance(row, dict) and set(row.get("goal_item_ids", [])) - selected_goals
    )
    future_obligations = [item for item in dict.fromkeys(future_obligations) if isinstance(item, str)]
    boundary_match_results: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            rejected.append(_reject(raw_item, index=index, code="INVALID_SEMANTIC_RESULT_SHAPE", message="semantic result must be an object"))
            continue
        if raw_item.get("criterion_id"):
            canonical_results.append(raw_item)
            continue
        goal_item_id = _goal_item_from(raw_item)
        result_text = raw_item.get("result")
        if not goal_item_id:
            rejected.append(_reject(raw_item, index=index, code="MISSING_GOAL_ITEM", message="shorthand semantic result requires goal_item_id"))
            continue
        if goal_item_id in future_goals:
            quality_warnings.append(_quality_warning(raw_item, index=index, code="FUTURE_GOAL_ITEM", message="shorthand semantic result references a future goal item", goal_item_id=goal_item_id))
            continue
        if goal_item_id not in selected_goals:
            quality_warnings.append(_quality_warning(raw_item, index=index, code="UNLINKED_GOAL_ITEM", message="shorthand semantic result does not link to the current patchlet goal item", goal_item_id=goal_item_id))
            continue
        if any(field in raw_item for field in WORKER_PROOF_FIELDS):
            quality_warnings.append(_quality_warning(raw_item, index=index, code="WORKER_PROOF_CLAIM_NOT_ALLOWED", message="worker shorthand may not claim canonical proof fields", goal_item_id=goal_item_id))
            continue
        if not isinstance(result_text, str) or not result_text.strip():
            rejected.append(_reject(raw_item, index=index, code="MISSING_RESULT_TEXT", message="shorthand semantic result requires non-empty result text", goal_item_id=goal_item_id))
            continue
        if is_vague_worker_claim(result_text):
            quality_warnings.append(_quality_warning(raw_item, index=index, code="VAGUE_RESULT_TEXT", message="shorthand semantic result is too vague to link safely", goal_item_id=goal_item_id))
            continue
        boundary_match = match_worker_claim_to_current_boundary(
            worker_text=result_text,
            allowed_product_runtime_file=allowed_product_runtime_file,
            slice_change_boundary=slice_change_boundary,
            proof_obligations=proof_obligations,
            probe_plan=probe_plan,
            selected_proof_obligation_ids=selected_proof_obligation_ids,
            future_proof_obligation_ids=future_obligations,
            actual_diff_text=actual_diff_text,
        )
        boundary_match_results.append({
            "raw_item_index": index,
            "goal_item_id": goal_item_id,
            **boundary_match,
        })
        if boundary_match.get("mentions_future_boundary") or detect_future_boundary_claim(
            result_text,
            proof_obligations=proof_obligations,
            future_proof_obligation_ids=future_obligations,
            slice_change_boundary=slice_change_boundary,
        ):
            quality_warnings.append(_quality_warning(raw_item, index=index, code="FUTURE_SLICE_CLAIM", message="shorthand semantic result claims future-slice completion", goal_item_id=goal_item_id))
            continue
        if not boundary_match.get("mentions_current_boundary"):
            quality_warnings.append(_quality_warning(raw_item, index=index, code="CURRENT_BOUNDARY_NOT_MENTIONED", message="shorthand semantic result does not mention the current slice boundary", goal_item_id=goal_item_id))
            continue
        matching_obligations = _proof_obligations_for_goal(
            goal_item_id=goal_item_id,
            selected_proof_obligation_ids=selected_proof_obligation_ids,
            proof_obligations=proof_obligations,
        )
        if len(matching_obligations) != 1:
            rejected.append(_reject(raw_item, index=index, code="AMBIGUOUS_PROOF_OBLIGATION_LINK", message="shorthand semantic result must link to exactly one current proof obligation", goal_item_id=goal_item_id))
            continue
        proof_obligation_id = matching_obligations[0]
        probe = _probe_for_obligation(proof_obligation_id, probe_plan)
        if probe is None:
            rejected.append(_reject(raw_item, index=index, code="UNLINKED_PROBE_PLAN", message="shorthand semantic result has no selected probe-plan link", goal_item_id=goal_item_id))
            continue
        accepted.append(
            {
                "kind": "worker_semantic_claim",
                "claim_id": f"WSC{len(accepted) + 1:03d}",
                "patchlet_id": patchlet_id,
                "work_slice_id": work_slice_id,
                "goal_item_id": goal_item_id,
                "proof_obligation_id": proof_obligation_id,
                "raw_result_text": result_text,
                "claim_status": "LINKED_PENDING_ORCHESTRATOR_PROOF",
                "raw_item": raw_item,
                "raw_item_index": index,
                "raw_shape": "shorthand_goal_item_result",
                "linkage": {
                    "goal_item_linked": True,
                    "proof_obligation_linked": True,
                    "slice_boundary_linked": True,
                    "probe_plan_linked": True,
                },
                "safety": {
                    "vague": False,
                    "mentions_current_boundary": True,
                    "mentions_forbidden_future_boundary": False,
                    "claims_future_slice_completion": False,
                },
                "boundary_evidence_match": boundary_match,
                "proof_not_claimed_here": True,
            }
        )
    return {
        "schema_version": "1.0",
        "kind": "semantic_goal_results_normalization_result",
        "patchlet_id": patchlet_id,
        "work_slice_id": work_slice_id,
        "accepted": not rejected,
        "accepted_raw_claims": accepted,
        "rejected_raw_claims": rejected,
        "semantic_quality_warnings": quality_warnings,
        "canonical_results_from_worker": canonical_results,
        "boundary_evidence_matches": boundary_match_results,
        "proof_not_claimed_here": True,
    }


def _probe_row_for_obligation(independent_probe_rerun_result: dict[str, Any], obligation_id: str) -> dict[str, Any] | None:
    for row in independent_probe_rerun_result.get("probe_results", []):
        if obligation_id in set(row.get("obligation_ids", [])):
            return row
    return None


def canonicalize_semantic_goal_results_after_probe(
    *,
    normalization_result: dict[str, Any],
    independent_probe_rerun_result: dict[str, Any],
    proof_obligations: dict[str, Any],
    probe_plan: dict[str, Any],
) -> dict[str, Any]:
    if independent_probe_rerun_result.get("kind") != "independent_probe_rerun_result":
        raise ValueError("independent probe result is required before semantic result canonicalization")
    canonical_results: list[dict[str, Any]] = []
    selected = set(independent_probe_rerun_result.get("selected_obligation_ids", []))
    proven = set(independent_probe_rerun_result.get("proven_obligation_ids", []))
    failed = set(independent_probe_rerun_result.get("failed_obligation_ids", []))
    for claim in normalization_result.get("accepted_raw_claims", []):
        if claim.get("claim_status") != "LINKED_PENDING_ORCHESTRATOR_PROOF":
            raise ValueError("semantic worker claim must be linked before canonicalization")
        obligation_id = claim["proof_obligation_id"]
        if obligation_id not in selected:
            continue
        probe_row = _probe_row_for_obligation(independent_probe_rerun_result, obligation_id)
        if probe_row is None:
            continue
        expected_actual = probe_row.get("expected_actual") or {}
        passed = obligation_id in proven and probe_row.get("passed") is True
        if obligation_id in failed:
            passed = False
        canonical_results.append(
            {
                "criterion_id": obligation_id,
                "kind": "orchestrator_verified_proof_obligation_result",
                "goal_item_id": claim["goal_item_id"],
                "proof_obligation_id": obligation_id,
                "work_slice_id": claim["work_slice_id"],
                "patchlet_id": claim["patchlet_id"],
                "expected_value": expected_actual.get("expected"),
                "actual_value": expected_actual.get("actual"),
                "passed": passed,
                "verification_source": "independent_probe_rerun",
                "independent_probe_id": probe_row.get("probe_id"),
                "worker_claim_id": claim["claim_id"],
                "raw_worker_result": claim.get("raw_item"),
            }
        )
    return {
        "schema_version": "1.0",
        "kind": "semantic_goal_results_canonicalization_result",
        "patchlet_id": normalization_result.get("patchlet_id"),
        "work_slice_id": normalization_result.get("work_slice_id"),
        "canonical_results": canonical_results,
        "raw_worker_results_preserved": True,
    }
