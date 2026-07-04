from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


class PatchletPlanError(ValueError):
    pass


def _topological_work_slices(slices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {row["work_slice_id"]: row for row in slices}
    indegree = {row["work_slice_id"]: 0 for row in slices}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for row in slices:
        for dep in row.get("depends_on_work_slice_ids", []):
            if dep not in by_id:
                raise PatchletPlanError(f"unknown work slice dependency {dep}")
            outgoing[dep].append(row["work_slice_id"])
            indegree[row["work_slice_id"]] += 1
    ready = deque(sorted([sid for sid, count in indegree.items() if count == 0]))
    ordered: list[dict[str, Any]] = []
    while ready:
        sid = ready.popleft()
        ordered.append(by_id[sid])
        for child in sorted(outgoing.get(sid, [])):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready = deque(sorted(ready))
    if len(ordered) != len(slices):
        raise PatchletPlanError("work slice dependency cycle detected")
    return ordered


def build_patchlet_plan(
    *,
    work_slices: dict[str, Any],
    dependency_graph: dict[str, Any] | None = None,
    default_patchlet_timeout_seconds: int = 600,
) -> dict[str, Any]:
    ordered = _topological_work_slices(list(work_slices.get("slices", [])))
    slice_to_patchlet: dict[str, str] = {}
    patchlets: list[dict[str, Any]] = []
    for row in ordered:
        pid = f"P{len(patchlets) + 1:04d}"
        slice_to_patchlet[row["work_slice_id"]] = pid
        allowed_file = row.get("allowed_product_runtime_file")
        if not isinstance(allowed_file, str) or not allowed_file:
            raise PatchletPlanError(f"{row.get('work_slice_id')} missing allowed_product_runtime_file")
        patchlets.append(
            {
                "patchlet_id": pid,
                "work_slice_id": row["work_slice_id"],
                "allowed_product_runtime_file": allowed_file,
                "allowed_product_runtime_files": [allowed_file],
                "proof_obligation_ids": list(row.get("proof_obligation_ids", [])),
                "goal_item_ids": list(row.get("goal_item_ids", [])),
                "dependency_patchlet_ids": [],
                "downstream_patchlet_ids": [],
                "time_budget_seconds": int(row.get("time_budget_seconds") or default_patchlet_timeout_seconds),
                "prompt_budget_policy": {
                    "must_fit_within_timeout": True,
                    "avoid_memory_compacting": True,
                    "max_scope_files": 1,
                    "max_product_runtime_edit_files": 1,
                },
                "prompt_scope": row.get("prompt_scope", {}),
                "scope_statement": row.get("scope_statement"),
                "slice_change_boundary": row.get("slice_change_boundary"),
                "boundary_enforcement_status": row.get("boundary_enforcement_status"),
                "title": row.get("title"),
                "expected_patchlet_statuses": [
                    "COMPLETE",
                    "VERIFIED_NO_CHANGE_NEEDED",
                    "BLOCKED_WITH_EVIDENCE",
                    "FAILED_WITH_EVIDENCE",
                ],
            }
        )
    by_slice = {p["work_slice_id"]: p for p in patchlets}
    for row in ordered:
        patchlet = by_slice[row["work_slice_id"]]
        deps = [slice_to_patchlet[dep] for dep in row.get("depends_on_work_slice_ids", [])]
        patchlet["dependency_patchlet_ids"] = deps
    by_id = {p["patchlet_id"]: p for p in patchlets}
    for patchlet in patchlets:
        for dep in patchlet["dependency_patchlet_ids"]:
            by_id[dep]["downstream_patchlet_ids"].append(patchlet["patchlet_id"])
    plan = {
        "schema_version": "1.0",
        "kind": "patchlet_plan",
        "workflow_id": work_slices.get("workflow_id"),
        "run_id": work_slices.get("run_id"),
        "patchlets": patchlets,
    }
    validate_patchlet_plan(plan)
    return plan


def build_dependency_graph_from_patchlet_plan(patchlet_plan: dict[str, Any]) -> dict[str, Any]:
    patchlets = patchlet_plan.get("patchlets", [])
    nodes = [
        {
            "node_id": row["patchlet_id"],
            "node_type": "patchlet",
            "work_slice_id": row.get("work_slice_id"),
            "allowed_product_runtime_file": row.get("allowed_product_runtime_file"),
        }
        for row in patchlets
    ]
    edges = [
        {
            "from": dep,
            "to": row["patchlet_id"],
            "edge_type": "must_complete_before",
            "reason": f"{row['patchlet_id']} depends on {dep}.",
        }
        for row in patchlets
        for dep in row.get("dependency_patchlet_ids", [])
    ]
    order, has_cycles = _topological_patchlet_order(patchlets)
    return {
        "schema_version": "1.0",
        "kind": "decomposition_dependency_graph",
        "workflow_id": patchlet_plan.get("workflow_id"),
        "run_id": patchlet_plan.get("run_id"),
        "nodes": nodes,
        "edges": edges,
        "has_cycles": has_cycles,
        "topological_order": order,
    }


def _topological_patchlet_order(patchlets: list[dict[str, Any]]) -> tuple[list[str], bool]:
    by_id = {row["patchlet_id"]: row for row in patchlets}
    indegree = {pid: 0 for pid in by_id}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for row in patchlets:
        for dep in row.get("dependency_patchlet_ids", []):
            if dep not in by_id:
                raise PatchletPlanError(f"unknown patchlet dependency {dep}")
            outgoing[dep].append(row["patchlet_id"])
            indegree[row["patchlet_id"]] += 1
    ready = deque(sorted([pid for pid, count in indegree.items() if count == 0]))
    order: list[str] = []
    while ready:
        pid = ready.popleft()
        order.append(pid)
        for child in sorted(outgoing.get(pid, [])):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready = deque(sorted(ready))
    return order, len(order) != len(patchlets)


def build_transaction_group_plan(patchlet_plan: dict[str, Any], dependency_graph: dict[str, Any]) -> dict[str, Any]:
    by_id = {row["patchlet_id"]: row for row in patchlet_plan.get("patchlets", [])}
    layers: list[list[str]] = []
    assigned: set[str] = set()
    topo = dependency_graph.get("topological_order", [])
    while len(assigned) < len(topo):
        layer: list[str] = []
        used_files: set[str] = set()
        for pid in topo:
            if pid in assigned:
                continue
            patchlet = by_id[pid]
            deps = set(patchlet.get("dependency_patchlet_ids", []))
            if not deps.issubset(assigned):
                continue
            allowed_file = patchlet.get("allowed_product_runtime_file")
            if allowed_file in used_files:
                continue
            layer.append(pid)
            used_files.add(allowed_file)
        if not layer:
            raise PatchletPlanError("dependency cycle blocks transaction group planning")
        assigned.update(layer)
        layers.append(layer)
    groups = []
    for idx, layer in enumerate(layers, start=1):
        group_patchlets = [by_id[pid] for pid in layer]
        deps = sorted({dep for row in group_patchlets for dep in row.get("dependency_patchlet_ids", []) if dep not in layer})
        groups.append(
            {
                "transaction_group_id": f"TG{idx:03d}",
                "patchlet_ids": layer,
                "goal_item_ids": sorted({gid for row in group_patchlets for gid in row.get("goal_item_ids", [])}),
                "proof_obligation_ids": sorted({oid for row in group_patchlets for oid in row.get("proof_obligation_ids", [])}),
                "dependency_patchlet_ids": deps,
                "group_type": "dependency_layer",
                "can_run_after": [f"TG{idx - 1:03d}"] if idx > 1 else [],
                "operator_summary": f"Dependency layer {idx} with {len(layer)} patchlets.",
            }
        )
    return {
        "schema_version": "1.0",
        "kind": "transaction_group_plan",
        "workflow_id": patchlet_plan.get("workflow_id"),
        "run_id": patchlet_plan.get("run_id"),
        "transaction_groups": groups,
    }


def validate_patchlet_plan(plan: dict[str, Any]) -> None:
    ids = {row.get("patchlet_id") for row in plan.get("patchlets", [])}
    for row in plan.get("patchlets", []):
        files = row.get("allowed_product_runtime_files")
        if files is not None and len(files) != 1:
            raise PatchletPlanError(f"{row.get('patchlet_id')} must have exactly one allowed product/runtime file")
        if not row.get("allowed_product_runtime_file"):
            raise PatchletPlanError(f"{row.get('patchlet_id')} missing allowed_product_runtime_file")
        if int(row.get("time_budget_seconds") or 0) <= 0:
            raise PatchletPlanError(f"{row.get('patchlet_id')} missing positive time_budget_seconds")
        for dep in row.get("dependency_patchlet_ids", []):
            if dep not in ids:
                raise PatchletPlanError(f"{row.get('patchlet_id')} depends on unknown {dep}")
    graph = build_dependency_graph_from_patchlet_plan(plan)
    if graph["has_cycles"]:
        raise PatchletPlanError("patchlet dependency cycle detected")
