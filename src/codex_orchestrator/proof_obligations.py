from __future__ import annotations

from typing import Any

from codex_orchestrator.state import now_iso
from codex_orchestrator.validators.schema_validator import validate_json


def normalize_proof_obligations(
    *,
    master_prompt_frozen: dict[str, Any],
    goal_interpretation: dict[str, Any],
    model_output: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(model_output)
    normalized.setdefault("schema_version", "1.0")
    normalized.setdefault("kind", "proof_obligations")
    normalized.setdefault("workflow_id", master_prompt_frozen.get("workflow_id"))
    normalized.setdefault("run_id", master_prompt_frozen.get("run_id"))
    normalized.setdefault("master_prompt_sha256", master_prompt_frozen.get("sha256"))
    normalized.setdefault("master_prompt_frozen_path", ".codex-orchestrator/master_prompt_frozen.json")
    normalized.setdefault("goal_interpretation_path", ".codex-orchestrator/goal_interpretation/goal_interpretation.json")
    for obligation in normalized.get("obligations", []):
        if "proof_kind" not in obligation and "proof_strategy" in obligation:
            obligation["proof_kind"] = obligation["proof_strategy"]
        if "proof_strategy" not in obligation and "proof_kind" in obligation:
            obligation["proof_strategy"] = obligation["proof_kind"]
    return normalized


def validate_proof_obligations(*, proof_obligations: dict[str, Any], goal_interpretation: dict[str, Any], master_prompt_frozen: dict[str, Any]) -> None:
    errors = validate_json(proof_obligations, "proof_obligations.schema.json")
    if proof_obligations.get("master_prompt_sha256") != master_prompt_frozen.get("sha256"):
        errors.append("proof obligations master prompt hash does not match frozen master prompt")
    goal_ids = {item.get("goal_item_id") for item in goal_interpretation.get("goal_items", [])}
    required_goal_ids = {item.get("goal_item_id") for item in goal_interpretation.get("goal_items", []) if item.get("required") is True}
    span_ids = {span.get("span_id") for span in master_prompt_frozen.get("source_spans", [])}
    covered_goal_ids: set[str] = set()
    for obligation in proof_obligations.get("obligations", []):
        oid = obligation.get("obligation_id")
        if obligation.get("required") is True:
            covered_goal_ids.update(obligation.get("goal_item_ids", []))
        if not obligation.get("goal_item_ids"):
            errors.append(f"{oid} missing goal_item_ids")
        for goal_id in obligation.get("goal_item_ids", []):
            if goal_id not in goal_ids:
                errors.append(f"{oid} references unknown goal item {goal_id}")
        if not obligation.get("source_span_ids"):
            errors.append(f"{oid} missing source_span_ids")
        for span_id in obligation.get("source_span_ids", []):
            if span_id not in span_ids:
                errors.append(f"{oid} references unknown source span {span_id}")
        if not (obligation.get("proof_strategy") or obligation.get("proof_kind")):
            errors.append(f"{oid} missing proof strategy")
        if not obligation.get("evidence_requirements"):
            errors.append(f"{oid} missing evidence requirements")
        claim = str(obligation.get("claim") or obligation.get("statement") or "").strip()
        if len(claim) < 12 or claim.lower() in {"prove it", "works", "verify behavior"}:
            errors.append(f"{oid} has vague claim")
    missing = sorted(required_goal_ids - covered_goal_ids)
    if missing:
        errors.append(f"required goal items lack proof obligations: {', '.join(missing)}")
    if errors:
        raise ValueError("; ".join(errors))


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
