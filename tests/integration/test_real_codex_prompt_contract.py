from __future__ import annotations

import json
import os
from pathlib import Path

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
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workers.codex_exec import CodexExecWorker


def _contract_template_path() -> Path:
    return Path("src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md").resolve()


def _setup_compiled_ctx(git_repo: Path, monkeypatch):
    monkeypatch.setenv("CXOR_REAL_CODEX_CONTRACT_PATH", str(_contract_template_path()))
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))["patchlets"][0]
    return ctx, patchlet


def _setup_repair_patchlet_ctx(git_repo: Path, monkeypatch):
    ctx, _ = _setup_compiled_ctx(git_repo, monkeypatch)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"unauthorized_files": {"other.py": "bad = True\n"}, "status": "COMPLETE"}),
        encoding="utf-8",
    )
    result = run_next_patchlet(ctx, worker_mode="mock")
    assert result.status == "FAILED_WITH_EVIDENCE"
    classify_failures(ctx)
    plan_repair(ctx)
    apply_repair(ctx)
    assert load_state(ctx).stage == "PATCHLET_REGENERATION_REQUIRED"
    regenerate_patchlets(ctx, from_repair_plan="latest")
    patchlets = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))["patchlets"]
    repair_patchlet = next(patchlet for patchlet in patchlets if patchlet.get("is_repair_patchlet"))
    return ctx, repair_patchlet


def _write_fake_codex(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

patchlet_id = os.environ["CXOR_PATCHLET_ID"]
report = {
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": patchlet_id,
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [f".artifacts/probes/{patchlet_id}/probe.py"],
    "probe_commands": [f"python .artifacts/probes/{patchlet_id}/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
    "root_cause_classification": {
        "observed_failure": "no change needed",
        "immediate_cause": "no change needed",
        "why_immediate_cause_happened": "already ok",
        "deeper_owner_boundary": "app.py",
        "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "direct probe",
        "negative_control_proof": "negative control",
        "recursive_why_audit": []
    },
    "before_after_state": [{"before": "ok", "after": "ok"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "cleanup ok",
    "probe_artifact_refs": [],
    "acceptance_criteria_result": "pass"
}
Path(os.environ["CXOR_REPORT_PATH"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["CXOR_REPORT_PATH"]).write_text(json.dumps(report), encoding="utf-8")
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _generated_prompt_for_patchlet(ctx, patchlet: dict, tmp_path: Path, monkeypatch) -> str:
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    run_dir = ctx.paths.runs_dir / f"{patchlet['patchlet_id']}_attempt1"
    CodexExecWorker().run_patchlet(ctx, patchlet, run_dir=run_dir)
    return (run_dir / "codex_task_prompt.md").read_text(encoding="utf-8")


def test_generated_real_codex_prompt_includes_allowed_report_statuses(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    for status in ["COMPLETE", "VERIFIED_NO_CHANGE_NEEDED", "BLOCKED_WITH_EVIDENCE", "FAILED_WITH_EVIDENCE"]:
        assert status in prompt


def test_generated_real_codex_prompt_forbids_fixed_done_success_passed_ok(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    for status in ["FIXED", "DONE", "SUCCESS", "PASSED", "OK"]:
        assert status in prompt
    assert "Never use" in prompt


def test_generated_real_codex_prompt_includes_patchlet_report_json_skeleton(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert '"kind": "patchlet_report"' in prompt
    assert '"cleanup_proof": "cleanup passed; no transient files remain"' in prompt


def test_generated_real_codex_prompt_skeleton_uses_actual_patchlet_id(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert f'"patchlet_id": "{patchlet["patchlet_id"]}"' in prompt


def test_generated_real_codex_prompt_says_cleanup_proof_is_string(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert "cleanup_proof" in prompt
    assert "must be a string, not an object" in prompt


def test_generated_real_codex_prompt_says_changed_product_runtime_file_is_required(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert "changed_product_runtime_file" in prompt
    assert "must be present" in prompt


def test_generated_real_codex_prompt_says_required_ledgers_must_exist(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert "row_ledger" in prompt
    assert "trace_ledger" in prompt
    assert "must be present" in prompt


def test_repair_patchlet_prompt_includes_same_report_contract_as_initial_patchlet(git_repo: Path, monkeypatch):
    ctx, repair_patchlet = _setup_repair_patchlet_ctx(git_repo, monkeypatch)

    prompt = (ctx.root / repair_patchlet["subprompt_path"]).read_text(encoding="utf-8")

    assert "Real Codex Patchlet Contract" in prompt
    assert "# REPORT SCHEMA CONTRACT" in prompt
    assert "FIXED" in prompt
    assert "cleanup_proof" in prompt


def test_generated_prompt_references_final_report_contract(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert "FINAL_REPORT_CONTRACT.md" in prompt
    assert "# FINAL REPORT CONTRACT" in prompt


def test_generated_prompt_says_marker_must_be_standalone_column_one(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert "standalone line beginning at column 1" in prompt


def test_generated_prompt_forbids_marker_prefix_and_backticks(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert "Marker: `FINAL_STATUS: PASS`" in prompt
    assert "Do not wrap the final status marker in backticks" in prompt
    assert "Do not prefix the marker with \"Marker:\"" in prompt


def test_repair_patchlet_prompt_includes_final_report_contract(git_repo: Path, monkeypatch):
    ctx, repair_patchlet = _setup_repair_patchlet_ctx(git_repo, monkeypatch)

    prompt = (ctx.root / repair_patchlet["subprompt_path"]).read_text(encoding="utf-8")

    assert "# FINAL REPORT CONTRACT" in prompt
    assert "FINAL_STATUS: PASS" in prompt
    assert "Marker: `FINAL_STATUS: PASS`" in prompt


def test_real_codex_contract_injected_true_for_repair_patchlet_prompt(git_repo: Path, monkeypatch):
    ctx, repair_patchlet = _setup_repair_patchlet_ctx(git_repo, monkeypatch)

    prompt = (ctx.root / repair_patchlet["subprompt_path"]).read_text(encoding="utf-8")

    assert "Real Codex Patchlet Contract" in prompt


def test_generated_prompt_distinguishes_execution_root_from_target_root(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert "There are two roots" in prompt
    assert "CXOR_EXECUTION_ROOT" in prompt
    assert "CXOR_TARGET_ROOT" in prompt


def test_generated_prompt_says_product_edits_happen_in_execution_root(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert "Product/runtime edits happen only here" in prompt or "where product/runtime files are edited" in prompt


def test_generated_prompt_says_target_root_product_file_is_read_only(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert "Product/runtime files under target root are read-only" in prompt


def test_generated_prompt_lists_allowed_execution_root_edit_path(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert f"CXOR_EXECUTION_ROOT/{patchlet['allowed_product_runtime_file']}" in prompt


def test_generated_prompt_lists_forbidden_target_root_edit_path(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, patchlet = _setup_compiled_ctx(git_repo, monkeypatch)

    prompt = _generated_prompt_for_patchlet(ctx, patchlet, tmp_path, monkeypatch)

    assert f"CXOR_TARGET_ROOT/{patchlet['allowed_product_runtime_file']}" in prompt


def test_repair_patchlet_prompt_includes_execution_root_edit_contract(git_repo: Path, monkeypatch):
    ctx, repair_patchlet = _setup_repair_patchlet_ctx(git_repo, monkeypatch)

    prompt = (ctx.root / repair_patchlet["subprompt_path"]).read_text(encoding="utf-8")

    assert "Execution-root edit contract" in prompt
    assert f"CXOR_EXECUTION_ROOT/{repair_patchlet['allowed_product_runtime_file']}" in prompt
    assert f"CXOR_TARGET_ROOT/{repair_patchlet['allowed_product_runtime_file']}" in prompt
