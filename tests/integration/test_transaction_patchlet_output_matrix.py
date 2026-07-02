from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.stages.verify_group import verify_group
from codex_orchestrator.target_repo import resolve_target_repo


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def test_verify_group_writes_patchlet_output_matrix(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")

    result = verify_group(ctx, transaction_group_id="TG001")

    assert Path(result["patchlet_output_matrix"]).exists()


def test_patchlet_output_matrix_links_reports_probes_diffs_and_wrapper_gates(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")

    result = verify_group(ctx, transaction_group_id="TG001")
    matrix = read_json(Path(result["patchlet_output_matrix"]))
    row = matrix["patchlets"][0]

    assert row["report_valid"] is True
    assert row["probe_valid"] is True
    assert row["allowed_diff_valid"] is True
    assert row["wrapper_gate_accepted"] is True


def test_patchlet_output_matrix_records_contradictions(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    gate_path = ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json"
    gate = read_json(gate_path)
    gate["accepted"] = False
    gate_path.write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_group(ctx, transaction_group_id="TG001")
    matrix = read_json(Path(result["patchlet_output_matrix"]))

    assert "wrapper_gate_not_accepted" in matrix["patchlets"][0]["contradictions"]


def test_group_gate_result_blocks_when_matrix_has_contradictions(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    gate_path = ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json"
    gate = read_json(gate_path)
    gate["accepted"] = False
    gate_path.write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_group(ctx, transaction_group_id="TG001")
    gate_result = read_json(Path(result["group_gate_result"]))

    assert result["status"] == "FAILED"
    assert gate_result["accepted"] is False


def test_group_gate_result_passes_when_matrix_all_valid(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")

    result = verify_group(ctx, transaction_group_id="TG001")
    gate_result = read_json(Path(result["group_gate_result"]))

    assert result["status"] == "PASSED"
    assert gate_result["accepted"] is True


def test_verify_group_remains_read_only_for_product_files(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    before = (git_repo / "app.py").read_text(encoding="utf-8")

    verify_group(ctx, transaction_group_id="TG001")

    assert (git_repo / "app.py").read_text(encoding="utf-8") == before
