from __future__ import annotations

import json

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import TargetRepoContext


def _load_evidence(ctx: TargetRepoContext) -> list[dict]:
    if not ctx.paths.search_evidence_jsonl.exists():
        return []
    return [json.loads(line) for line in ctx.paths.search_evidence_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_inventory(ctx: TargetRepoContext) -> dict:
    evidence = _load_evidence(ctx)
    nodes = []
    for idx, row in enumerate([r for r in evidence if r.get("file")], start=1):
        nodes.append({
            "id": f"N{idx:03d}",
            "file": row["file"],
            "symbol": row.get("symbol"),
            "role": row.get("role", "runtime_boundary"),
            "evidence_ids": [row["evidence_id"]],
            "confidence": row.get("confidence", "medium"),
        })
    edges = []
    for idx in range(len(nodes) - 1):
        edge_evidence_ids = sorted(set(nodes[idx]["evidence_ids"] + nodes[idx + 1]["evidence_ids"]))
        edges.append({
            "id": f"EDGE{idx + 1:03d}",
            "from": nodes[idx]["id"],
            "to": nodes[idx + 1]["id"],
            "kind": "related_to",
            "evidence_ids": edge_evidence_ids,
            "confidence": "medium",
        })
    graph = {
        "schema_version": "1.0",
        "kind": "inventory_graph",
        "nodes": nodes,
        "edges": edges,
    }
    write_json(ctx.paths.inventory_graph, graph)
    table = ["# Inventory Table", "", "| Node | Role | File | Evidence | Confidence |", "|---|---|---|---|---|"]
    for node in nodes:
        table.append(f"| {node['id']} | {node['role']} | {node['file']} | {','.join(node['evidence_ids'])} | {node['confidence']} |")
    ctx.paths.inventory_table.write_text("\n".join(table) + "\n", encoding="utf-8")

    goal = read_json(ctx.paths.goal_spec) if ctx.paths.goal_spec.exists() else {"success_goals": [{"goal_id": "G001"}]}
    goal_id = goal.get("success_goals", [{"goal_id": "G001"}])[0].get("goal_id", "G001")
    evidence_ids = sorted({evidence_id for node in nodes for evidence_id in node["evidence_ids"]})
    write_json(ctx.paths.path_mapping, {
        "schema_version": "1.0",
        "kind": "path_mapping",
        "goal_mappings": [{
            "goal_id": goal_id,
            "graph_node_ids": [n["id"] for n in nodes],
            "graph_edge_ids": [edge["id"] for edge in edges],
            "evidence_ids": evidence_ids,
        }],
    })

    state = load_state(ctx)
    transition(ctx, state, "INVENTORY_READY", reason="inventory graph built")
    return graph
