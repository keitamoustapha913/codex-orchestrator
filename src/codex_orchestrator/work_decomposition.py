from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.impact_analysis import build_impact_dependency_analysis, write_impact_dependency_analysis
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.patchlet_planner import (
    build_dependency_graph_from_patchlet_plan,
    build_patchlet_plan,
    build_transaction_group_plan,
)
from codex_orchestrator.work_slice_planner import plan_work_slices


def build_work_decomposition_plan(
    *,
    repo_root: Path,
    workflow_root: Path,
    inventory_graph: dict[str, Any],
    proof_obligations: dict[str, Any],
    goal_interpretation: dict[str, Any],
    master_prompt_frozen: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    impact = build_impact_dependency_analysis(
        repo_root=repo_root,
        inventory_graph=inventory_graph,
        proof_obligations=proof_obligations,
        goal_interpretation=goal_interpretation,
    )
    write_impact_dependency_analysis(repo_root=repo_root, workflow_root=workflow_root, analysis=impact)
    work_slices = plan_work_slices(
        impact_analysis=impact,
        proof_obligations=proof_obligations,
        default_patchlet_timeout_seconds=timeout_seconds,
    )
    patchlet_plan = build_patchlet_plan(
        work_slices=work_slices,
        dependency_graph=None,
        default_patchlet_timeout_seconds=timeout_seconds,
    )
    dependency_graph = build_dependency_graph_from_patchlet_plan(patchlet_plan)
    transaction_group_plan = build_transaction_group_plan(patchlet_plan, dependency_graph)
    decomp_dir = workflow_root / "decomposition"
    write_json(decomp_dir / "work_slices.json", work_slices)
    append_operator_event(
        repo_root,
        event_type="work_slices_written",
        severity="info",
        stage="WORK_DECOMPOSITION",
        summary=f"Work slices written: {len(work_slices.get('slices', []))}.",
        artifact_paths=[".codex-orchestrator/decomposition/work_slices.json"],
    )
    write_json(decomp_dir / "patchlet_plan.json", patchlet_plan)
    append_operator_event(
        repo_root,
        event_type="patchlet_plan_written",
        severity="info",
        stage="WORK_DECOMPOSITION",
        summary=f"Patchlet plan written: {len(patchlet_plan.get('patchlets', []))} patchlets.",
        artifact_paths=[".codex-orchestrator/decomposition/patchlet_plan.json"],
    )
    write_json(decomp_dir / "dependency_graph.json", dependency_graph)
    append_operator_event(
        repo_root,
        event_type="dependency_graph_written",
        severity="info",
        stage="WORK_DECOMPOSITION",
        summary="Decomposition dependency graph written.",
        artifact_paths=[".codex-orchestrator/decomposition/dependency_graph.json"],
    )
    write_json(decomp_dir / "transaction_group_plan.json", transaction_group_plan)
    append_operator_event(
        repo_root,
        event_type="transaction_group_plan_written",
        severity="info",
        stage="WORK_DECOMPOSITION",
        summary=f"Transaction group plan written: {len(transaction_group_plan.get('transaction_groups', []))} groups.",
        artifact_paths=[".codex-orchestrator/decomposition/transaction_group_plan.json"],
    )
    per_file: dict[str, int] = {}
    for patchlet in patchlet_plan.get("patchlets", []):
        path = patchlet["allowed_product_runtime_file"]
        per_file[path] = per_file.get(path, 0) + 1
    same_file = {path: count for path, count in per_file.items() if count > 1}
    plan = {
        "schema_version": "1.0",
        "kind": "work_decomposition_plan",
        "workflow_id": master_prompt_frozen.get("workflow_id") or proof_obligations.get("workflow_id"),
        "run_id": master_prompt_frozen.get("run_id") or proof_obligations.get("run_id"),
        "master_prompt_sha256": master_prompt_frozen.get("sha256") or proof_obligations.get("master_prompt_sha256"),
        "goal_interpretation_path": ".codex-orchestrator/goal_interpretation.json",
        "proof_obligations_path": ".codex-orchestrator/proof_obligations.json",
        "inventory_graph_path": ".codex-orchestrator/inventory_graph.json",
        "default_patchlet_timeout_seconds": timeout_seconds,
        "decomposition_strategy": "small_bounded_work_slices",
        "one_allowed_file_per_patchlet": True,
        "multiple_patchlets_per_file_allowed": True,
        "avoid_memory_compacting": True,
        "work_slice_count": len(work_slices.get("slices", [])),
        "patchlet_count": len(patchlet_plan.get("patchlets", [])),
        "transaction_group_count": len(transaction_group_plan.get("transaction_groups", [])),
        "operator_summary": (
            f"Work was decomposed into {len(work_slices.get('slices', []))} bounded patchlets "
            f"across {len(per_file)} files."
        ),
        "risk_summary": {
            "large_patchlet_risk": False,
            "multi_file_patchlet_risk": False,
            "dependency_cycle_risk": bool(dependency_graph.get("has_cycles")),
        },
        "per_file_patchlet_counts": dict(sorted(per_file.items())),
        "same_file_multi_patchlet_groups": same_file,
    }
    validate_work_decomposition_plan(plan)
    write_json(decomp_dir / "work_decomposition_plan.json", plan)
    append_operator_event(
        repo_root,
        event_type="work_decomposition_planned",
        severity="info",
        stage="WORK_DECOMPOSITION",
        summary=(
            f"decomposition planned: {plan['work_slice_count']} work slices -> "
            f"{plan['patchlet_count']} patchlets across {len(per_file)} files."
        ),
        artifact_paths=[".codex-orchestrator/decomposition/work_decomposition_plan.json"],
        details=summarize_work_decomposition(plan),
    )
    return plan


def validate_work_decomposition_plan(plan: dict[str, Any]) -> None:
    if plan.get("one_allowed_file_per_patchlet") is not True:
        raise ValueError("work decomposition must enforce one allowed file per patchlet")
    if plan.get("multiple_patchlets_per_file_allowed") is not True:
        raise ValueError("work decomposition must allow multiple patchlets per file")
    if int(plan.get("default_patchlet_timeout_seconds") or 0) <= 0:
        raise ValueError("default_patchlet_timeout_seconds must be positive")


def summarize_work_decomposition(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "work_slice_count": plan.get("work_slice_count", 0),
        "patchlet_count": plan.get("patchlet_count", 0),
        "transaction_group_count": plan.get("transaction_group_count", 0),
        "same_file_multi_patchlet_groups": plan.get("same_file_multi_patchlet_groups", {}),
        "decomposition_plan_path": ".codex-orchestrator/decomposition/work_decomposition_plan.json",
    }
