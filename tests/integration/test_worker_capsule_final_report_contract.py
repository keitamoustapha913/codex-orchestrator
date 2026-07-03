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
from codex_orchestrator.worker_capsule import build_worker_capsule, ensure_worker_capsule, ensure_worker_memory, ensure_worker_stage_templates


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
        run_id="P0001_attempt1",
        execution_root=ctx.root,
        artifact_root=ctx.root,
        is_worktree=False,
        worktree_path=None,
    )
    capsule = build_worker_capsule(run_ctx, patchlet)
    ensure_worker_capsule(ctx, capsule)
    ensure_worker_memory(ctx, capsule, run_ctx, patchlet, worker_mode="real_codex")
    ensure_worker_stage_templates(capsule, run_ctx, patchlet)
    return patchlet, capsule


def _contract_text(git_repo: Path) -> str:
    _, capsule = _setup(git_repo)
    return (capsule.worker_memory_dir / "FINAL_REPORT_CONTRACT.md").read_text(encoding="utf-8")


def test_worker_capsule_writes_final_report_contract(git_repo: Path):
    _, capsule = _setup(git_repo)

    assert (capsule.worker_memory_dir / "FINAL_REPORT_CONTRACT.md").exists()


def test_final_report_contract_contains_canonical_pass_line(git_repo: Path):
    text = _contract_text(git_repo)

    assert "FINAL_STATUS: PASS" in text
    assert "standalone canonical marker beginning at column 1" in text


def test_final_report_contract_contains_forbidden_marker_backtick_example(git_repo: Path):
    text = _contract_text(git_repo)

    assert "Marker: `FINAL_STATUS: PASS`" in text
    assert "`FINAL_STATUS: PASS`" in text
    assert "Do not wrap the final status marker in backticks" in text


def test_final_report_contract_template_first_nonempty_line_is_final_status_pass(git_repo: Path):
    _, capsule = _setup(git_repo)
    final_report = (capsule.worker_stage_dir / "05_final_report.md").read_text(encoding="utf-8")

    first_nonempty = next(line for line in final_report.splitlines() if line.strip())

    assert first_nonempty == "FINAL_STATUS: PASS"


def test_task_contract_references_final_report_contract(git_repo: Path):
    _, capsule = _setup(git_repo)
    text = (capsule.worker_memory_dir / "TASK_CONTRACT.md").read_text(encoding="utf-8")

    assert "FINAL_REPORT_CONTRACT.md" in text


def test_write_these_files_references_final_report_contract(git_repo: Path):
    _, capsule = _setup(git_repo)
    text = (capsule.worker_memory_dir / "WRITE_THESE_FILES.md").read_text(encoding="utf-8")

    assert "FINAL_REPORT_CONTRACT.md" in text
