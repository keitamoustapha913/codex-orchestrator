from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from codex_orchestrator.codex_execution_policy import resolve_patchlet_timeout_seconds


def _default_timeout(default_patchlet_timeout_seconds: int | None = None) -> int:
    if default_patchlet_timeout_seconds:
        return int(default_patchlet_timeout_seconds)
    return resolve_patchlet_timeout_seconds(os.environ)


def _goal_ids(candidate: dict[str, Any]) -> list[str]:
    return list(candidate.get("goal_item_ids") or ["GI001"])


def _obligation_ids(candidate: dict[str, Any]) -> list[str]:
    return list(candidate.get("proof_obligation_ids") or ["PO001"])


def _slice_title(path: str, slice_type: str) -> str:
    labels = {
        "entrypoint_wiring": "Update entrypoint wiring for requested behavior",
        "final_integration_adjustment": "Finalize entrypoint integration for requested behavior",
        "business_logic_change": "Implement narrow business behavior change",
        "validation_adjustment": "Add validation branch for requested behavior",
        "formatting_adjustment": "Adjust formatting behavior for requested output",
        "configuration_adjustment": "Set configuration value for requested behavior",
        "dependency_bridge": "Align dependency bridge for requested behavior",
        "runtime_behavior_change": "Update runtime behavior for requested outcome",
    }
    return f"{labels.get(slice_type, 'Update requested behavior')} in {path}"


def _desired_slice_types(candidate: dict[str, Any], *, single_simple_file: bool) -> list[str]:
    types = list(dict.fromkeys(candidate.get("suggested_slice_types") or ["runtime_behavior_change"]))
    if single_simple_file:
        if len(types) > 1 and any(t in types for t in {"validation_adjustment", "formatting_adjustment", "dependency_bridge", "final_integration_adjustment"}):
            return types
        return [types[0]]
    if candidate.get("risk_level") == "high" and len(types) == 1:
        types = [types[0], "final_integration_adjustment"]
    return types


def _topological_file_order(impact_analysis: dict[str, Any]) -> list[str]:
    files = sorted(row["path"] for row in impact_analysis.get("candidate_files", []))
    deps: dict[str, set[str]] = {path: set() for path in files}
    for edge in impact_analysis.get("dependency_edges", []):
        if edge.get("from_file") in deps and edge.get("to_file") in deps:
            deps[edge["to_file"]].add(edge["from_file"])
    ordered: list[str] = []
    pending = set(files)
    while pending:
        ready = sorted(path for path in pending if not (deps[path] & pending))
        if not ready:
            ordered.extend(sorted(pending))
            break
        for path in ready:
            ordered.append(path)
            pending.remove(path)
    return ordered


def plan_work_slices(
    *,
    impact_analysis: dict[str, Any],
    proof_obligations: dict[str, Any],
    default_patchlet_timeout_seconds: int | None = None,
    max_slices_per_file: int | None = None,
) -> dict[str, Any]:
    timeout = _default_timeout(default_patchlet_timeout_seconds)
    candidates_by_path = {row["path"]: row for row in impact_analysis.get("candidate_files", [])}
    order = _topological_file_order(impact_analysis)
    single_simple_file = len(order) <= 1
    slices: list[dict[str, Any]] = []
    last_slice_for_file: dict[str, str] = {}
    last_slice_by_path: dict[str, str] = {}
    for path in order:
        candidate = candidates_by_path[path]
        slice_types = _desired_slice_types(candidate, single_simple_file=single_simple_file)
        if max_slices_per_file is not None:
            slice_types = slice_types[:max_slices_per_file]
        previous_for_same_file: str | None = None
        for slice_type in slice_types:
            work_slice_id = f"WS{len(slices) + 1:03d}"
            depends = []
            for dependency_file in candidate.get("dependency_inputs", []):
                dep_slice = last_slice_by_path.get(dependency_file)
                if dep_slice and dep_slice not in depends:
                    depends.append(dep_slice)
            if previous_for_same_file and previous_for_same_file not in depends:
                depends.append(previous_for_same_file)
            forbidden = sorted(p for p in candidates_by_path if p != path)
            context_files = sorted(set([path] + list(candidate.get("dependency_inputs", [])) + list(candidate.get("dependency_outputs", []))))
            slices.append(
                {
                    "work_slice_id": work_slice_id,
                    "title": _slice_title(path, slice_type),
                    "allowed_product_runtime_file": path,
                    "slice_type": slice_type,
                    "scope_statement": f"Only update {slice_type.replace('_', ' ')} in {path}; do not edit any other product/runtime file.",
                    "goal_item_ids": _goal_ids(candidate),
                    "proof_obligation_ids": _obligation_ids(candidate),
                    "inventory_node_ids": list(candidate.get("inventory_node_ids", [])),
                    "depends_on_work_slice_ids": depends,
                    "risk_level": candidate.get("risk_level", "low"),
                    "estimated_complexity": "small",
                    "time_budget_seconds": timeout,
                    "budget_source": "CODEX_PATCHLET_TIMEOUT_SECONDS" if os.environ.get("CODEX_PATCHLET_TIMEOUT_SECONDS") else "default_600_seconds",
                    "scope_size": "single_product_runtime_file",
                    "memory_compacting_required": False,
                    "budget_fit_assessment": {
                        "fits_default_600_seconds": timeout <= 600,
                        "reason": "One allowed edit file, narrow slice scope, and local proof requirement.",
                    },
                    "prompt_scope": {
                        "allowed_context_files": context_files,
                        "allowed_edit_file": path,
                        "forbidden_edit_files": forbidden,
                        "must_include": [
                            "proof obligation " + ", ".join(_obligation_ids(candidate)),
                            "local probe requirement",
                            "single-file edit boundary",
                        ],
                        "must_exclude": [
                            "whole-repo refactor",
                            "multi-file edit",
                            "open-ended exploration",
                        ],
                        "memory_compacting_required": False,
                    },
                    "acceptance_summary": f"{path} satisfies this bounded slice without editing other product/runtime files.",
                }
            )
            previous_for_same_file = work_slice_id
            last_slice_for_file[path] = work_slice_id
            last_slice_by_path[path] = work_slice_id
    return {
        "schema_version": "1.0",
        "kind": "work_slices",
        "workflow_id": impact_analysis.get("workflow_id"),
        "run_id": impact_analysis.get("run_id"),
        "slices": slices,
        "per_file_slice_counts": dict(sorted(defaultdict(int, {p: len([s for s in slices if s["allowed_product_runtime_file"] == p]) for p in candidates_by_path}).items())),
        "required_proof_obligation_ids": [row.get("obligation_id") for row in proof_obligations.get("obligations", []) if row.get("obligation_id")],
    }
