from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.prompt_index import read_prompt_index
from codex_orchestrator.stages.apply_repair import apply_repair
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.classify_failures import classify_failures
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.plan_repair import plan_repair
from codex_orchestrator.stages.regenerate_patchlets import regenerate_patchlets
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
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


def _run_bad_report(ctx):
    scenario = {"report_production_override": {"probe_artifact_refs": ["/etc/passwd"]}}
    path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scenario), encoding="utf-8")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)


def test_report_schema_contract_includes_object_shaped_probe_ref_example(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")
    assert '"probe_artifact_refs": [' in text
    assert '"patchlet_id": "P0001"' in text
    assert '"probe_root": ".artifacts/probes/P0001"' in text
    assert '"files": [' in text


def test_report_schema_contract_includes_invalid_string_probe_ref_example(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")
    assert "Invalid:" in text
    assert '".artifacts/probes/P0001/comparison.txt"' in text


def test_report_schema_contract_forbids_string_probe_refs(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")
    assert "never string-only paths" in text
    assert "Do not write probe_artifact_refs as strings" in text


def test_report_schema_contract_requires_bounded_relative_evidence_paths(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")
    assert "bounded, POSIX-style" in text
    assert "Never copy that absolute filesystem path" in text
    assert "any `/tmp/...` absolute path" in text
    assert ".artifacts/probes/P0001/run_001/before_state.json" in text


def test_report_schema_contract_uses_canonical_goal_item_id_shorthand(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")
    assert '"goal_item_id": "<current goal item id>"' in text
    assert '"goal_item":' not in text


def test_report_schema_contract_keeps_final_status_marker_out_of_report_json(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")
    assert '"final_status_marker":' not in text
    assert "- final_status_marker\n" not in text
    assert "`final_status_marker` belongs to the final Markdown wrapper" in text


def test_primary_worker_report_template_forbids_absolute_and_traversal_paths():
    from codex_orchestrator.report_contract import render_primary_worker_report_template

    text = render_primary_worker_report_template()
    assert "never absolute filesystem paths" in text
    assert "Never copy `$CXOR_WORKER_EVIDENCE_DIR`" in text
    assert "`..`" in text


def test_task_worker_prompt_does_not_include_formal_probe_ref_skeleton(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/codex_task_prompt.md").read_text(encoding="utf-8")
    assert '"probe_root": ".artifacts/probes/P0001"' not in text
    assert '"probe_artifact_refs":' not in text


def test_task_worker_prompt_delegates_probe_refs_to_report_production(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/codex_task_prompt.md").read_text(encoding="utf-8")
    assert "Report Production Worker derive those" in text


def test_repair_prompt_for_probe_ref_shape_failure_includes_exact_field(git_repo: Path):
    ctx = _ctx(git_repo)
    _run_bad_report(ctx)
    classify_failures(ctx)
    plan_repair(ctx)
    apply_repair(ctx)
    regenerate_patchlets(ctx)
    text = (ctx.paths.workflow_dir / "subprompts/0002_repair.md").read_text(encoding="utf-8")
    assert "field: probe_artifact_refs" in text


def test_repair_prompt_for_probe_ref_shape_failure_includes_expected_and_actual_types(git_repo: Path):
    ctx = _ctx(git_repo)
    _run_bad_report(ctx)
    classify_failures(ctx)
    plan_repair(ctx)
    apply_repair(ctx)
    regenerate_patchlets(ctx)
    text = (ctx.paths.workflow_dir / "subprompts/0002_repair.md").read_text(encoding="utf-8")
    assert "expected: array of objects" in text
    assert "actual: array of strings" in text


def test_repair_prompt_for_probe_ref_shape_failure_includes_valid_replacement_example(git_repo: Path):
    ctx = _ctx(git_repo)
    _run_bad_report(ctx)
    classify_failures(ctx)
    plan_repair(ctx)
    apply_repair(ctx)
    regenerate_patchlets(ctx)
    text = (ctx.paths.workflow_dir / "subprompts/0002_repair.md").read_text(encoding="utf-8")
    assert "Use this exact object shape" in text
    assert '"patchlet_id"' in text


def test_repair_prompt_for_probe_ref_shape_failure_says_do_not_modify_product_files_for_report_shape_only(git_repo: Path):
    ctx = _ctx(git_repo)
    _run_bad_report(ctx)
    classify_failures(ctx)
    plan_repair(ctx)
    apply_repair(ctx)
    regenerate_patchlets(ctx)
    text = (ctx.paths.workflow_dir / "subprompts/0002_repair.md").read_text(encoding="utf-8")
    assert "Do not rewrite product/runtime files just to fix this report shape" in text


def test_prompt_index_records_hardened_report_contract_artifact(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    prompts = read_prompt_index(ctx.root)["prompts"]
    worker_prompt = [prompt for prompt in prompts if prompt["kind"] == "patchlet_worker_prompt"][-1]
    assert "TASK_COMPLETION_HANDOFF_CONTRACT.md" in worker_prompt["contracts"]
    assert "REPORT_SCHEMA_CONTRACT.md" not in worker_prompt["contracts"]


def test_generated_report_contract_does_not_advertise_acceptance_criteria_result(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    contract = (
        ctx.paths.runs_dir
        / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md"
    ).read_text(encoding="utf-8")
    assert "acceptance_criteria_result" not in contract


def test_generated_worker_prompt_does_not_advertise_acceptance_criteria_result(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    prompt = (
        ctx.paths.runs_dir / "P0001_attempt1/codex_task_prompt.md"
    ).read_text(encoding="utf-8")
    assert "acceptance_criteria_result" not in prompt
