from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.validators.schema_validator import validate_json


SAFE_SIDE_EFFECT_POLICIES = {"no_product_mutation"}
SAFE_EXECUTION_CONTEXTS = {"integration_candidate", "accepted_integration", "target_read_only", "artifact_only"}


def normalize_probe_plan(
    *,
    model_output: dict[str, Any],
    proof_obligations: dict[str, Any],
    master_prompt_frozen: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(model_output)
    normalized.setdefault("schema_version", "1.0")
    normalized.setdefault("kind", "probe_plan")
    normalized.setdefault("workflow_id", proof_obligations.get("workflow_id") or master_prompt_frozen.get("workflow_id"))
    normalized.setdefault("run_id", proof_obligations.get("run_id") or master_prompt_frozen.get("run_id"))
    normalized.setdefault("master_prompt_sha256", proof_obligations.get("master_prompt_sha256") or master_prompt_frozen.get("sha256"))
    normalized.setdefault("proof_obligations_path", ".codex-orchestrator/proof_planning/proof_obligations.json")
    for probe in normalized.get("probes", []):
        probe.setdefault("status", "PLANNED")
    return normalized


def validate_probe_plan_for_required_obligations(
    *,
    proof_obligations: dict[str, Any],
    probe_plan: dict[str, Any],
) -> dict[str, Any]:
    schema_errors = validate_json(probe_plan, "probe_plan.schema.json")
    covered: set[str] = set()
    invalid: list[str] = []
    invalid_reasons: list[str] = []
    obligation_ids = {row.get("obligation_id") for row in proof_obligations.get("obligations", [])}
    for probe in probe_plan.get("probes", []):
        probe_id = probe.get("probe_id")
        safe = (
            probe.get("rerunnable_by_orchestrator") is True
            and probe.get("side_effect_policy") == "no_product_mutation"
            and probe.get("execution_context") in SAFE_EXECUTION_CONTEXTS
            and probe.get("owner") != "worker_proposed"
            and bool(probe.get("expected_observation") or probe.get("expected_outputs") or probe.get("command") or probe.get("script_path"))
        )
        for obligation_id in probe.get("obligation_ids", []):
            if obligation_id not in obligation_ids:
                invalid_reasons.append(f"{probe_id} references unknown obligation {obligation_id}")
                safe = False
        if safe:
            covered.update(probe.get("obligation_ids", []))
        else:
            invalid.append(probe_id)
    required = [row["obligation_id"] for row in proof_obligations.get("obligations", []) if row.get("required") is True]
    missing = [obligation_id for obligation_id in required if obligation_id not in covered]
    return {
        "accepted": not schema_errors and not missing and not invalid and not invalid_reasons,
        "covered_obligation_ids": sorted(covered),
        "missing_obligation_ids": missing,
        "invalid_probe_ids": invalid,
        "errors": schema_errors + invalid_reasons,
    }


def validate_probe_plan(*, proof_obligations: dict[str, Any], probe_plan: dict[str, Any]) -> None:
    result = validate_probe_plan_for_required_obligations(proof_obligations=proof_obligations, probe_plan=probe_plan)
    errors = list(result.get("errors", []))
    if result["missing_obligation_ids"]:
        errors.append("required obligations lack probes: " + ", ".join(result["missing_obligation_ids"]))
    if result["invalid_probe_ids"]:
        errors.append("invalid probes: " + ", ".join(str(pid) for pid in result["invalid_probe_ids"]))
    if errors:
        raise ValueError("; ".join(errors))
