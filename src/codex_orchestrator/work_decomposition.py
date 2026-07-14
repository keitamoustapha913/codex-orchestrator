from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.impact_analysis import build_impact_dependency_analysis, write_impact_dependency_analysis
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.patchlet_planner import (
    build_dependency_graph_from_patchlet_plan,
    build_patchlet_plan,
    build_transaction_group_plan,
)
from codex_orchestrator.work_slice_planner import plan_work_slices


def _probe_ids_by_obligation(probe_plan: dict[str, Any]) -> dict[str, list[str]]:
    by_obligation: dict[str, list[str]] = {}
    for probe in probe_plan.get("probes", []):
        probe_id = probe.get("probe_id")
        if not probe_id:
            continue
        for obligation_id in probe.get("obligation_ids", []):
            by_obligation.setdefault(str(obligation_id), []).append(str(probe_id))
    return {key: sorted(set(value)) for key, value in by_obligation.items()}


def _row_symbol(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        for key in ("symbol", "function", "boundary", "key"):
            if metadata.get(key):
                return str(metadata[key])
    for key in ("subject", "claim", "expected"):
        value = str(row.get(key, ""))
        if "=" in value:
            return value.split("=", 1)[0].split()[-1].strip("` ")
    return str(row.get("subject")) if row.get("subject") else None


def _row_expected(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        for key in ("expected_observation", "expected", "expected_value"):
            if metadata.get(key) is not None:
                return str(metadata[key])
    expected = row.get("expected")
    if expected is not None:
        text = str(expected)
        return text.split("=", 1)[1] if "=" in text else text
    return None


def _mapping_result(
    *,
    workflow_root: Path,
    impact: dict[str, Any],
    proof_obligations: dict[str, Any],
    goal_interpretation: dict[str, Any],
) -> dict[str, Any]:
    probe_path = workflow_root / "probe_plan.json"
    probe_plan = read_json(probe_path) if probe_path.exists() else {"probes": []}
    probes_by_obligation = _probe_ids_by_obligation(probe_plan)
    candidates = impact.get("candidate_files", [])
    required_goal_ids = [
        row["goal_item_id"]
        for row in goal_interpretation.get("goal_items", [])
        if row.get("required") is True and row.get("goal_item_id")
    ]
    required_obligation_ids = [
        row["obligation_id"]
        for row in proof_obligations.get("obligations", [])
        if row.get("required") is True and row.get("obligation_id")
    ]
    candidate_hits_by_goal: dict[str, list[str]] = {goal_id: [] for goal_id in required_goal_ids}
    candidate_hits_by_obligation: dict[str, list[str]] = {oid: [] for oid in required_obligation_ids}
    positive_mappings: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        path = str(candidate["path"])
        goal_ids = list(candidate.get("goal_item_ids", []))
        obligation_ids = list(candidate.get("proof_obligation_ids", []))
        probe_ids = sorted({pid for oid in obligation_ids for pid in probes_by_obligation.get(oid, [])})
        for goal_id in goal_ids:
            candidate_hits_by_goal.setdefault(goal_id, []).append(path)
        for obligation_id in obligation_ids:
            candidate_hits_by_obligation.setdefault(obligation_id, []).append(path)
        row = {
            "file": path,
            "goal_item_ids": goal_ids,
            "proof_obligation_ids": obligation_ids,
            "probe_ids": probe_ids,
            "inventory_node_ids": candidate.get("inventory_node_ids", []),
        }
        candidate_rows.append(
            {
                **row,
                "positive_file_link_evidence": bool(goal_ids or obligation_ids),
            }
        )
        if goal_ids or obligation_ids:
            positive_mappings.append(
                {
                    **row,
                    "match_evidence": {
                        "goal_items": candidate.get("goal_match_evidence", {}),
                        "proof_obligations": candidate.get("obligation_match_evidence", {}),
                    },
                }
            )
        else:
            unmatched.append({**row, "reason": "no positive slice evidence", "work_assigned": 0})
    ambiguous_goal_item_ids = sorted(goal_id for goal_id, paths in candidate_hits_by_goal.items() if len(set(paths)) > 1)
    ambiguous_obligation_ids = sorted(oid for oid, paths in candidate_hits_by_obligation.items() if len(set(paths)) > 1)
    mapped_goal_ids = sorted({goal_id for mapping in positive_mappings for goal_id in mapping["goal_item_ids"]})
    mapped_obligation_ids = sorted({oid for mapping in positive_mappings for oid in mapping["proof_obligation_ids"]})
    missing_probe_obligation_ids = sorted(
        oid
        for oid in mapped_obligation_ids
        if not probes_by_obligation.get(oid)
    )
    unmapped_goal_ids = sorted(set(required_goal_ids) - set(mapped_goal_ids))
    unmapped_obligation_ids = sorted(set(required_obligation_ids) - set(mapped_obligation_ids))
    errors: list[dict[str, Any]] = []
    for goal_id in unmapped_goal_ids:
        errors.append({"code": "UNMAPPED_REQUIRED_GOAL_ITEM", "goal_item_id": goal_id})
    for obligation_id in unmapped_obligation_ids:
        errors.append({"code": "UNMAPPED_REQUIRED_PROOF_OBLIGATION", "proof_obligation_id": obligation_id})
    for goal_id in ambiguous_goal_item_ids:
        errors.append({"code": "AMBIGUOUS_REQUIRED_TARGET", "goal_item_id": goal_id, "candidate_files": sorted(set(candidate_hits_by_goal.get(goal_id, [])))})
    for obligation_id in ambiguous_obligation_ids:
        errors.append({"code": "AMBIGUOUS_REQUIRED_TARGET", "proof_obligation_id": obligation_id, "candidate_files": sorted(set(candidate_hits_by_obligation.get(obligation_id, [])))})
    for obligation_id in missing_probe_obligation_ids:
        errors.append({"code": "MISSING_MANDATORY_PROBE", "proof_obligation_id": obligation_id})
    if required_obligation_ids and not positive_mappings and not errors:
        errors.append({"code": "NO_RESOLVABLE_WORK_SLICES"})
    blocking = bool(errors)
    return {
        "schema_version": "1.0",
        "kind": "file_mapping_result",
        "accepted": not blocking,
        "candidate_files": candidate_rows,
        "positive_mappings": positive_mappings,
        "unmatched_candidate_files": unmatched,
        "unmapped_goal_item_ids": unmapped_goal_ids,
        "unmapped_proof_obligation_ids": unmapped_obligation_ids,
        "ambiguous_goal_item_ids": ambiguous_goal_item_ids,
        "ambiguous_proof_obligation_ids": ambiguous_obligation_ids,
        "missing_probe_obligation_ids": missing_probe_obligation_ids,
        "probes_by_obligation": probes_by_obligation,
        "errors": errors,
    }


def _apply_positive_mapping_to_impact(
    *,
    impact: dict[str, Any],
    mapping: dict[str, Any],
    proof_obligations: dict[str, Any],
    goal_interpretation: dict[str, Any],
) -> dict[str, Any]:
    goals_by_id = {row.get("goal_item_id"): row for row in goal_interpretation.get("goal_items", [])}
    obligations_by_id = {row.get("obligation_id"): row for row in proof_obligations.get("obligations", [])}
    mapping_by_file = {row["file"]: row for row in mapping.get("positive_mappings", [])}
    candidate_files: list[dict[str, Any]] = []
    for candidate in impact.get("candidate_files", []):
        positive = mapping_by_file.get(candidate["path"])
        if not positive:
            continue
        updated = dict(candidate)
        updated["goal_item_ids"] = positive["goal_item_ids"]
        updated["proof_obligation_ids"] = positive["proof_obligation_ids"]
        updated["probe_ids"] = positive["probe_ids"]
        updated["probes_by_obligation"] = {
            oid: mapping.get("probes_by_obligation", {}).get(oid, [])
            for oid in positive["proof_obligation_ids"]
        }
        updated["goal_items_by_id"] = {gid: goals_by_id.get(gid, {}) for gid in positive["goal_item_ids"]}
        updated["proof_obligations_by_id"] = {oid: obligations_by_id.get(oid, {}) for oid in positive["proof_obligation_ids"]}
        candidate_files.append(updated)
    return {**impact, "candidate_files": candidate_files}


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
    mapping = _mapping_result(
        workflow_root=workflow_root,
        impact=impact,
        proof_obligations=proof_obligations,
        goal_interpretation=goal_interpretation,
    )
    decomp_dir = workflow_root / "decomposition"
    write_json(decomp_dir / "file_mapping_result.json", mapping)
    if mapping.get("accepted") is True:
        impact = _apply_positive_mapping_to_impact(
            impact=impact,
            mapping=mapping,
            proof_obligations=proof_obligations,
            goal_interpretation=goal_interpretation,
        )
    else:
        impact = {**impact, "candidate_files": []}
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
    write_json(decomp_dir / "work_slices.json", work_slices)
    boundary_count = sum(1 for row in work_slices.get("slices", []) if row.get("slice_change_boundary"))
    append_operator_event(
        repo_root,
        event_type="work_slices_written",
        severity="info",
        stage="WORK_DECOMPOSITION",
        summary=f"Work slices written: {len(work_slices.get('slices', []))}.",
        artifact_paths=[".codex-orchestrator/decomposition/work_slices.json"],
    )
    if boundary_count:
        append_operator_event(
            repo_root,
            event_type="slice_boundary_planned",
            severity="info",
            stage="WORK_DECOMPOSITION",
            summary=f"Slice change boundaries planned: {boundary_count}.",
            artifact_paths=[".codex-orchestrator/decomposition/work_slices.json"],
            details={"slice_change_boundary_count": boundary_count},
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
