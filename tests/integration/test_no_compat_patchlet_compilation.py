from __future__ import annotations

from pathlib import Path

import pytest

from conftest import read_json, run

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.target_repo import resolve_target_repo


def _ctx(repo: Path):
    (repo / "service.txt").write_text("before\n", encoding="utf-8")
    (repo / "master_prompt.md").write_text("Change service behavior and prove it.\n", encoding="utf-8")
    run(["git", "add", "service.txt", "master_prompt.md"], repo)
    run(["git", "commit", "-m", "compile setup"], repo)
    ctx = resolve_target_repo(repo=repo)
    init_workflow(ctx, master=repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_json(
        ctx.paths.workflow_dir / "provability/provability_result.json",
        {
            "schema_version": "1.0",
            "kind": "provability_result",
            "master_prompt_sha256": "0" * 64,
            "provability_status": "PROVABLE",
            "can_start_product_patchlets": True,
        },
    )
    write_json(ctx.paths.invariants, {"schema_version": "1.0", "kind": "invariants", "invariants": []})
    return ctx


def _write_decomposition(ctx, patchlets):
    d = ctx.paths.workflow_dir / "decomposition"
    write_json(d / "impact_dependency_analysis.json", {"schema_version": "1.0", "kind": "impact_dependency_analysis", "candidate_files": []})
    write_json(d / "work_decomposition_plan.json", {"schema_version": "1.0", "kind": "work_decomposition_plan", "one_allowed_file_per_patchlet": True, "multiple_patchlets_per_file_allowed": True, "default_patchlet_timeout_seconds": 600})
    write_json(d / "work_slices.json", {"schema_version": "1.0", "kind": "work_slices", "slices": []})
    write_json(d / "patchlet_plan.json", {"schema_version": "1.0", "kind": "patchlet_plan", "patchlets": patchlets})
    write_json(d / "dependency_graph.json", {"schema_version": "1.0", "kind": "decomposition_dependency_graph", "nodes": [], "edges": [], "has_cycles": False, "topological_order": [p["patchlet_id"] for p in patchlets]})
    write_json(d / "transaction_group_plan.json", {"schema_version": "1.0", "kind": "transaction_group_plan", "transaction_groups": [{"transaction_group_id": "TG001", "patchlet_ids": [p["patchlet_id"] for p in patchlets]}]})


def test_compile_patchlets_requires_patchlet_plan(git_repo: Path):
    ctx = _ctx(git_repo)
    with pytest.raises(RuntimeError, match="missing required decomposition artifacts"):
        compile_patchlets(ctx)
    assert read_json(ctx.paths.patchlet_index)["patchlets"] == []


def test_compile_patchlets_from_patchlet_plan(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_decomposition(
        ctx,
        [
            {
                "patchlet_id": "P0001",
                "work_slice_id": "WS001",
                "allowed_product_runtime_file": "service.txt",
                "allowed_product_runtime_files": ["service.txt"],
                "goal_item_ids": ["GI001"],
                "proof_obligation_ids": ["PO001"],
                "dependency_patchlet_ids": [],
                "downstream_patchlet_ids": [],
                "time_budget_seconds": 600,
                "prompt_budget_policy": {"must_fit_within_timeout": True, "avoid_memory_compacting": True, "max_product_runtime_edit_files": 1},
            }
        ],
    )
    index = compile_patchlets(ctx)
    assert index["patchlets"][0]["work_slice_id"] == "WS001"
    assert index["patchlets"][0]["allowed_product_runtime_files"] == ["service.txt"]


def test_patchlet_index_rejects_multiple_allowed_files(git_repo: Path):
    ctx = _ctx(git_repo)
    _write_decomposition(
        ctx,
        [
            {
                "patchlet_id": "P0001",
                "work_slice_id": "WS001",
                "allowed_product_runtime_file": "service.txt",
                "allowed_product_runtime_files": ["service.txt", "other.txt"],
                "time_budget_seconds": 600,
                "dependency_patchlet_ids": [],
            }
        ],
    )
    with pytest.raises(Exception, match="exactly one allowed product/runtime file"):
        compile_patchlets(ctx)


def test_multiple_patchlets_same_allowed_file_is_valid(git_repo: Path):
    ctx = _ctx(git_repo)
    base = {
        "allowed_product_runtime_file": "service.txt",
        "allowed_product_runtime_files": ["service.txt"],
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        "time_budget_seconds": 600,
        "prompt_budget_policy": {"must_fit_within_timeout": True, "avoid_memory_compacting": True, "max_product_runtime_edit_files": 1},
    }
    _write_decomposition(
        ctx,
        [
            {"patchlet_id": "P0001", "work_slice_id": "WS001", "dependency_patchlet_ids": [], "downstream_patchlet_ids": ["P0002"], **base},
            {"patchlet_id": "P0002", "work_slice_id": "WS002", "dependency_patchlet_ids": ["P0001"], "downstream_patchlet_ids": [], **base},
        ],
    )
    index = compile_patchlets(ctx)
    assert [p["allowed_product_runtime_file"] for p in index["patchlets"]] == ["service.txt", "service.txt"]
    assert index["patchlets"][1]["dependency_patchlet_ids"] == ["P0001"]
