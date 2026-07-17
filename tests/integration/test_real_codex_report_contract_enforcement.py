from __future__ import annotations

import json
import subprocess
from pathlib import Path

from codex_orchestrator.diagnostics import diagnose_real_codex_attempt
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _setup(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _run_invalid_report_attempt(git_repo: Path, tmp_path: Path, monkeypatch):
    del tmp_path
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage
    from codex_orchestrator.workers.mock import MockWorker

    ctx = _setup(git_repo)
    invalid_override = {
        "status": "FIXED",
        "changed_product_runtime_file": None,
        "changed_artifact_files": [],
        "probe_commands": [],
        "deterministic_run_counts": None,
        "root_cause_classification": {},
        "before_after_state": None,
        "row_ledger": None,
        "trace_ledger": None,
        "cleanup_proof": {"cleanup_passed": True},
        "probe_artifact_refs": [],
    }
    original_launch = run_patchlet_stage.launch_report_production_worker

    def launch_invalid_report(**kwargs):
        kwargs["context"] = {**kwargs["context"], "mock_report_override": invalid_override}
        return original_launch(**kwargs)

    monkeypatch.setattr(run_patchlet_stage, "worker_for_mode", lambda _mode: MockWorker())
    monkeypatch.setattr(run_patchlet_stage, "launch_report_production_worker", launch_invalid_report)

    result = run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)
    attempt_id = f"{result.patchlet_id}_attempt1"
    run_dir = ctx.paths.runs_dir / attempt_id
    (run_dir / "stdout.txt").write_text("network timeout keyword noise\n", encoding="utf-8")
    (run_dir / "stderr.txt").write_text("API model timeout keyword noise\n", encoding="utf-8")
    diagnosis_result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(diagnosis_result["diagnosis_json_path"]))
    run_manifest = _read_json(ctx.paths.run_manifest)
    run = run_manifest["runs"][-1]
    return ctx, result, run, diagnosis


def test_fake_codex_invalid_fixed_status_report_safe_fails_with_schema_diagnosis(git_repo: Path, tmp_path: Path, monkeypatch):
    _, result, run, diagnosis = _run_invalid_report_attempt(git_repo, tmp_path, monkeypatch)

    assert result.status == "FAILED_WITH_EVIDENCE"
    assert run["report_valid"] is False
    assert diagnosis["diagnosis"]["primary_category"] == "patchlet_report_schema_violation"
    assert "FIXED" in run["report_validation"]["reason"]


def test_fake_codex_invalid_cleanup_proof_object_safe_fails_with_schema_diagnosis(git_repo: Path, tmp_path: Path, monkeypatch):
    _, _, run, diagnosis = _run_invalid_report_attempt(git_repo, tmp_path, monkeypatch)

    assert diagnosis["diagnosis"]["primary_category"] == "patchlet_report_schema_violation"
    assert "not of type 'string'" in run["report_validation"]["reason"]
    assert "cleanup_proof_type_error" in diagnosis["observed_signals"]


def test_report_producer_invalid_required_field_types_safe_fail_with_schema_diagnosis(
    git_repo: Path, tmp_path: Path, monkeypatch
):
    _, _, run, diagnosis = _run_invalid_report_attempt(git_repo, tmp_path, monkeypatch)

    reason = run["report_validation"]["reason"]
    assert diagnosis["diagnosis"]["primary_category"] == "patchlet_report_schema_violation"
    assert "None is not of type" in reason
    assert "FIXED" in reason


def test_invalid_report_diagnosis_preserves_report_validation_reason(git_repo: Path, tmp_path: Path, monkeypatch):
    _, _, run, diagnosis = _run_invalid_report_attempt(git_repo, tmp_path, monkeypatch)

    assert diagnosis["diagnosis"]["report_validation_reason"] == run["report_validation"]["reason"]


def test_invalid_report_diagnosis_precedes_network_keyword_noise(git_repo: Path, tmp_path: Path, monkeypatch):
    _, _, _, diagnosis = _run_invalid_report_attempt(git_repo, tmp_path, monkeypatch)

    assert diagnosis["diagnosis"]["primary_category"] == "patchlet_report_schema_violation"
    assert "captured_output_contains_network_or_api_error" not in diagnosis["observed_signals"]


def test_invalid_report_failure_preserves_evidence_artifacts(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, result, _, diagnosis = _run_invalid_report_attempt(git_repo, tmp_path, monkeypatch)
    run_dir = ctx.paths.runs_dir / f"{result.patchlet_id}_attempt1"

    assert (run_dir / "stdout.txt").exists()
    assert (run_dir / "stderr.txt").exists()
    assert (run_dir / "P0001.task_completion_handoff.json").exists()
    assert (run_dir / "gates/report_production_worker/attempt_1/worker_patchlet_report_v2.json").exists()
    assert (run_dir / "gates/report_production_worker/attempt_1/report_production_worker_result.json").exists()
    assert not (run_dir / "gates/report_production_worker/attempt_2").exists()
    assert (run_dir / "worker_memory" / "REPORT_SCHEMA_CONTRACT.md").exists()
    assert diagnosis["artifact_presence"]["wrapper_gate_result"] is True


def test_invalid_report_failure_keeps_target_product_files_clean(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, _, _, _ = _run_invalid_report_attempt(git_repo, tmp_path, monkeypatch)

    status = subprocess.run(
        ["git", "-C", str(ctx.root), "status", "--short", "--", "app.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert status.stdout.strip() == ""


def test_invalid_report_failure_does_not_blind_retry(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, _, run, diagnosis = _run_invalid_report_attempt(git_repo, tmp_path, monkeypatch)

    assert diagnosis["blind_retry_allowed"] is False
    assert run["wrapper_gate_result"]
    wrapper_gate = _read_json(ctx.root / run["wrapper_gate_result"])
    assert wrapper_gate["blind_retry_allowed"] is False
