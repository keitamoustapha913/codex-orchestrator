from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.patchlet_run_context import build_patchlet_run_context
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.worker_capsule import (
    build_worker_capsule,
    ensure_worker_capsule,
    ensure_worker_memory,
    ensure_worker_stage_templates,
    write_wrapper_gate_result,
)


def _setup(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))["patchlets"][0]
    run_ctx = build_patchlet_run_context(
        ctx,
        patchlet=patchlet,
        run_id=f"{patchlet['patchlet_id']}_attempt1",
        execution_root=ctx.root,
        artifact_root=ctx.root,
        is_worktree=False,
        worktree_path=None,
    )
    capsule = build_worker_capsule(run_ctx, patchlet)
    ensure_worker_capsule(ctx, capsule)
    ensure_worker_memory(ctx, capsule, run_ctx, patchlet, worker_mode="real_codex")
    ensure_worker_stage_templates(capsule, run_ctx, patchlet)
    return ctx, patchlet, run_ctx, capsule


def _gate_for_final_report(git_repo: Path, final_report_text: str | None) -> dict:
    ctx, _, run_ctx, capsule = _setup(git_repo)
    final_report_path = capsule.worker_stage_dir / "05_final_report.md"
    if final_report_text is None:
        final_report_path.unlink()
    else:
        final_report_path.write_text(final_report_text, encoding="utf-8")
    return write_wrapper_gate_result(
        ctx,
        capsule,
        run_ctx,
        worker_mode="real_codex",
        worker_exit_ok=True,
        diff_allowed=True,
        report_valid=True,
        probe_valid=True,
        next_state="GROUP_VERIFICATION_REQUIRED",
    )


def test_wrapper_gate_accepts_bare_final_status_pass_line(git_repo: Path):
    gate = _gate_for_final_report(git_repo, "FINAL_STATUS: PASS\n\n# Final Report\n")

    assert gate["accepted"] is True
    assert gate["final_status_gate"] == "present"
    assert gate["final_status_claim"] == "PASS"
    assert gate["final_status_marker_canonical"] is True
    assert gate["final_status_marker_error"] is None


def test_wrapper_gate_rejects_marker_prefix_backtick_final_status_pass(git_repo: Path):
    gate = _gate_for_final_report(git_repo, "Marker: `FINAL_STATUS: PASS`\n")

    assert gate["accepted"] is False
    assert gate["final_status_gate"] == "fail"
    assert gate["final_status_marker_error"] == "noncanonical_final_status_marker"


def test_wrapper_gate_reports_noncanonical_marker_when_backticked_marker_present(git_repo: Path):
    gate = _gate_for_final_report(git_repo, "Marker: `FINAL_STATUS: PASS`\n")

    assert gate["final_status_marker_noncanonical"] == "Marker: `FINAL_STATUS: PASS`"
    assert any("noncanonical FINAL_STATUS marker found" in reason for reason in gate["reasons"])


def test_wrapper_gate_rejects_backtick_only_final_status_pass(git_repo: Path):
    gate = _gate_for_final_report(git_repo, "`FINAL_STATUS: PASS`\n")

    assert gate["accepted"] is False
    assert gate["final_status_marker_error"] == "noncanonical_final_status_marker"


def test_wrapper_gate_rejects_final_status_inside_sentence(git_repo: Path):
    gate = _gate_for_final_report(git_repo, "The final marker is FINAL_STATUS: PASS\n")

    assert gate["accepted"] is False
    assert gate["final_status_marker_error"] == "noncanonical_final_status_marker"


def test_wrapper_gate_rejects_invalid_final_status_ok(git_repo: Path):
    gate = _gate_for_final_report(git_repo, "FINAL_STATUS: OK\n")

    assert gate["accepted"] is False
    assert gate["final_status_marker_canonical"] is False
    assert gate["final_status_marker_error"] == "invalid_final_status_marker_value"


def test_wrapper_gate_reports_missing_marker_when_absent(git_repo: Path):
    gate = _gate_for_final_report(git_repo, "# Final Report\nNo marker here.\n")

    assert gate["accepted"] is False
    assert gate["final_status_gate"] == "missing"
    assert gate["final_status_marker_error"] == "missing_final_status_marker"


def test_wrapper_gate_result_preserves_reasons(git_repo: Path):
    gate = _gate_for_final_report(git_repo, "FINAL_STATUS: SUCCESS\n")

    assert any("invalid FINAL_STATUS marker value" in reason for reason in gate["reasons"])


def test_wrapper_gate_result_is_used_in_run_manifest(git_repo: Path):
    gate = _gate_for_final_report(git_repo, "Marker: `FINAL_STATUS: PASS`\n")

    gate_path = Path(gate["worker_capsule_manifest"]).parent / "gates" / "wrapper_gate_result.json"
    saved = json.loads((git_repo / gate_path).read_text(encoding="utf-8"))

    assert saved["final_status_marker_error"] == "noncanonical_final_status_marker"
