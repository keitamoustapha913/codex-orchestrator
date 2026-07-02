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
from codex_orchestrator.patchlet_run_context import build_patchlet_run_context
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.worker_capsule import build_worker_capsule, write_wrapper_gate_result


def _compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def test_worker_stage_templates_are_created_before_worker_execution(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    stage_dir = ctx.paths.runs_dir / "P0001_attempt1" / "worker_stage"
    assert (stage_dir / "00_preflight.md").exists()
    assert (stage_dir / "01_investigation.md").exists()
    assert (stage_dir / "02_probe_plan.md").exists()
    assert (stage_dir / "03_implementation.md").exists()
    assert (stage_dir / "04_validation.md").exists()
    assert (stage_dir / "05_final_report.md").exists()


def test_worker_stage_preflight_template_mentions_allowed_file_and_report_path(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "worker_stage" / "00_preflight.md").read_text(encoding="utf-8")
    assert "app.py" in text
    assert ".codex-orchestrator/reports/P0001.json" in text
    assert ".artifacts/probes/P0001" in text


def test_worker_stage_probe_plan_template_mentions_root_cause_requirements(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "worker_stage" / "02_probe_plan.md").read_text(encoding="utf-8")
    assert "Minimal reproduction" in text
    assert "Deterministic run count" in text
    assert "Producer -> transformer -> consumer boundary" in text
    assert "Negative control" in text
    assert "Cleanup proof" in text


def test_worker_stage_final_report_template_mentions_final_status(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "worker_stage" / "05_final_report.md").read_text(encoding="utf-8")
    assert "FINAL_STATUS: PASS" in text


def test_missing_preflight_stage_fails_wrapper_gate(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")
    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][0]
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")
    capsule = build_worker_capsule(run_ctx, patchlet)
    (run_dir / "worker_stage" / "00_preflight.md").unlink()

    gate = write_wrapper_gate_result(
        ctx,
        capsule,
        run_ctx,
        worker_mode="mock",
        worker_exit_ok=True,
        diff_allowed=True,
        report_valid=True,
        probe_valid=True,
        next_state="PATCHLETS_READY",
        report_path=ctx.paths.reports_dir / "P0001.json",
    )

    assert gate["accepted"] is False
    assert gate["stage_gate"] == "fail"
    assert "missing worker_stage/00_preflight.md" in gate["reasons"]


def test_missing_probe_plan_stage_blocks_complete_report_acceptance(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")
    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][0]
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")
    capsule = build_worker_capsule(run_ctx, patchlet)
    (run_dir / "worker_stage" / "02_probe_plan.md").unlink()

    gate = write_wrapper_gate_result(
        ctx,
        capsule,
        run_ctx,
        worker_mode="mock",
        worker_exit_ok=True,
        diff_allowed=True,
        report_valid=True,
        probe_valid=True,
        next_state="PATCHLETS_READY",
        report_path=ctx.paths.reports_dir / "P0001.json",
    )

    assert gate["accepted"] is False
    assert gate["stage_gate"] == "fail"
    assert "missing worker_stage/02_probe_plan.md" in gate["reasons"]


def test_missing_final_report_marker_fails_wrapper_gate(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")
    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][0]
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")
    capsule = build_worker_capsule(run_ctx, patchlet)
    (run_dir / "worker_stage" / "05_final_report.md").write_text("# Final Report\n\nNo terminal status marker.\n", encoding="utf-8")

    gate = write_wrapper_gate_result(
        ctx,
        capsule,
        run_ctx,
        worker_mode="mock",
        worker_exit_ok=True,
        diff_allowed=True,
        report_valid=True,
        probe_valid=True,
        next_state="PATCHLETS_READY",
        report_path=ctx.paths.reports_dir / "P0001.json",
    )

    assert gate["accepted"] is False
    assert gate["stage_gate"] == "fail"
    assert gate["final_status_gate"] == "missing"
    assert "missing worker_stage/05_final_report.md FINAL_STATUS marker" in gate["reasons"]
