from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json, validate_json_file


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    return ctx


def test_build_inventory_generates_schema_valid_graph_nodes_from_evidence(git_repo: Path):
    ctx = _ctx(git_repo)

    graph = build_inventory(ctx)

    assert validate_json_file(ctx.paths.inventory_graph, "inventory_graph.schema.json") == []
    assert graph["nodes"]
    for node in graph["nodes"]:
        assert node["evidence_ids"]


def test_inventory_table_is_generated_from_graph(git_repo: Path):
    ctx = _ctx(git_repo)

    graph = build_inventory(ctx)
    table = ctx.paths.inventory_table.read_text(encoding="utf-8")

    assert "| Node | Role | File | Evidence | Confidence |" in table
    for node in graph["nodes"]:
        assert node["id"] in table
        assert node["file"] in table


def test_path_mapping_links_goals_to_graph_nodes_and_evidence(git_repo: Path):
    ctx = _ctx(git_repo)

    build_inventory(ctx)

    mapping = read_json(ctx.paths.path_mapping)
    assert validate_json_file(ctx.paths.path_mapping, "path_mapping.schema.json") == []
    goal_mapping = mapping["goal_mappings"][0]
    assert goal_mapping["goal_id"] == "G001"
    assert goal_mapping["graph_node_ids"]
    assert goal_mapping["evidence_ids"]


def test_inventory_graph_ids_are_stable_across_rerun(git_repo: Path):
    ctx = _ctx(git_repo)

    first_graph = build_inventory(ctx)
    second_graph = build_inventory(ctx)

    assert first_graph == second_graph


def test_inventory_graph_rejects_node_without_evidence_link():
    bad_graph = {
        "schema_version": "1.0",
        "kind": "inventory_graph",
        "nodes": [{
            "id": "N001",
            "file": "app.py",
            "symbol": None,
            "role": "producer",
            "evidence_ids": [],
            "confidence": "high",
        }],
        "edges": [],
    }

    errors = validate_json(bad_graph, "inventory_graph.schema.json")

    assert errors
