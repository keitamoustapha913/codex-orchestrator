from __future__ import annotations

import json
import os
import hashlib
import subprocess
from pathlib import Path

from codex_orchestrator.git_guard import changed_between, snapshot_status
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.stages.run_patchlet import _quarantine_execution_root_scratch_files
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.diff_validator import validate_changed_paths


def _run_ctx(tmp_path: Path) -> PatchletRunContext:
    target = tmp_path / "target"
    execution = tmp_path / "execution"
    run_dir = target / ".codex-orchestrator" / "runs" / "P0001_attempt1"
    reports = target / ".codex-orchestrator" / "reports"
    probes = target / ".artifacts" / "probes"
    for path in [target, execution, run_dir, reports, probes]:
        path.mkdir(parents=True, exist_ok=True)
    return PatchletRunContext(
        target_root=target,
        execution_root=execution,
        artifact_root=target,
        workflow_dir=target / ".codex-orchestrator",
        reports_dir=reports,
        probe_dir=probes,
        runs_dir=target / ".codex-orchestrator" / "runs",
        run_dir=run_dir,
        is_worktree=True,
        worktree_path=execution,
    )


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _git_run_ctx(tmp_path: Path) -> PatchletRunContext:
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "policy.bundle").write_text("profile=legacy\nmode=permissive\n", encoding="utf-8")
    (run_ctx.execution_root / "peer.record").write_text("owner=platform\n", encoding="utf-8")
    _git("init", cwd=run_ctx.execution_root)
    _git("config", "user.email", "test@example.invalid", cwd=run_ctx.execution_root)
    _git("config", "user.name", "Test User", cwd=run_ctx.execution_root)
    _git("add", ".", cwd=run_ctx.execution_root)
    _git("commit", "-m", "baseline", cwd=run_ctx.execution_root)
    return run_ctx


def _policy_patchlet() -> dict:
    return {
        "patchlet_id": "P0001",
        "allowed_product_runtime_file": "policy.bundle",
        "allowed_artifact_dirs": [".artifacts/probes/", ".codex-orchestrator/runs/"],
    }


def _patchlet() -> dict:
    return _policy_patchlet()


def _report(path: Path, changed_artifact_files: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"changed_artifact_files": changed_artifact_files}), encoding="utf-8")
    return path


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _setup_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _fake_codex_report() -> str:
    return """#!/usr/bin/env python3
import json, os
from pathlib import Path
Path(os.environ["CXOR_WORKER_SCRATCH_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["CXOR_WORKER_SCRATCH_DIR"], "report_json_validated.txt").write_text("ok\\n", encoding="utf-8")
Path(os.environ["CXOR_REPORT_PATH"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["CXOR_REPORT_PATH"]).write_text(json.dumps({
  "schema_version":"1.0","kind":"patchlet_report","patchlet_id":"P0001",
  "status":"VERIFIED_NO_CHANGE_NEEDED","final_status_marker":"FINAL_STATUS: PASS",
  "changed_product_runtime_file":None,"changed_artifact_files":[".artifacts/probes/P0001/probe.py"],
  "probe_commands":["python .artifacts/probes/P0001/probe.py"],
  "deterministic_run_counts":{"baseline":"5/5","proof_of_fix":"5/5","negative_controls":"5/5"},
  "root_cause_classification":{"observed_failure":"none","immediate_cause":"none","why_immediate_cause_happened":"already ok","deeper_owner_boundary":"target","producer_transformer_consumer_boundary":"target -> probe","not_downstream_of_unprobed_state_proof":"direct","negative_control_proof":"direct"},
  "before_after_state":[{"before":"ok","after":"ok"}],"row_ledger":[],"trace_ledger":[],
  "cleanup_proof":"ok","probe_artifact_refs":[],"acceptance_criteria_result":"pass"
}), encoding="utf-8")
"""


def test_known_root_scratch_file_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_validation.json").write_text("{}", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert result[0]["original_path"] == "report_validation.json"
    assert not (run_ctx.execution_root / "report_validation.json").exists()


def test_unknown_json_root_scratch_file_quarantined_when_declared_by_worker_report(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "custom_check.json").write_text("{}", encoding="utf-8")
    report = _report(run_ctx.reports_dir / "P0001.json", ["custom_check.json"])
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=report, allowed_product_runtime_file="service.cfg")
    assert result[0]["declared_by_report"] is True


def test_report_role_root_scratch_file_quarantined_without_declaration(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_validated.json").write_text("{}", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert result[0]["original_path"] == "report_validated.json"
    assert result[0]["reason"] == "role_shaped_report_validated_output"


def test_patchlet_prefixed_report_pretty_json_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "p0001_report_pretty.json").write_text("{}", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result[0]["original_path"] == "p0001_report_pretty.json"
    assert result[0]["reason"] == "patchlet_prefixed_report_formatting_scratch"
    assert not (run_ctx.execution_root / "p0001_report_pretty.json").exists()


def test_patchlet_prefixed_report_formatted_json_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "P0001-report-formatted.json").write_text("{}", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result[0]["original_path"] == "P0001-report-formatted.json"
    assert result[0]["reason"] == "patchlet_prefixed_report_formatting_scratch"


def test_patchlet_prefixed_report_output_txt_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "patchlet_P0001_report_output.txt").write_text("ok\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result[0]["original_path"] == "patchlet_P0001_report_output.txt"
    assert result[0]["reason"] == "patchlet_prefixed_report_formatting_scratch"


def test_patchlet_prefixed_report_check_json_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "p0001_report_check.json").write_text("{}", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result[0]["original_path"] == "p0001_report_check.json"
    assert result[0]["reason"] in {"patchlet_prefixed_report_formatting_scratch", "role_shaped_report_check_output"}


def test_patchlet_prefixed_report_pretty_preserves_content_and_hash(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    content = '{\n  "status": "PASS"\n}\n'
    (run_ctx.execution_root / "p0001_report_pretty.json").write_text(content, encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    quarantined = run_ctx.target_root / result[0]["quarantine_path"]
    assert quarantined.read_text(encoding="utf-8") == content
    assert result[0]["sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_patchlet_prefixed_report_pretty_removed_before_diff_validation(tmp_path: Path):
    run_ctx = _git_run_ctx(tmp_path)
    (run_ctx.execution_root / "policy.bundle").write_text("profile=no-compat\nmode=permissive\n", encoding="utf-8")
    (run_ctx.execution_root / "p0001_report_pretty.json").write_text("{}", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert not (run_ctx.execution_root / "p0001_report_pretty.json").exists()


def test_patchlet_prefixed_report_pretty_recomputes_changed_paths_to_allowed_file_only(tmp_path: Path):
    run_ctx = _git_run_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "policy.bundle").write_text("profile=no-compat\nmode=permissive\n", encoding="utf-8")
    (run_ctx.execution_root / "p0001_report_pretty.json").write_text("{}", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")
    after = snapshot_status(run_ctx.execution_root)
    changed = changed_between(before, after)
    diff_result = validate_changed_paths(changed, _policy_patchlet())

    assert changed == ["policy.bundle"]
    assert diff_result.allowed is True


def test_random_pretty_json_is_rejected(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "random_pretty.json").write_text("{}", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert (run_ctx.execution_root / "random_pretty.json").exists()


def test_patchlet_prefixed_pretty_without_report_role_is_rejected(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "p0001_pretty.json").write_text("{}", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert (run_ctx.execution_root / "p0001_pretty.json").exists()


def test_patchlet_prefixed_runtime_pretty_is_rejected(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "p0001_runtime_pretty.json").write_text("{}", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert (run_ctx.execution_root / "p0001_runtime_pretty.json").exists()


def test_executable_patchlet_report_pretty_is_rejected(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    path = run_ctx.execution_root / "p0001_report_pretty.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o755)

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert path.exists()


def test_changed_peer_product_file_still_rejected_with_report_pretty_present(tmp_path: Path):
    run_ctx = _git_run_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "policy.bundle").write_text("profile=no-compat\nmode=permissive\n", encoding="utf-8")
    (run_ctx.execution_root / "peer.record").write_text("owner=security\n", encoding="utf-8")
    (run_ctx.execution_root / "p0001_report_pretty.json").write_text("{}", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _policy_patchlet())

    assert "peer.record" in diff_result.unauthorized_paths


def test_unknown_root_scratch_file_rejected_when_not_declared(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "custom_check.json").write_text("{}", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert result == []
    assert (run_ctx.execution_root / "custom_check.json").exists()


def test_root_product_file_still_rejected(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "other.cfg").write_text("x=1\n", encoding="utf-8")
    report = _report(run_ctx.reports_dir / "P0001.json", ["other.cfg"])
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=report, allowed_product_runtime_file="service.cfg")
    assert result == []
    assert (run_ctx.execution_root / "other.cfg").exists()


def test_quarantined_scratch_file_recorded_in_gate_result(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / ".report_check.json").write_text("{}", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    record = json.loads((run_ctx.run_dir / "quarantined_scratch" / "quarantined_scratch_files.json").read_text(encoding="utf-8"))
    assert record["quarantined_scratch_files"] == result


def test_quarantine_preserves_original_content(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / ".report_check.json").write_text('{"ok": true}', encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    quarantined = run_ctx.target_root / result[0]["quarantine_path"]
    assert quarantined.read_text(encoding="utf-8") == '{"ok": true}'


def test_quarantine_removes_root_scratch_from_worktree_before_diff_acceptance(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / ".report_check.json").write_text("{}", encoding="utf-8")
    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert not (run_ctx.execution_root / ".report_check.json").exists()


def test_quarantine_does_not_weaken_one_file_rule(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "service.cfg").write_text("status=ready\n", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert result == []
    assert (run_ctx.execution_root / "service.cfg").exists()


def test_report_check_out_root_file_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_check.out").write_text("OK\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "report_check.out"
    assert result[0]["reason"] == "role_shaped_report_check_output"
    assert not (run_ctx.execution_root / "report_check.out").exists()


def test_report_json_validated_txt_root_file_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_json_validated.txt").write_text("}\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "report_json_validated.txt"
    assert result[0]["reason"] == "role_shaped_report_validation_output"
    assert not (run_ctx.execution_root / "report_json_validated.txt").exists()


def test_validate_report_out_is_quarantined_as_role_shaped_scratch(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "validate_report.out").write_text("valid\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "validate_report.out"
    assert result[0]["reason"] == "role_shaped_report_validate_output"
    assert not (run_ctx.execution_root / "validate_report.out").exists()


def test_validation_report_out_is_quarantined_as_role_shaped_scratch(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "validation_report.out").write_text("valid\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "validation_report.out"
    assert result[0]["reason"] == "role_shaped_report_validation_output"


def test_probe_validate_out_is_quarantined_as_role_shaped_scratch(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "probe_validate.out").write_text("valid\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "probe_validate.out"
    assert result[0]["reason"] == "role_shaped_probe_validate_output"


def test_report_validation_result_txt_root_file_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_validation_result.txt").write_text("valid\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "report_validation_result.txt"
    assert result[0]["reason"] == "role_shaped_report_validation_output"


def test_validation_report_txt_root_file_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "validation_report.txt").write_text("valid\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "validation_report.txt"


def test_probe_json_validated_txt_root_file_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "probe_json_validated.txt").write_text("valid\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "probe_json_validated.txt"
    assert result[0]["reason"] == "role_shaped_probe_validation_output"


def test_report_check_log_root_file_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_check.log").write_text("OK\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "report_check.log"


def test_report_validation_json_root_file_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_validation.json").write_text("{}", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "report_validation.json"


def test_dot_report_check_json_root_file_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / ".report_check.json").write_text("{}", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == ".report_check.json"


def test_quarantine_preserves_scratch_content_and_hash(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    content = "OK\n"
    (run_ctx.execution_root / "report_check.out").write_text(content, encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    quarantined = run_ctx.target_root / result[0]["quarantine_path"]
    assert quarantined.read_text(encoding="utf-8") == content
    assert len(result[0]["sha256"]) == 64
    assert result[0]["size_bytes"] == len(content)


def test_quarantine_records_metadata_artifact(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_check.out").write_text("OK\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    record = json.loads((run_ctx.run_dir / "gates" / "scratch_artifact_quarantine_result.json").read_text(encoding="utf-8"))
    assert record["kind"] == "scratch_artifact_quarantine_result"
    assert record["quarantined"][0]["original_path"] == "report_check.out"
    assert record["one_file_rule_preserved"] is True
    assert record["slice_boundary_preserved"] is True


def test_quarantine_removes_scratch_from_product_diff_before_guard(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_check.out").write_text("OK\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert not (run_ctx.execution_root / "report_check.out").exists()


def test_diff_guard_rechecks_after_quarantine(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_check.out").write_text("OK\n", encoding="utf-8")
    (run_ctx.execution_root / "service.cfg").write_text("status=ready\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    remaining = sorted(path.name for path in run_ctx.execution_root.iterdir())

    assert remaining == ["service.cfg"]


def test_unknown_root_out_file_not_role_shaped_is_rejected(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "new_config.out").write_text("x\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert (run_ctx.execution_root / "new_config.out").exists()
    record = json.loads((run_ctx.run_dir / "gates" / "scratch_artifact_quarantine_result.json").read_text(encoding="utf-8"))
    assert record["rejected"][0]["original_path"] == "new_config.out"


def test_random_out_root_file_is_rejected_when_not_declared(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "random.out").write_text("x\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert (run_ctx.execution_root / "random.out").exists()


def test_debug_txt_root_file_is_rejected_when_not_declared(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "debug.txt").write_text("x\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert (run_ctx.execution_root / "debug.txt").exists()


def test_notes_txt_root_file_is_rejected_when_not_declared(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "notes.txt").write_text("x\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert (run_ctx.execution_root / "notes.txt").exists()


def test_declared_debug_txt_is_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "debug.txt").write_text("scratch\n", encoding="utf-8")
    report = _report(run_ctx.reports_dir / "P0001.json", ["debug.txt"])

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=report, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "debug.txt"
    assert result[0]["declared_by_worker_report"] is True


def test_worker_scratch_dir_file_is_quarantined_or_moved_without_product_diff(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    scratch_dir = run_ctx.run_dir / "worker_scratch"
    scratch_dir.mkdir(parents=True)
    (scratch_dir / "debug.txt").write_text("scratch\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert (scratch_dir / "debug.txt").exists()


def _git_worker_scratch_ctx(tmp_path: Path, *, scratch_name: str = "worker_scratch") -> tuple[PatchletRunContext, object]:
    run_ctx = _git_run_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "policy.bundle").write_text("profile=no-compat\nmode=permissive\n", encoding="utf-8")
    scratch_dir = run_ctx.execution_root / scratch_name
    scratch_dir.mkdir()
    return run_ctx, before


def _write_tree(root: Path, tree: dict[str, str]) -> None:
    for rel_path, content in tree.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_untracked_worker_scratch_directory_is_quarantined(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path)
    _write_tree(run_ctx.execution_root / "worker_scratch", {"report.json": '{"status": "pass"}\n'})

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result[0]["original_path"] == "worker_scratch"
    assert result[0]["classification"] == "worker_scratch_directory"
    assert not (run_ctx.execution_root / "worker_scratch").exists()
    assert (run_ctx.target_root / result[0]["quarantine_path"]).exists()


def test_worker_scratch_directory_removed_before_diff_validation(tmp_path: Path):
    run_ctx, before = _git_worker_scratch_ctx(tmp_path)
    _write_tree(run_ctx.execution_root / "worker_scratch", {"report.json": '{"status": "pass"}\n'})

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")
    after = snapshot_status(run_ctx.execution_root)
    changed = changed_between(before, after)

    assert not (run_ctx.execution_root / "worker_scratch").exists()
    assert changed == ["policy.bundle"]


def test_worker_scratch_directory_recomputes_changed_paths_to_allowed_file_only(tmp_path: Path):
    run_ctx, before = _git_worker_scratch_ctx(tmp_path)
    _write_tree(run_ctx.execution_root / "worker_scratch", {"report.json": '{"status": "pass"}\n'})

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")
    after = snapshot_status(run_ctx.execution_root)
    changed = changed_between(before, after)
    diff_result = validate_changed_paths(changed, _patchlet())

    assert changed == ["policy.bundle"]
    assert diff_result.allowed is True


def test_worker_scratch_directory_manifest_preserves_file_hashes(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path)
    content = '{"status": "pass"}\n'
    _write_tree(run_ctx.execution_root / "worker_scratch", {"report.json": content})

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")
    record = result[0]
    entries = {entry["relative_path"]: entry for entry in record["entries"]}

    assert entries["report.json"]["sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_worker_scratch_directory_manifest_preserves_total_size(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path)
    _write_tree(run_ctx.execution_root / "worker_scratch", {"report.json": '{"status": "pass"}\n', "notes.txt": "ok\n"})

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")
    record = result[0]

    assert record["total_size_bytes"] == len('{"status": "pass"}\n'.encode("utf-8")) + len("ok\n".encode("utf-8"))


def test_worker_scratch_directory_manifest_records_quarantine_reason(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path)
    _write_tree(run_ctx.execution_root / "worker_scratch", {"report.json": '{"status": "pass"}\n'})

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result[0]["reason"] == "role_shaped_untracked_worker_scratch_directory"


def test_worker_scratch_directory_with_nested_safe_text_files_is_quarantined(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path)
    _write_tree(
        run_ctx.execution_root / "worker_scratch",
        {
            "reports/report.json": '{"status": "pass"}\n',
            "logs/notes.txt": "ok\n",
        },
    )

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result[0]["original_path"] == "worker_scratch"
    assert result[0]["file_count"] == 2


def test_worker_scratch_directory_with_executable_file_is_rejected(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path)
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    _write_tree(scratch_dir, {"report.sh": "#!/bin/sh\n"})
    (scratch_dir / "report.sh").chmod(0o755)

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert scratch_dir.exists()


def test_worker_scratch_directory_with_symlink_escape_is_rejected(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path)
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    outside = run_ctx.execution_root / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    scratch_dir.mkdir(exist_ok=True)
    (scratch_dir / "escape.txt").symlink_to(outside)

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert (scratch_dir / "escape.txt").exists()


def test_worker_scratch_directory_with_nested_git_dir_is_rejected(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path)
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    _write_tree(scratch_dir, {"report.json": '{"status": "pass"}\n'})
    (scratch_dir / ".git").mkdir()

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert scratch_dir.exists()


def test_worker_scratch_directory_with_product_like_file_is_rejected(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path)
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    _write_tree(scratch_dir, {"policy.bundle": "profile=legacy\nmode=permissive\n"})

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert scratch_dir.exists()


def test_random_scratch_directory_is_rejected(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path, scratch_name="random_scratch")
    _write_tree(run_ctx.execution_root / "random_scratch", {"report.json": '{"status": "pass"}\n'})

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert (run_ctx.execution_root / "random_scratch").exists()


def test_scratch_directory_without_worker_role_is_rejected(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path, scratch_name="scratch")
    _write_tree(run_ctx.execution_root / "scratch", {"report.json": '{"status": "pass"}\n'})

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert (run_ctx.execution_root / "scratch").exists()


def test_worker_output_directory_is_rejected(tmp_path: Path):
    run_ctx, _ = _git_worker_scratch_ctx(tmp_path, scratch_name="worker_output")
    _write_tree(run_ctx.execution_root / "worker_output", {"report.json": '{"status": "pass"}\n'})

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")

    assert result == []
    assert (run_ctx.execution_root / "worker_output").exists()


def test_tracked_worker_scratch_directory_is_rejected(tmp_path: Path):
    run_ctx = _git_run_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "policy.bundle").write_text("profile=no-compat\nmode=permissive\n", encoding="utf-8")
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    scratch_dir.mkdir()
    (scratch_dir / "report.json").write_text('{"status": "tracked"}\n', encoding="utf-8")
    _git("add", "worker_scratch/report.json", cwd=run_ctx.execution_root)
    _git("commit", "-m", "track worker scratch", cwd=run_ctx.execution_root)
    (run_ctx.execution_root / "policy.bundle").write_text("profile=no-compat\nmode=permissive\n", encoding="utf-8")
    (scratch_dir / "report.json").write_text('{"status": "changed"}\n', encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")
    after = snapshot_status(run_ctx.execution_root)
    changed = changed_between(before, after)
    diff_result = validate_changed_paths(changed, _patchlet())

    assert result == []
    assert diff_result.allowed is False
    assert "worker_scratch/report.json" in diff_result.unauthorized_paths


def test_changed_peer_product_file_still_rejected_when_worker_scratch_dir_present(tmp_path: Path):
    run_ctx, before = _git_worker_scratch_ctx(tmp_path)
    _write_tree(run_ctx.execution_root / "worker_scratch", {"report.json": '{"status": "pass"}\n'})
    (run_ctx.execution_root / "release.env").write_text("release_channel=green\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="policy.bundle")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is False
    assert "release.env" in diff_result.unauthorized_paths


def test_root_scratch_sweep_result_written(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_json_validated.txt").write_text("}\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    result = json.loads((run_ctx.run_dir / "gates" / "root_scratch_sweep_result.json").read_text(encoding="utf-8"))
    assert result["kind"] == "root_scratch_sweep_result"
    assert result["root_level_untracked_files"] == ["report_json_validated.txt"]
    assert result["classified"][0]["action"] == "quarantine"


def test_root_scratch_sweep_runs_before_diff_guard(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_json_validated.txt").write_text("}\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    record = json.loads((run_ctx.run_dir / "gates" / "scratch_artifact_quarantine_result.json").read_text(encoding="utf-8"))
    assert record["root_scratch_sweep_completed_before_diff_guard"] is True


def test_recomputed_diff_excludes_quarantined_scratch(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_json_validated.txt").write_text("}\n", encoding="utf-8")
    (run_ctx.execution_root / "service.cfg").write_text("status=ready\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert sorted(path.name for path in run_ctx.execution_root.iterdir()) == ["service.cfg"]


def test_unknown_root_conf_file_is_rejected(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "new_runtime.conf").write_text("x=1\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert (run_ctx.execution_root / "new_runtime.conf").exists()


def test_new_product_runtime_file_is_rejected_not_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "gateway.routes").write_text("route /\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert (run_ctx.execution_root / "gateway.routes").exists()


def test_allowed_product_file_still_checked_by_slice_boundary(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "service.cfg").write_text("mode=strict\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert (run_ctx.execution_root / "service.cfg").exists()


def test_declared_worker_scratch_file_is_quarantined_even_if_name_is_not_known(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "notes.tmp").write_text("scratch\n", encoding="utf-8")
    report = _report(run_ctx.reports_dir / "P0001.json", ["notes.tmp"])

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=report, allowed_product_runtime_file="service.cfg")

    assert result[0]["original_path"] == "notes.tmp"
    assert result[0]["declared_by_worker_report"] is True


def test_undeclared_non_role_shaped_file_is_rejected(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "notes.tmp").write_text("scratch\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []


def test_scratch_quarantine_does_not_allow_executable_root_file(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    path = run_ctx.execution_root / "report_check.sh"
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert path.exists()


def test_worktree_git_pointer_file_is_ignored_not_reported_as_scratch(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / ".git").write_text("gitdir: /tmp/worktree.git\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")

    assert result == []
    assert not (run_ctx.run_dir / "gates" / "scratch_artifact_quarantine_result.json").exists()


def test_worker_scratch_env_vars_are_recorded_in_command_json(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, _fake_codex_report())
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    command = json.loads((ctx.paths.runs_dir / "P0001_attempt1" / "command.json").read_text(encoding="utf-8"))
    assert command["env"]["CXOR_ATTEMPT_ROOT"].endswith(".codex-orchestrator/runs/P0001_attempt1")
    assert command["env"]["CXOR_REQUIRED_REPORT_PATH"].endswith(".codex-orchestrator/reports/P0001.json")
    assert command["env"]["CXOR_REQUIRED_PROBE_ARTIFACT_ROOT"].endswith(".artifacts/probes/P0001")
    assert command["env"]["CXOR_WORKER_SCRATCH_DIR"].endswith(".codex-orchestrator/runs/P0001_attempt1/worker_scratch")
    assert command["env"]["CXOR_QUARANTINE_DIR"].endswith(".codex-orchestrator/runs/P0001_attempt1/quarantined_scratch")


def test_worker_scratch_paths_are_recorded_in_run_manifest(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, _fake_codex_report())
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    manifest = json.loads(ctx.paths.run_manifest.read_text(encoding="utf-8"))
    entry = manifest["runs"][0]
    contract = entry["worker_scratch_contract"]
    assert contract["attempt_scratch_dir"] == ".codex-orchestrator/runs/P0001_attempt1/worker_scratch"
    assert contract["quarantine_dir"] == ".codex-orchestrator/runs/P0001_attempt1/quarantined_scratch"


def test_worker_prompt_tells_codex_not_to_write_root_scratch(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, _fake_codex_report())
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "codex_task_prompt.md").read_text(encoding="utf-8")
    assert "Do not write scratch/check/validation files in the target repository root" in text
    assert "CXOR_WORKER_SCRATCH_DIR" in text


def test_worker_memory_tells_codex_scratch_dir(git_repo: Path, tmp_path: Path, monkeypatch):
    ctx = _setup_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_executable(fake_codex, _fake_codex_report())
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    assert "CXOR_WORKER_SCRATCH_DIR" in (run_dir / "worker_memory" / "TASK_CONTRACT.md").read_text(encoding="utf-8")
    assert "worker scratch directory" in (run_dir / "worker_memory" / "LIVE_MEMORY.md").read_text(encoding="utf-8")
    assert "CXOR_WORKER_SCRATCH_DIR" in (run_dir / "worker_memory" / "WRITE_THESE_FILES.md").read_text(encoding="utf-8")
