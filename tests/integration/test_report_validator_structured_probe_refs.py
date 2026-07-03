from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report_file, validate_patchlet_report_structured


def _report(refs):
    return {
        "schema_version": "1.0",
        "kind": "patchlet_report",
        "patchlet_id": "P0001",
        "status": "VERIFIED_NO_CHANGE_NEEDED",
        "changed_product_runtime_file": None,
        "changed_artifact_files": [],
        "probe_commands": ["probe"],
        "deterministic_run_counts": {"baseline": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {"observed_failure": "none", "immediate_cause": "none", "why_immediate_cause_happened": "none", "deeper_owner_boundary": "app.py", "producer_transformer_consumer_boundary": "probe", "not_downstream_of_unprobed_state_proof": "probe", "negative_control_proof": "probe", "recursive_why_audit": ["why"]},
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "ok",
        "probe_artifact_refs": refs,
        "acceptance_criteria_result": "pass",
    }


def test_validate_patchlet_report_returns_structured_success():
    result = validate_patchlet_report_structured(_report([{"patchlet_id": "P0001", "probe_root": ".artifacts/probes/P0001", "run_id": "default"}]))
    assert result["valid"] is True


def test_validate_patchlet_report_returns_structured_schema_errors():
    result = validate_patchlet_report_structured(_report([".artifacts/probes/P0001/a.txt"]))
    assert result["valid"] is False
    assert result["errors"][0]["json_pointer"] == "/probe_artifact_refs/0"


def test_validate_patchlet_report_rejects_canonical_string_probe_refs():
    result = validate_patchlet_report_structured(_report([".artifacts/probes/P0001/a.txt"]))
    assert result["errors"][0]["actual_type"] == "string"


def test_validate_patchlet_report_includes_probe_artifact_refs_not_objects_signature():
    result = validate_patchlet_report_structured(_report([".artifacts/probes/P0001/a.txt"]))
    assert result["errors"][0]["normalized_signature"] == "probe_artifact_refs_not_objects"


def test_validate_patchlet_report_includes_probe_root_semantic_errors(git_repo: Path):
    result = validate_patchlet_report_structured(_report([{"patchlet_id": "P0001", "probe_root": "tmp", "run_id": "default"}]), repo_root=git_repo)
    assert result["errors"][0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_validate_patchlet_report_includes_file_metadata_errors(git_repo: Path):
    path = git_repo / ".artifacts/probes/P0001/a.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    result = validate_patchlet_report_structured(_report([{"patchlet_id": "P0001", "probe_root": ".artifacts/probes/P0001", "run_id": "default", "files": [{"path": ".artifacts/probes/P0001/a.txt", "kind": "a", "sha256": "0" * 64, "size_bytes": 1}]}]), repo_root=git_repo)
    assert "sha256" in result["message"]


def test_validate_patchlet_report_human_message_is_preserved():
    result = validate_patchlet_report_structured(_report([".artifacts/probes/P0001/a.txt"]))
    assert "is not of type 'object'" in result["message"]


def test_validate_patchlet_report_file_uses_canonical_report_path(git_repo: Path):
    report_path = git_repo / ".codex-orchestrator/reports/P0001.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(_report([".artifacts/probes/P0001/a.txt"])), encoding="utf-8")
    try:
        validate_patchlet_report_file(report_path, {"patchlet_id": "P0001"})
    except ReportValidationError as exc:
        assert exc.errors[0]["normalized_signature"] == "probe_artifact_refs_not_objects"


def test_report_validator_does_not_mutate_report_file(git_repo: Path):
    report_path = git_repo / ".codex-orchestrator/reports/P0001.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_report([".artifacts/probes/P0001/a.txt"]))
    report_path.write_text(text, encoding="utf-8")
    try:
        validate_patchlet_report_file(report_path, {"patchlet_id": "P0001"})
    except ReportValidationError:
        pass
    assert report_path.read_text(encoding="utf-8") == text
