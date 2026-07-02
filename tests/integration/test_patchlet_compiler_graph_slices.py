from __future__ import annotations

from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
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
    extract_invariants(ctx)
    return ctx


def test_compile_patchlets_from_invariant_graph_slices(git_repo: Path):
    ctx = _ctx(git_repo)

    index = compile_patchlets(ctx)

    assert validate_json_file(ctx.paths.patchlet_index, "patchlet_index.schema.json") == []
    assert index["patchlets"]


def test_each_patchlet_has_exactly_one_allowed_product_runtime_file(git_repo: Path):
    ctx = _ctx(git_repo)

    index = compile_patchlets(ctx)

    for patchlet in index["patchlets"]:
        assert isinstance(patchlet["allowed_product_runtime_file"], str)
        assert patchlet["allowed_product_runtime_file"]


def test_patchlet_links_goal_invariant_evidence_and_graph_nodes(git_repo: Path):
    ctx = _ctx(git_repo)

    index = compile_patchlets(ctx)
    patchlet = index["patchlets"][0]

    assert patchlet["master_goal_ids"] == ["G001"]
    assert patchlet["invariant_ids"] == ["I001"]
    assert patchlet["evidence_ids"]
    assert patchlet["graph_node_ids"]


def test_patchlet_subprompt_contains_root_cause_probe_gate_and_tdd_checklist(git_repo: Path):
    ctx = _ctx(git_repo)

    index = compile_patchlets(ctx)
    subprompt = (ctx.root / index["patchlets"][0]["subprompt_path"]).read_text(encoding="utf-8")

    assert "ROOT-CAUSE PROBE-ONLY INVESTIGATION" in subprompt
    assert "TDD checklist" in subprompt


def test_patchlet_subprompt_requires_durable_probe_artifacts(git_repo: Path):
    ctx = _ctx(git_repo)

    index = compile_patchlets(ctx)
    subprompt = (ctx.root / index["patchlets"][0]["subprompt_path"]).read_text(encoding="utf-8")

    assert "durable probe artifacts" in subprompt
    assert "row_ledger.jsonl" in subprompt
    assert "trace_ledger.jsonl" in subprompt


def test_patchlet_compiler_is_idempotent_and_preserves_existing_statuses(git_repo: Path):
    ctx = _ctx(git_repo)

    first = compile_patchlets(ctx)
    patchlet_index = read_json(ctx.paths.patchlet_index)
    patchlet_index["patchlets"][0]["status"] = "COMPLETE"
    ctx.paths.patchlet_index.write_text(__import__("json").dumps(patchlet_index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    second = compile_patchlets(ctx)

    assert second["patchlets"][0]["status"] == "COMPLETE"


def test_patchlet_index_schema_rejects_patchlet_without_invariant_link():
    bad_index = {
        "schema_version": "1.0",
        "kind": "patchlet_index",
        "patchlets": [{
            "schema_version": "1.0",
            "kind": "patchlet",
            "patchlet_id": "P0001",
            "subprompt_path": ".codex-orchestrator/subprompts/0001_app.md",
            "master_goal_ids": ["G001"],
            "invariant_ids": [],
            "evidence_ids": ["E001"],
            "graph_node_ids": ["N001"],
            "allowed_product_runtime_file": "app.py",
            "allowed_artifact_dirs": [".artifacts/probes/", ".codex-orchestrator/reports/", ".codex-orchestrator/runs/"],
            "transaction_group_id": "TG001",
            "depends_on": [],
            "status": "PENDING",
        }],
    }

    errors = validate_json(bad_index, "patchlet_index.schema.json")

    assert errors
