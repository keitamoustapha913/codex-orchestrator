from __future__ import annotations

from typing import Any

from codex_orchestrator.validators.schema_validator import validate_json


BLOCKING_STATUSES = {"AMBIGUOUS", "CONTRADICTORY", "INVALID"}


def normalize_goal_interpretation(
    *,
    model_output: dict[str, Any],
    master_prompt_frozen: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(model_output)
    normalized.setdefault("schema_version", "1.0")
    normalized.setdefault("kind", "goal_interpretation")
    normalized.setdefault("workflow_id", master_prompt_frozen.get("workflow_id"))
    normalized.setdefault("run_id", master_prompt_frozen.get("run_id"))
    normalized.setdefault("master_prompt_sha256", master_prompt_frozen.get("sha256"))
    normalized.setdefault("master_prompt_frozen_path", ".codex-orchestrator/master_prompt_frozen.json")
    normalized.setdefault("goal_summary", _prompt_excerpt(master_prompt_frozen))
    normalized.setdefault("non_goals", [])
    normalized.setdefault("ambiguities", [])
    normalized.setdefault("assumptions", [])
    normalized.setdefault("contradictions", [])
    normalized.setdefault("requires_external_resources", False)
    return normalized


def validate_goal_interpretation(interpretation: dict[str, Any], *, master_prompt_frozen: dict[str, Any] | None = None) -> None:
    errors = validate_json(interpretation, "goal_interpretation.schema.json")
    if master_prompt_frozen is not None:
        span_ids = {span.get("span_id") for span in master_prompt_frozen.get("source_spans", [])}
        if interpretation.get("master_prompt_sha256") != master_prompt_frozen.get("sha256"):
            errors.append("goal interpretation master prompt hash does not match frozen master prompt")
        if interpretation.get("proof_not_claimed_here") is not True:
            errors.append("goal interpretation must not claim proof")
        if interpretation.get("interpretation_status") in BLOCKING_STATUSES:
            errors.append(f"goal interpretation status blocks workflow: {interpretation.get('interpretation_status')}")
        for item in interpretation.get("goal_items", []):
            if item.get("required") is True and not item.get("source_span_ids"):
                errors.append(f"{item.get('goal_item_id')} missing source_span_ids")
            for span_id in item.get("source_span_ids", []):
                if span_id not in span_ids:
                    errors.append(f"{item.get('goal_item_id')} references unknown source span {span_id}")
    if errors:
        raise ValueError("; ".join(errors))


def _prompt_excerpt(master_prompt_frozen: dict[str, Any]) -> str:
    spans = master_prompt_frozen.get("source_spans", [])
    if not spans:
        return "frozen master prompt"
    return str(spans[0].get("text", "")).strip()
