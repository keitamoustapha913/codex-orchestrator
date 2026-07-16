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
from codex_orchestrator.worker_capsule import build_worker_capsule, ensure_worker_capsule, ensure_worker_memory


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
    return ctx, patchlet, run_ctx, capsule


def _contract_text(git_repo: Path) -> str:
    _, _, _, capsule = _setup(git_repo)
    return (capsule.worker_memory_dir / "REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")


def test_worker_capsule_writes_report_schema_contract(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    assert (capsule.worker_memory_dir / "REPORT_SCHEMA_CONTRACT.md").exists()


def test_report_schema_contract_contains_allowed_statuses(git_repo: Path):
    text = _contract_text(git_repo)

    for status in ["COMPLETE", "VERIFIED_NO_CHANGE_NEEDED", "BLOCKED_WITH_EVIDENCE", "FAILED_WITH_EVIDENCE"]:
        assert status in text


def test_report_schema_contract_contains_forbidden_statuses(git_repo: Path):
    text = _contract_text(git_repo)

    for status in ["FIXED", "DONE", "SUCCESS", "PASSED", "OK"]:
        assert status in text
    assert "Never use `FIXED`" in text


def test_report_schema_contract_contains_minimal_json_skeleton(git_repo: Path):
    text = _contract_text(git_repo)

    assert '"kind": "worker_patchlet_report"' in text
    assert '"status": "VERIFIED_NO_CHANGE_NEEDED"' in text
    assert '"cleanup_proof": "cleanup passed; no transient files remain"' in text


def test_report_schema_contract_uses_actual_patchlet_id(git_repo: Path):
    _, patchlet, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")

    assert f'"patchlet_id": "{patchlet["patchlet_id"]}"' in text


def test_report_schema_contract_says_cleanup_proof_is_string(git_repo: Path):
    text = _contract_text(git_repo)

    assert "`cleanup_proof` must be a string, not an object" in text


def test_report_schema_contract_says_changed_product_runtime_file_required(git_repo: Path):
    text = _contract_text(git_repo)

    assert "`changed_product_runtime_file` must be present" in text


def test_task_contract_references_report_schema_contract(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "TASK_CONTRACT.md").read_text(encoding="utf-8")

    assert "REPORT_SCHEMA_CONTRACT.md" in text


def test_write_these_files_references_report_schema_contract(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "WRITE_THESE_FILES.md").read_text(encoding="utf-8")

    assert "REPORT_SCHEMA_CONTRACT.md" in text


def test_worker_capsule_memory_includes_execution_root_edit_contract(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "TASK_CONTRACT.md").read_text(encoding="utf-8")

    assert "Execution-root edit contract" in text
    assert "Product/runtime files under target root are read-only" in text


def test_worker_capsule_memory_includes_forbidden_target_root_product_path(git_repo: Path):
    _, patchlet, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "TASK_CONTRACT.md").read_text(encoding="utf-8")

    assert f"CXOR_TARGET_ROOT/{patchlet['allowed_product_runtime_file']}" in text
