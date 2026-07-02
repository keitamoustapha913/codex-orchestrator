from __future__ import annotations

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import TargetRepoContext


def extract_invariants(ctx: TargetRepoContext) -> list[dict]:
    graph = read_json(ctx.paths.inventory_graph) if ctx.paths.inventory_graph.exists() else {"nodes": [], "edges": []}
    goal = read_json(ctx.paths.goal_spec) if ctx.paths.goal_spec.exists() else {"success_goals": [{"goal_id": "G001"}]}
    path_mapping = read_json(ctx.paths.path_mapping) if ctx.paths.path_mapping.exists() else {
        "goal_mappings": [{"goal_id": "G001", "graph_node_ids": [], "graph_edge_ids": [], "evidence_ids": []}]
    }
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    goal_mapping = path_mapping.get("goal_mappings", [{"goal_id": "G001", "graph_node_ids": [], "graph_edge_ids": [], "evidence_ids": []}])[0]
    node_ids = goal_mapping.get("graph_node_ids", []) or [node["id"] for node in nodes]
    edge_ids = goal_mapping.get("graph_edge_ids", []) or [edge["id"] for edge in edges]
    evidence_ids = goal_mapping.get("evidence_ids", []) or sorted({eid for node in nodes for eid in node.get("evidence_ids", [])})
    runtime_file = next((node.get("file") for node in nodes if node.get("id") in node_ids and node.get("file")), None)
    invariant = {
        "schema_version": "1.0",
        "kind": "invariant",
        "invariant_id": "I001",
        "master_goal_id": goal_mapping.get("goal_id") or goal.get("success_goals", [{"goal_id": "G001"}])[0].get("goal_id", "G001"),
        "description": "Master goal behavior must be proven at the direct runtime boundary before any implementation is accepted.",
        "producer_nodes": node_ids[:1],
        "transformer_nodes": [],
        "adapter_nodes": [],
        "consumer_nodes": node_ids[1:],
        "state_owner_nodes": node_ids[:1],
        "runtime_signal_or_condition": f"Direct probe observes {runtime_file or 'the target runtime boundary'} deterministically.",
        "required_probes": ["minimal_direct_runtime_probe"],
        "negative_controls": ["unrelated file/control path remains unchanged"],
        "regression_commands": [],
        "evidence_ids": evidence_ids,
        "graph_node_ids": node_ids,
        "graph_edge_ids": edge_ids,
    }
    document = {
        "schema_version": "1.0",
        "kind": "invariants",
        "invariants": [invariant],
    }
    write_json(ctx.paths.invariants, document)
    state = load_state(ctx)
    transition(ctx, state, "INVARIANTS_READY", reason="invariants extracted")
    return [invariant]
