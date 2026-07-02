from __future__ import annotations

from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.extract_invariants import extract_invariants
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
    build_inventory(ctx)
    return ctx


def test_extract_invariants_links_goals_graph_nodes_and_evidence(git_repo: Path):
    ctx = _ctx(git_repo)

    invariants = extract_invariants(ctx)

    saved = read_json(ctx.paths.invariants)
    assert validate_json_file(ctx.paths.invariants, "invariant.schema.json") == []
    assert invariants[0]["master_goal_id"] == "G001"
    assert saved["invariants"][0]["graph_node_ids"]
    assert saved["invariants"][0]["evidence_ids"]


def test_invariants_include_runtime_boundary_and_probe_requirement(git_repo: Path):
    ctx = _ctx(git_repo)

    extract_invariants(ctx)

    invariant = read_json(ctx.paths.invariants)["invariants"][0]
    assert invariant["runtime_signal_or_condition"]
    assert invariant["required_probes"]


def test_invariants_include_negative_controls(git_repo: Path):
    ctx = _ctx(git_repo)

    extract_invariants(ctx)

    invariant = read_json(ctx.paths.invariants)["invariants"][0]
    assert invariant["negative_controls"]


def test_invariants_are_stable_across_rerun(git_repo: Path):
    ctx = _ctx(git_repo)

    first = read_json(ctx.paths.invariants) if ctx.paths.invariants.exists() else None
    first_invariants = extract_invariants(ctx)
    second_invariants = extract_invariants(ctx)
    second = read_json(ctx.paths.invariants)

    assert first is None or first == second or first_invariants == second_invariants
    assert first_invariants == second_invariants


def test_invariants_schema_rejects_unlinked_invariant():
    bad = {
        "schema_version": "1.0",
        "kind": "invariants",
        "invariants": [{
            "invariant_id": "I001",
            "master_goal_id": "G001",
            "description": "bad",
            "producer_nodes": [],
            "transformer_nodes": [],
            "adapter_nodes": [],
            "consumer_nodes": [],
            "state_owner_nodes": [],
            "runtime_signal_or_condition": "",
            "required_probes": [],
            "negative_controls": [],
            "regression_commands": [],
            "evidence_ids": [],
            "graph_node_ids": [],
            "graph_edge_ids": [],
        }],
    }

    errors = validate_json(bad, "invariant.schema.json")

    assert errors
