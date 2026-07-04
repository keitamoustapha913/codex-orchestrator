from __future__ import annotations

import re
from typing import Any


GOAL_ITEM_ALIASES = ("goal_item", "goal_item_id", "goal")
WORKER_PROOF_FIELDS = {"criterion_id", "expected_value", "actual_value", "passed", "verification_source"}
VAGUE_RESULT_TEXTS = {
    "done",
    "ok",
    "okay",
    "looks good",
    "complete",
    "completed",
    "success",
    "successful",
    "passes",
    "passed",
    "fixed",
    "implemented",
    "seems fine",
    "probably passes",
    "all good",
}
FUTURE_CLAIM_PATTERNS = (
    "all five",
    "all settings",
    "future work complete",
    "future slices complete",
    "master prompt satisfied",
    "final goal complete",
)
COMPLETION_WORDS = {"updated", "changed", "complete", "completed", "set", "strict", "green", "enabled", "deny", "done"}


def _norm_text(value: str) -> str:
    return re.sub(r"[^a-z0-9=.-]+", " ", value.lower()).strip()


def _goal_item_from(raw_item: dict[str, Any]) -> str | None:
    for alias in GOAL_ITEM_ALIASES:
        value = raw_item.get(alias)
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


def _boundary_tokens(slice_change_boundary: dict[str, Any] | None, probe_plan: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    boundary = slice_change_boundary or {}
    if boundary.get("section"):
        tokens.add(str(boundary["section"]).strip("[]"))
    for change in boundary.get("allowed_changes") or []:
        for key in ("key", "old_value", "new_value", "old_line", "new_line", "section"):
            value = change.get(key)
            if isinstance(value, str) and value.strip():
                tokens.add(value.strip())
                if "=" in value:
                    tokens.update(part.strip() for part in value.split("=") if part.strip())
    for probe in probe_plan.get("probes", []):
        expected = probe.get("expected_observation") or {}
        for value in expected.values() if isinstance(expected, dict) else []:
            if isinstance(value, str) and value.strip():
                tokens.add(value.strip())
                if "=" in value:
                    tokens.update(part.strip() for part in value.split("=") if part.strip())
    return {_norm_text(token) for token in tokens if _norm_text(token)}


def _forbidden_keys(slice_change_boundary: dict[str, Any] | None) -> set[str]:
    return {
        _norm_text(str(row.get("key")))
        for row in (slice_change_boundary or {}).get("forbidden_changes", [])
        if row.get("key")
    }


def _is_vague(text: str) -> bool:
    normalized = _norm_text(text).rstrip(".")
    return normalized in VAGUE_RESULT_TEXTS


def _claims_future_slice(text: str, *, forbidden_keys: set[str]) -> bool:
    normalized = _norm_text(text)
    if any(pattern in normalized for pattern in FUTURE_CLAIM_PATTERNS):
        return True
    words = set(normalized.split())
    if "without" in words or "unchanged" in words or "reserved" in words:
        return False
    return bool(forbidden_keys & words and COMPLETION_WORDS & words)


def _mentions_current_boundary(text: str, *, tokens: set[str]) -> bool:
    normalized = _norm_text(text)
    return any(token and token in normalized for token in tokens)


def _reject(raw_item: Any, *, index: int, code: str, message: str, goal_item_id: str | None = None) -> dict[str, Any]:
    return {
        "raw_item": raw_item,
        "raw_item_index": index,
        "raw_shape": "shorthand_goal_item_result" if isinstance(raw_item, dict) else "unsupported",
        "goal_item_id": goal_item_id,
        "error_code": code,
        "message": message,
    }


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
) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    canonical_results: list[dict[str, Any]] = []
    selected_goals = set(selected_goal_item_ids)
    future_goals = set((slice_change_boundary or {}).get("forbidden_future_goal_item_ids", []))
    boundary_tokens = _boundary_tokens(slice_change_boundary, probe_plan)
    forbidden = _forbidden_keys(slice_change_boundary)
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
            rejected.append(_reject(raw_item, index=index, code="MISSING_GOAL_ITEM", message="shorthand semantic result requires goal_item, goal_item_id, or goal"))
            continue
        if goal_item_id in future_goals:
            rejected.append(_reject(raw_item, index=index, code="FUTURE_GOAL_ITEM", message="shorthand semantic result references a future goal item", goal_item_id=goal_item_id))
            continue
        if goal_item_id not in selected_goals:
            rejected.append(_reject(raw_item, index=index, code="UNLINKED_GOAL_ITEM", message="shorthand semantic result does not link to the current patchlet goal item", goal_item_id=goal_item_id))
            continue
        if any(field in raw_item for field in WORKER_PROOF_FIELDS):
            rejected.append(_reject(raw_item, index=index, code="WORKER_PROOF_CLAIM_NOT_ALLOWED", message="worker shorthand may not claim canonical proof fields", goal_item_id=goal_item_id))
            continue
        if not isinstance(result_text, str) or not result_text.strip():
            rejected.append(_reject(raw_item, index=index, code="MISSING_RESULT_TEXT", message="shorthand semantic result requires non-empty result text", goal_item_id=goal_item_id))
            continue
        if _is_vague(result_text):
            rejected.append(_reject(raw_item, index=index, code="VAGUE_RESULT_TEXT", message="shorthand semantic result is too vague to link safely", goal_item_id=goal_item_id))
            continue
        if _claims_future_slice(result_text, forbidden_keys=forbidden):
            rejected.append(_reject(raw_item, index=index, code="FUTURE_SLICE_CLAIM", message="shorthand semantic result claims future-slice completion", goal_item_id=goal_item_id))
            continue
        if not _mentions_current_boundary(result_text, tokens=boundary_tokens):
            rejected.append(_reject(raw_item, index=index, code="CURRENT_BOUNDARY_NOT_MENTIONED", message="shorthand semantic result does not mention the current slice boundary", goal_item_id=goal_item_id))
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
        "canonical_results_from_worker": canonical_results,
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
