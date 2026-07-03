from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from codex_orchestrator.diagnostics import diagnose_real_codex_attempt
from codex_orchestrator.jsonio import read_json
from codex_orchestrator.stages.apply_repair import apply_repair
from codex_orchestrator.stages.auto import run_auto
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
from codex_orchestrator.stages.verify_global import verify_global
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.integration_artifact_validator import validate_integration_artifacts


def _write_verified_no_change_codex(path: Path, *, canonical: bool) -> None:
    marker = "FINAL_STATUS: PASS" if canonical else "Marker: `FINAL_STATUS: PASS`"
    path.write_text(
        f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path

patchlet_id = os.environ["CXOR_PATCHLET_ID"]
probe_root = Path(os.environ["CXOR_PROBE_ROOT"])
run_root = probe_root / "run_001"
run_root.mkdir(parents=True, exist_ok=True)
(probe_root / "probe.py").write_text("print('probe passed')\\n", encoding="utf-8")
for name, payload in {{
    "row_ledger.jsonl": '{{"row": 1}}\\n',
    "trace_ledger.jsonl": '{{"trace": 1}}\\n',
    "before_state.json": '{{"state": "before"}}\\n',
    "after_state.json": '{{"state": "after"}}\\n',
    "cleanup_proof.json": '{{"cleanup_passed": true}}\\n',
}}.items():
    (run_root / name).write_text(payload, encoding="utf-8")

Path(os.environ["CXOR_PREFLIGHT_PATH"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["CXOR_PREFLIGHT_PATH"]).write_text("preflight done", encoding="utf-8")
Path(os.environ["CXOR_FINAL_REPORT_PATH"]).write_text(
    {marker!r} + "\\n\\n# Final Report\\n\\n- Patchlet: `" + patchlet_id + "`\\n",
    encoding="utf-8",
)
report = {{
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": patchlet_id,
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [
        f".artifacts/probes/{{patchlet_id}}/probe.py",
        f".artifacts/probes/{{patchlet_id}}/run_001/row_ledger.jsonl",
        f".artifacts/probes/{{patchlet_id}}/run_001/trace_ledger.jsonl",
        f".artifacts/probes/{{patchlet_id}}/run_001/before_state.json",
        f".artifacts/probes/{{patchlet_id}}/run_001/after_state.json",
        f".artifacts/probes/{{patchlet_id}}/run_001/cleanup_proof.json",
    ],
    "probe_commands": [f"python .artifacts/probes/{{patchlet_id}}/probe.py"],
    "deterministic_run_counts": {{"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"}},
    "root_cause_classification": {{
        "observed_failure": "no change needed",
        "immediate_cause": "already satisfies goal",
        "why_immediate_cause_happened": "direct probe passed",
        "deeper_owner_boundary": "app.py",
        "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "direct probe",
        "negative_control_proof": "negative control",
        "recursive_why_audit": []
    }},
    "before_after_state": [{{"before": "ok", "after": "ok"}}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "cleanup ok",
    "probe_artifact_refs": [{{"patchlet_id": patchlet_id, "probe_root": f".artifacts/probes/{{patchlet_id}}", "run_id": "run_001"}}],
    "acceptance_criteria_result": "pass"
}}
Path(os.environ["CXOR_REPORT_PATH"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["CXOR_REPORT_PATH"]).write_text(json.dumps(report), encoding="utf-8")
print(json.dumps({{"event": "turn.completed", "summary": "verified no change"}}), flush=True)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _setup_ctx(git_repo: Path, tmp_path: Path, monkeypatch, *, canonical: bool):
    fake_codex = tmp_path / "codex"
    _write_verified_no_change_codex(fake_codex, canonical=canonical)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _run_noncanonical_chain(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo, tmp_path, monkeypatch, canonical=False)
    result = run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)
    attempt_id = f"{result.patchlet_id}_attempt1"
    diagnosis_result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = read_json(Path(diagnosis_result["diagnosis_json_path"]))
    verify_global(ctx)
    classify_failures(ctx)
    plan_repair(ctx)
    apply_repair(ctx)
    regeneration = regenerate_patchlets(ctx, from_repair_plan="latest")
    return ctx, result, diagnosis, regeneration


def test_fake_codex_valid_report_noncanonical_final_marker_reproduces_wrapper_gate_failure(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, result, _, _ = _run_noncanonical_chain(git_repo, tmp_path, monkeypatch)
    run = read_json(ctx.paths.run_manifest)["runs"][-1]
    gate = read_json(ctx.root / run["wrapper_gate_result"])

    assert result.report_valid is True
    assert gate["accepted"] is False
    assert gate["final_status_marker_error"] == "noncanonical_final_status_marker"


def test_fake_codex_noncanonical_marker_diagnosis_not_network_error(git_repo: Path, tmp_path: Path, monkeypatch):
    _, _, diagnosis, _ = _run_noncanonical_chain(git_repo, tmp_path, monkeypatch)

    assert diagnosis["diagnosis"]["primary_category"] == "wrapper_gate_final_status_marker_error"
    assert diagnosis["diagnosis"]["primary_category"] != "network_or_api_error"


def test_fake_codex_noncanonical_marker_failure_records_tg_source_and_member_patchlet(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, _, _, _ = _run_noncanonical_chain(git_repo, tmp_path, monkeypatch)
    failure = read_json(ctx.paths.failures_dir / "F0001.json")

    assert failure["source_type"] == "transaction_group"
    assert failure["source_id"] == "TG001"
    assert failure["source_patchlet_ids"] == ["P0001"]


def test_fake_codex_noncanonical_marker_does_not_lookup_tg001_as_patchlet(git_repo: Path, tmp_path: Path, monkeypatch):
    _, _, _, regeneration = _run_noncanonical_chain(git_repo, tmp_path, monkeypatch)

    assert regeneration["patchlet_ids"] == ["P0002"]


def test_fake_codex_noncanonical_marker_keeps_app_py_clean(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, _, _, _ = _run_noncanonical_chain(git_repo, tmp_path, monkeypatch)
    status = subprocess.run(
        ["git", "-C", str(ctx.root), "status", "--short", "--", "app.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert status.stdout.strip() == ""


def test_fake_codex_noncanonical_marker_preserves_evidence(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, _, _, _ = _run_noncanonical_chain(git_repo, tmp_path, monkeypatch)
    run_dir = ctx.paths.runs_dir / "P0001_attempt1"

    assert (run_dir / "worker_stage" / "05_final_report.md").exists()
    assert (run_dir / "gates" / "wrapper_gate_result.json").exists()
    assert (ctx.paths.failures_dir / "F0001.json").exists()


def test_fake_codex_noncanonical_marker_no_blind_retry(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx, _, _, _ = _run_noncanonical_chain(git_repo, tmp_path, monkeypatch)
    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json")

    assert gate["blind_retry_allowed"] is False


def test_fake_codex_canonical_marker_valid_report_is_accepted(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo, tmp_path, monkeypatch, canonical=True)
    result = run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)
    run = read_json(ctx.paths.run_manifest)["runs"][-1]
    gate = read_json(ctx.root / run["wrapper_gate_result"])

    assert result.status == "VERIFIED_NO_CHANGE_NEEDED"
    assert gate["accepted"] is True


def test_fake_codex_canonical_marker_does_not_enter_tg_repair_regeneration(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo, tmp_path, monkeypatch, canonical=True)

    final_state = run_auto(ctx, until="DONE", worker_mode="real_codex", use_worktree=True, max_iterations=30)

    assert final_state.stage == "DONE"
    assert not list(ctx.paths.repair_plans_dir.glob("RP*.json"))


def test_verified_no_change_valid_report_canonical_marker_reaches_done_or_expected_success(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo, tmp_path, monkeypatch, canonical=True)

    final_state = run_auto(ctx, until="DONE", worker_mode="real_codex", use_worktree=True, max_iterations=30)

    assert final_state.stage == "DONE"


def test_verified_no_change_canonical_marker_transaction_group_passes(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo, tmp_path, monkeypatch, canonical=True)

    run_auto(ctx, until="DONE", worker_mode="real_codex", use_worktree=True, max_iterations=30)
    groups = read_json(ctx.paths.transaction_groups)

    assert groups["transaction_groups"][0]["status"] == "PASSED"


def test_verified_no_change_canonical_marker_no_repair_plan_created(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo, tmp_path, monkeypatch, canonical=True)

    run_auto(ctx, until="DONE", worker_mode="real_codex", use_worktree=True, max_iterations=30)

    assert not list(ctx.paths.repair_plans_dir.glob("RP*.json"))


def test_verified_no_change_canonical_marker_integration_artifacts_validate(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo, tmp_path, monkeypatch, canonical=True)

    run_auto(ctx, until="DONE", worker_mode="real_codex", use_worktree=True, max_iterations=30)
    validation = validate_integration_artifacts(ctx.root)

    assert validation["valid"] is True
