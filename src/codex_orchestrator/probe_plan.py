from __future__ import annotations

from pathlib import Path
from typing import Any


def build_probe_plan(
    *,
    proof_obligations: dict[str, Any],
    semantic_goal_spec: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []
    for obligation in proof_obligations.get("obligations", []):
        expected = (obligation.get("acceptance_rule") or {}).get("expected")
        probes.append(
            {
                "probe_id": f"GP{len(probes) + 1:03d}",
                "obligation_ids": [obligation["obligation_id"]],
                "probe_kind": "executable",
                "owner": "orchestrator_generated",
                "command": "PYTHONDONTWRITEBYTECODE=1 python -B <orchestrator-owned semantic goal probe>",
                "execution_context": "integration_candidate",
                "expected_outputs": [{"field": "actual", "comparison": "equals", "expected": expected}],
                "side_effect_policy": "no_product_mutation",
                "rerunnable_by_orchestrator": True,
                "status": "PLANNED",
                "evidence_paths": [],
            }
        )
    return {
        "schema_version": "1.0",
        "kind": "probe_plan",
        "workflow_id": proof_obligations.get("workflow_id"),
        "run_id": proof_obligations.get("run_id"),
        "master_prompt_sha256": proof_obligations.get("master_prompt_sha256"),
        "proof_obligations_path": ".codex-orchestrator/proof_obligations.json",
        "probes": probes,
    }


def validate_probe_plan_for_required_obligations(
    *,
    proof_obligations: dict[str, Any],
    probe_plan: dict[str, Any],
) -> dict[str, Any]:
    covered: set[str] = set()
    invalid: list[str] = []
    for probe in probe_plan.get("probes", []):
        safe = (
            probe.get("rerunnable_by_orchestrator") is True
            and probe.get("side_effect_policy") == "no_product_mutation"
            and probe.get("probe_kind") == "executable"
            and bool(probe.get("expected_outputs"))
        )
        if safe:
            covered.update(probe.get("obligation_ids", []))
        else:
            invalid.append(probe.get("probe_id"))
    required = [row["obligation_id"] for row in proof_obligations.get("obligations", []) if row.get("required") is True]
    missing = [obligation_id for obligation_id in required if obligation_id not in covered]
    return {
        "accepted": not missing and not invalid,
        "covered_obligation_ids": sorted(covered),
        "missing_obligation_ids": missing,
        "invalid_probe_ids": invalid,
    }
