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


def _key_value_rows(candidate: dict[str, Any]) -> dict[str, dict[str, str]]:
    rows = candidate.get("text_key_value_state") or []
    if not rows and candidate.get("content"):
        for line in str(candidate.get("content", "")).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            rows.append({"key": key.strip(), "value": value.strip(), "line": stripped})
    return {str(row.get("key")): row for row in rows if row.get("key")}


def _desired_changes(candidate: dict[str, Any], proof_obligations: dict[str, Any]) -> list[dict[str, Any]]:
    planned = list(candidate.get("desired_key_value_changes") or [])
    if planned:
        return planned
    by_id = {row.get("obligation_id"): row for row in proof_obligations.get("obligations", [])}
    desired: list[dict[str, Any]] = []
    for obligation_id in _obligation_ids(candidate):
        obligation = by_id.get(obligation_id, {})
        text = " ".join(str(obligation.get(key, "")) for key in ("claim", "description", "expected"))
        for token in text.replace(",", " ").replace(";", " ").split():
            if "=" not in token:
                continue
            key, value = token.strip("`.").split("=", 1)
            if key and value:
                desired.append(
                    {
                        "key": key,
                        "new_value": value.rstrip("."),
                        "proof_obligation_ids": [obligation_id],
                        "goal_item_ids": list(obligation.get("goal_item_ids", [])),
                    }
                )
                break
    return desired


def _slice_boundaries(candidate: dict[str, Any], proof_obligations: dict[str, Any]) -> list[dict[str, Any]]:
    old_by_key = _key_value_rows(candidate)
    desired = _desired_changes(candidate, proof_obligations)
    future_by_key = {str(row.get("key")): row for row in desired if row.get("key")}
    boundaries: list[dict[str, Any]] = []
    for idx, row in enumerate(desired, start=1):
        key = str(row.get("key", ""))
        old = old_by_key.get(key)
        new_value = str(row.get("new_value", ""))
        if not key or not old or not new_value:
            continue
        old_value = str(old.get("value", ""))
        old_line = str(old.get("line") or f"{key}={old_value}")
        new_line = f"{key}={new_value}"
        goal_ids = list(row.get("goal_item_ids") or [])
        obligation_ids = list(row.get("proof_obligation_ids") or [])
        forbidden = [item for fkey, item in future_by_key.items() if fkey != key]
        boundaries.append(
            {
                "boundary_id": f"SCB{idx:03d}",
                "boundary_type": "text_key_value_update",
                "allowed_product_runtime_file": candidate["path"],
                "goal_item_ids": goal_ids,
                "proof_obligation_ids": obligation_ids,
                "allowed_changes": [
                    {
                        "change_id": f"CH{idx:03d}",
                        "operation": "replace_line",
                        "key": key,
                        "old_value": old_value,
                        "new_value": new_value,
                        "old_line": old_line,
                        "new_line": new_line,
                        "match_strategy": "exact_key_value_line",
                    }
                ],
                "forbidden_future_goal_item_ids": sorted(
                    {gid for item in forbidden for gid in item.get("goal_item_ids", [])}
                ),
                "forbidden_future_proof_obligation_ids": sorted(
                    {oid for item in forbidden for oid in item.get("proof_obligation_ids", [])}
                ),
                "forbidden_changes": [
                    {
                        "key": str(item.get("key")),
                        "reason": f"reserved for later patchlet",
                    }
                    for item in forbidden
                    if item.get("key")
                ],
                "allow_unrelated_whitespace_only": False,
                "allow_context_reordering": False,
            }
        )
    return boundaries


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
        boundaries = _slice_boundaries(candidate, proof_obligations)
        if boundaries and len(slice_types) < len(boundaries):
            slice_types = slice_types + [slice_types[-1] if slice_types else "runtime_behavior_change"] * (len(boundaries) - len(slice_types))
        if max_slices_per_file is not None:
            slice_types = slice_types[:max_slices_per_file]
        previous_for_same_file: str | None = None
        for slice_index, slice_type in enumerate(slice_types):
            work_slice_id = f"WS{len(slices) + 1:03d}"
            boundary = boundaries[slice_index] if slice_index < len(boundaries) else None
            goal_item_ids = list(boundary.get("goal_item_ids", [])) if boundary else _goal_ids(candidate)
            proof_obligation_ids = list(boundary.get("proof_obligation_ids", [])) if boundary else _obligation_ids(candidate)
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
                    "goal_item_ids": goal_item_ids,
                    "proof_obligation_ids": proof_obligation_ids,
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
                            "proof obligation " + ", ".join(proof_obligation_ids),
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
                    **({"slice_change_boundary": boundary} if boundary else {"boundary_enforcement_status": "BOUNDARY_UNENFORCEABLE"}),
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
