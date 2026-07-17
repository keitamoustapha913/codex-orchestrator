from __future__ import annotations

import json
from pathlib import Path

import codex_orchestrator.validators.report_validator as report_validator
from codex_orchestrator.validators.diff_validator import validate_changed_paths
from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report, validate_patchlet_report_file
import pytest


def base_patchlet() -> dict:
    return {
        "schema_version": "1.0",
        "kind": "patchlet",
        "patchlet_id": "P0001",
        "subprompt_path": ".codex-orchestrator/subprompts/0001_app.md",
        "master_goal_ids": ["G001"],
        "invariant_ids": ["I001"],
        "evidence_ids": ["E001"],
        "graph_node_ids": ["N001"],
        "allowed_product_runtime_file": "app.py",
        "allowed_artifact_dirs": [".artifacts/probes/", ".codex-orchestrator/reports/", ".codex-orchestrator/runs/"],
        "transaction_group_id": "TG001",
        "depends_on": [],
        "status": "PENDING",
    }


def complete_report() -> dict:
    return {
        "schema_version": "2.0",
        "kind": "worker_patchlet_report",
        "patchlet_id": "P0001",
        "status": "COMPLETE",
        "changed_product_runtime_file": "app.py",
        "changed_artifact_files": [".artifacts/probes/P0001/probe.py"],
        "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
        "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "baseline failed",
            "immediate_cause": "wrong return value",
            "why_immediate_cause_happened": "state owner returned stale value",
            "deeper_owner_boundary": "app.main",
            "producer_transformer_consumer_boundary": "producer app.main -> consumer probe",
            "not_downstream_of_unprobed_state_proof": "direct toggle proved boundary",
            "negative_control_proof": "unrelated branch unchanged",
            "recursive_why_audit": ["why1", "why2", "why3"],
        },
        "before_after_state": [{"before": "bad", "after": "ok"}],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "probe created isolated temp data and cleaned it",
        "probe_artifact_refs": [{
            "patchlet_id": "P0001",
            "probe_root": ".artifacts/probes/P0001",
            "run_id": "run_001",
        }],
    }


def failed_report() -> dict:
    report = complete_report()
    report["status"] = "FAILED_WITH_EVIDENCE"
    report["changed_product_runtime_file"] = None
    report["failed_probe_evidence"] = "probe reproduced the failure deterministically"
    return report


def blocked_report() -> dict:
    report = complete_report()
    report["status"] = "BLOCKED_WITH_EVIDENCE"
    report["changed_product_runtime_file"] = None
    report["blocking_boundary_reason"] = "requires external dependency boundary outside allowed scope"
    return report


def _write_probe_artifacts(repo_root: Path, patchlet_id: str = "P0001", run_id: str = "run_001") -> None:
    probe_root = repo_root / ".artifacts" / "probes" / patchlet_id
    run_root = probe_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (probe_root / "probe.py").write_text("print('probe')\n", encoding="utf-8")
    (run_root / "row_ledger.jsonl").write_text(json.dumps({"row": 1}) + "\n", encoding="utf-8")
    (run_root / "trace_ledger.jsonl").write_text(json.dumps({"trace": 1}) + "\n", encoding="utf-8")
    (run_root / "before_state.json").write_text(json.dumps({"value": "before"}) + "\n", encoding="utf-8")
    (run_root / "after_state.json").write_text(json.dumps({"value": "after"}) + "\n", encoding="utf-8")
    (run_root / "cleanup_proof.json").write_text(json.dumps({"cleanup_passed": True}) + "\n", encoding="utf-8")


def test_diff_validator_allows_one_product_file_and_artifacts():
    result = validate_changed_paths(
        changed_paths=["app.py", ".artifacts/probes/P0001/probe.py", ".codex-orchestrator/reports/P0001.json"],
        patchlet=base_patchlet(),
    )
    assert result.allowed is True
    assert result.unauthorized_paths == []


def test_diff_validator_rejects_two_product_files():
    result = validate_changed_paths(
        changed_paths=["app.py", "other.py", ".codex-orchestrator/reports/P0001.json"],
        patchlet=base_patchlet(),
    )
    assert result.allowed is False
    assert "other.py" in result.unauthorized_paths


def test_diff_validator_rejects_frozen_workflow_artifacts():
    result = validate_changed_paths(
        changed_paths=[".codex-orchestrator/goal_spec.json", ".codex-orchestrator/reports/P0001.json"],
        patchlet=base_patchlet(),
    )
    assert result.allowed is False
    assert ".codex-orchestrator/goal_spec.json" in result.unauthorized_paths


def test_report_validator_accepts_complete_report():
    validate_patchlet_report(complete_report(), base_patchlet())


def test_report_validator_rejects_wrong_relative_product_path():
    report = complete_report()
    report["changed_product_runtime_file"] = "other.py"

    with pytest.raises(ReportValidationError) as exc_info:
        validate_patchlet_report(report, base_patchlet())

    assert exc_info.value.errors[0]["normalized_signature"] == "changed_product_runtime_file_mismatch"


def test_report_validator_rejects_absolute_product_path():
    report = complete_report()
    report["changed_product_runtime_file"] = "/tmp/worker/checkout/app.py"

    with pytest.raises(ReportValidationError):
        validate_patchlet_report(report, base_patchlet())


def _v1_report() -> dict:
    report = complete_report()
    report["schema_version"] = "1.0"
    report["kind"] = "patchlet_report"
    report["acceptance_criteria_result"] = "pass"
    return report


def test_report_validator_rejects_v1_schema_version():
    with pytest.raises(ReportValidationError):
        validate_patchlet_report(_v1_report(), base_patchlet())


def test_report_validator_rejects_v1_report_kind():
    with pytest.raises(ReportValidationError):
        validate_patchlet_report(_v1_report(), base_patchlet())


def test_report_validator_always_uses_worker_patchlet_report_v2_schema(monkeypatch: pytest.MonkeyPatch):
    schema_names = []

    def record_schema(report, schema_name):
        schema_names.append(schema_name)
        return []

    monkeypatch.setattr(report_validator, "iter_jsonschema_errors", record_schema)
    validate_patchlet_report(_v1_report(), base_patchlet())
    assert schema_names == ["worker_patchlet_report_v2.schema.json"]


def test_complete_v2_report_does_not_require_acceptance_criteria_result():
    report = complete_report()
    assert "acceptance_criteria_result" not in report
    validate_patchlet_report(report, base_patchlet())


def test_verified_no_change_v2_report_does_not_require_acceptance_criteria_result():
    report = complete_report()
    report["status"] = "VERIFIED_NO_CHANGE_NEEDED"
    report["changed_product_runtime_file"] = None
    validate_patchlet_report(report, base_patchlet())


def test_blocked_v2_report_does_not_require_acceptance_criteria_result():
    report = blocked_report()
    assert "acceptance_criteria_result" not in report
    validate_patchlet_report(report, base_patchlet())


def test_failed_v2_report_does_not_require_acceptance_criteria_result():
    report = failed_report()
    assert "acceptance_criteria_result" not in report
    validate_patchlet_report(report, base_patchlet())


def test_report_validator_rejects_vague_status():
    report = complete_report()
    report["status"] = "DONE"
    with pytest.raises(ReportValidationError):
        validate_patchlet_report(report, base_patchlet())


def test_report_validator_rejects_verified_no_change_with_product_diff():
    report = complete_report()
    report["status"] = "VERIFIED_NO_CHANGE_NEEDED"
    report["changed_product_runtime_file"] = "app.py"
    with pytest.raises(ReportValidationError):
        validate_patchlet_report(report, base_patchlet())


def test_report_validator_rejects_complete_without_root_cause():
    report = complete_report()
    report["root_cause_classification"]["immediate_cause"] = ""
    with pytest.raises(ReportValidationError):
        validate_patchlet_report(report, base_patchlet())


def test_complete_report_rejects_missing_minimal_probe():
    report = complete_report()
    report["probe_commands"] = []
    with pytest.raises(ReportValidationError, match="probe command"):
        validate_patchlet_report(report, base_patchlet())


def test_complete_report_rejects_missing_negative_control():
    report = complete_report()
    report["deterministic_run_counts"]["negative_controls"] = ""
    with pytest.raises(ReportValidationError, match="negative control"):
        validate_patchlet_report(report, base_patchlet())


def test_complete_report_rejects_missing_cleanup_proof():
    report = complete_report()
    report["cleanup_proof"] = ""
    with pytest.raises(ReportValidationError, match="cleanup_proof"):
        validate_patchlet_report(report, base_patchlet())


def test_complete_report_rejects_missing_recursive_why_audit():
    report = complete_report()
    report["root_cause_classification"]["recursive_why_audit"] = []
    with pytest.raises(ReportValidationError, match="recursive_why_audit"):
        validate_patchlet_report(report, base_patchlet())


def test_complete_report_rejects_missing_producer_transformer_consumer_boundary():
    report = complete_report()
    report["root_cause_classification"]["producer_transformer_consumer_boundary"] = ""
    with pytest.raises(ReportValidationError, match="producer_transformer_consumer_boundary"):
        validate_patchlet_report(report, base_patchlet())


def test_complete_report_rejects_timing_luck_language():
    report = complete_report()
    report["root_cause_classification"]["negative_control_proof"] = "rerun fixed it after flaky timing"
    with pytest.raises(ReportValidationError, match="timing-luck"):
        validate_patchlet_report(report, base_patchlet())


def test_verified_no_change_needed_requires_probe_and_no_product_diff():
    report = complete_report()
    report["status"] = "VERIFIED_NO_CHANGE_NEEDED"
    report["changed_product_runtime_file"] = None
    report["probe_commands"] = []
    with pytest.raises(ReportValidationError, match="probe command"):
        validate_patchlet_report(report, base_patchlet())


def test_failed_with_evidence_requires_failed_probe_evidence():
    report = failed_report()
    report["failed_probe_evidence"] = ""
    with pytest.raises(ReportValidationError, match="failed_probe_evidence"):
        validate_patchlet_report(report, base_patchlet())


def test_blocked_with_evidence_requires_boundary_reason():
    report = blocked_report()
    report["blocking_boundary_reason"] = ""
    with pytest.raises(ReportValidationError, match="blocking_boundary_reason"):
        validate_patchlet_report(report, base_patchlet())


def test_complete_report_requires_probe_artifact_refs():
    report = complete_report()
    report["probe_artifact_refs"] = []
    with pytest.raises(ReportValidationError, match="probe_artifact_refs"):
        validate_patchlet_report(report, base_patchlet())


def test_complete_report_rejects_missing_probe_artifact_files(tmp_path: Path):
    repo_root = tmp_path / "repo"
    report_path = repo_root / ".codex-orchestrator" / "reports" / "P0001.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(complete_report()) + "\n", encoding="utf-8")

    with pytest.raises(ReportValidationError, match="probe artifact"):
        validate_patchlet_report_file(report_path, base_patchlet())


def test_complete_report_accepts_valid_probe_artifact_ref(tmp_path: Path):
    repo_root = tmp_path / "repo"
    _write_probe_artifacts(repo_root)
    report_path = repo_root / ".codex-orchestrator" / "reports" / "P0001.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(complete_report()) + "\n", encoding="utf-8")

    validated = validate_patchlet_report_file(report_path, base_patchlet())

    assert validated["patchlet_id"] == "P0001"


def test_verified_no_change_needed_requires_valid_probe_artifact_ref(tmp_path: Path):
    repo_root = tmp_path / "repo"
    _write_probe_artifacts(repo_root)
    report = complete_report()
    report["status"] = "VERIFIED_NO_CHANGE_NEEDED"
    report["changed_product_runtime_file"] = None
    report_path = repo_root / ".codex-orchestrator" / "reports" / "P0001.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    validated = validate_patchlet_report_file(report_path, base_patchlet())

    assert validated["status"] == "VERIFIED_NO_CHANGE_NEEDED"


def test_failed_with_evidence_can_reference_failed_probe_artifacts(tmp_path: Path):
    repo_root = tmp_path / "repo"
    _write_probe_artifacts(repo_root)
    report = failed_report()
    report["probe_artifact_refs"] = [{
        "patchlet_id": "P0001",
        "probe_root": ".artifacts/probes/P0001",
        "run_id": "run_001",
    }]
    report_path = repo_root / ".codex-orchestrator" / "reports" / "P0001.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    validated = validate_patchlet_report_file(report_path, base_patchlet())

    assert validated["status"] == "FAILED_WITH_EVIDENCE"
