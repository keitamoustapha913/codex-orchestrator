from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.jsonio import read_json, write_json
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
from codex_orchestrator.validators.schema_validator import validate_json_file


def _setup_failed_tg(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    result = run_next_patchlet(ctx, worker_mode="mock")
    run_manifest = read_json(ctx.paths.run_manifest)
    run = run_manifest["runs"][-1]
    wrapper_gate_path = ctx.root / run["wrapper_gate_result"]
    wrapper_gate = read_json(wrapper_gate_path)
    wrapper_gate.update(
        {
            "accepted": False,
            "stage_gate": "fail",
            "final_status_gate": "fail",
            "final_status_marker_error": "noncanonical_final_status_marker",
            "final_status_marker_noncanonical": "Marker: `FINAL_STATUS: PASS`",
            "reasons": [
                "noncanonical FINAL_STATUS marker found; marker must be a standalone line beginning at column 1"
            ],
        }
    )
    write_json(wrapper_gate_path, wrapper_gate)
    index = read_json(ctx.paths.patchlet_index)
    group_id = next(patchlet["transaction_group_id"] for patchlet in index["patchlets"] if patchlet["patchlet_id"] == result.patchlet_id)
    verify_group(ctx, transaction_group_id=group_id)
    return ctx, group_id


def _failure_record(ctx) -> dict:
    return read_json(ctx.paths.failures_dir / "F0001.json")


def test_transaction_group_failure_record_preserves_source_type(git_repo: Path):
    ctx, _ = _setup_failed_tg(git_repo)

    assert _failure_record(ctx)["source_type"] == "transaction_group"


def test_transaction_group_failure_record_preserves_tg_source_id(git_repo: Path):
    ctx, group_id = _setup_failed_tg(git_repo)

    failure = _failure_record(ctx)

    assert failure["source_id"] == group_id
    assert failure["source_transaction_group_id"] == group_id


def test_transaction_group_failure_record_includes_member_patchlet_ids(git_repo: Path):
    ctx, _ = _setup_failed_tg(git_repo)

    assert _failure_record(ctx)["source_patchlet_ids"] == ["P0001"]


def test_transaction_group_failure_record_includes_wrapper_gate_reasons(git_repo: Path):
    ctx, _ = _setup_failed_tg(git_repo)

    failure = _failure_record(ctx)

    assert any("noncanonical FINAL_STATUS marker" in reason for reason in failure["gate_failure_reasons"])


def test_transaction_group_failure_record_schema_validates(git_repo: Path):
    ctx, _ = _setup_failed_tg(git_repo)

    assert validate_json_file(ctx.paths.failures_dir / "F0001.json", "failure_record.schema.json") == []


def test_patchlet_failure_record_still_uses_patchlet_source_type(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet_index = read_json(ctx.paths.patchlet_index)
    patchlet_index["patchlets"][0]["required_allowed_product_change"] = True
    write_json(ctx.paths.patchlet_index, patchlet_index)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"status": "COMPLETE"}),
        encoding="utf-8",
    )

    run_next_patchlet(ctx, worker_mode="mock")
    failure = read_json(ctx.paths.failures_dir / "F0001.json")

    assert failure["source_type"] == "patchlet"
    assert failure["source_id"] == "P0001"
    assert failure["source_patchlet_ids"] == ["P0001"]
