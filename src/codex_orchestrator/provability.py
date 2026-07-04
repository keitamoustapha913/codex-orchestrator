from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.state import now_iso


def classify_goal_provability(
    *,
    master_prompt_frozen: dict[str, Any],
    goal_interpretation: dict[str, Any],
    semantic_goal_spec: dict[str, Any] | None,
    repo_census: dict[str, Any] | None,
    capabilities: dict[str, Any] | None,
) -> dict[str, Any]:
    available = sorted((capabilities or {"local_execution": True}).keys())
    criteria = (semantic_goal_spec or {}).get("criteria", [])
    if criteria and goal_interpretation.get("interpretation_status") == "CONCORDANT":
        status = "PROVABLE"
        blocking: list[str] = []
        reasons = ["At least one required proof obligation can be formed and independently checked."]
        count = 1
        can_start = True
    else:
        status = "AMBIGUOUS"
        blocking = goal_interpretation.get("ambiguities") or ["No objective proof obligation could be formed."]
        reasons = ["The goal is ambiguous and no objective proof obligation could be formed."]
        count = 0
        can_start = False
    return {
        "schema_version": "1.0",
        "kind": "provability_result",
        "workflow_id": master_prompt_frozen.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id"),
        "master_prompt_sha256": master_prompt_frozen.get("sha256"),
        "created_at": now_iso(),
        "provability_status": status,
        "provability_stage": "pre_patchlet",
        "reasons": reasons,
        "blocking_reasons": blocking,
        "required_capabilities": ["local_execution"] if count else [],
        "available_capabilities": available,
        "missing_capabilities": [],
        "proof_obligation_count": count,
        "probe_plan_required": bool(count),
        "can_start_product_patchlets": can_start,
    }


def write_provability_result(workflow_root: Path, result: dict[str, Any]) -> Path:
    out_dir = workflow_root / "provability"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "provability_result.json"
    write_json(path, result)
    if result.get("can_start_product_patchlets") is not True:
        write_json(out_dir / "goal_not_provable_result.json", goal_not_provable_result(result))
    return path


def goal_not_provable_result(result: dict[str, Any]) -> dict[str, Any]:
    ambiguous = result.get("provability_status") == "AMBIGUOUS"
    return {
        "schema_version": "1.0",
        "kind": "goal_not_provable_result",
        "workflow_id": result.get("workflow_id"),
        "run_id": result.get("run_id"),
        "master_prompt_sha256": result.get("master_prompt_sha256"),
        "stage": "pre_patchlet",
        "status": "SAFE_FAILURE",
        "failure_signature": "goal_ambiguous" if ambiguous else "goal_not_provable",
        "reasons": result.get("blocking_reasons") or result.get("reasons", []),
        "created_artifacts": [
            ".codex-orchestrator/master_prompt_frozen.json",
            ".codex-orchestrator/goal_interpretation.json",
            ".codex-orchestrator/provability/provability_result.json",
        ],
    }
