from __future__ import annotations

from typing import Any

from codex_orchestrator.validators.schema_validator import validate_json


def build_goal_interpretation(
    *,
    master_prompt_frozen: dict[str, Any],
    semantic_goal_spec: dict[str, Any] | None = None,
    repo_census: dict[str, Any] | None = None,
) -> dict[str, Any]:
    criteria = (semantic_goal_spec or {}).get("criteria", [])
    spans = master_prompt_frozen.get("source_spans", [])
    span_ids = [spans[0]["span_id"]] if spans else []
    if criteria:
        criterion = criteria[0]
        expected = criterion.get("expected_value")
        goal_items = [
            {
                "goal_item_id": "GI001",
                "source_span_ids": span_ids,
                "goal_type": "behavior_change",
                "subject": "target repository behavior",
                "desired_state": f'app.main() returns "{expected}"',
                "must_change_product": "unknown",
                "acceptance_meaning": "A direct runtime check observes the expected value.",
                "required": True,
                "metadata": {"semantic_criterion_id": criterion.get("criterion_id")},
            }
        ]
        status = "CONCORDANT"
        summary = f'The application should make app.main() return "{expected}" and prove it.'
        ambiguities: list[str] = []
    else:
        goal_items = [
            {
                "goal_item_id": "GI001",
                "source_span_ids": span_ids,
                "goal_type": "unsupported_or_ambiguous",
                "subject": "target repository behavior",
                "desired_state": _prompt_excerpt(master_prompt_frozen),
                "must_change_product": "unknown",
                "acceptance_meaning": "No objective acceptance meaning was derived.",
                "required": True,
            }
        ]
        status = "AMBIGUOUS"
        summary = "The frozen master prompt could not be mapped to an objective built-in proof target."
        ambiguities = (semantic_goal_spec or {}).get("unsupported_reasons") or ["No objective proof target was derived."]
    return {
        "schema_version": "1.0",
        "kind": "goal_interpretation",
        "workflow_id": master_prompt_frozen.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id"),
        "master_prompt_sha256": master_prompt_frozen.get("sha256"),
        "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
        "interpretation_status": status,
        "goal_summary": summary,
        "goal_items": goal_items,
        "non_goals": [],
        "ambiguities": ambiguities,
        "assumptions": [],
        "requires_external_resources": False,
        "proof_not_claimed_here": True,
    }


def validate_goal_interpretation(interpretation: dict[str, Any]) -> None:
    errors = validate_json(interpretation, "goal_interpretation.schema.json")
    if errors:
        raise ValueError("; ".join(errors))


def _prompt_excerpt(master_prompt_frozen: dict[str, Any]) -> str:
    spans = master_prompt_frozen.get("source_spans", [])
    if not spans:
        return "frozen master prompt"
    return str(spans[0].get("text", "")).strip()
