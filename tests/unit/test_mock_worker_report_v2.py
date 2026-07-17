from __future__ import annotations

from codex_orchestrator.workers.mock import _default_report
from codex_orchestrator.validators.schema_validator import validate_json


def _patchlet() -> dict:
    return {
        "patchlet_id": "P0001",
        "allowed_product_runtime_file": "app.py",
    }


def _report_with_status(status: str) -> dict:
    report = _default_report(_patchlet())
    report["status"] = status
    if status in {"BLOCKED_WITH_EVIDENCE", "FAILED_WITH_EVIDENCE"}:
        report["changed_product_runtime_file"] = None
    if status == "BLOCKED_WITH_EVIDENCE":
        report["blocking_boundary_reason"] = "bounded external dependency"
    if status == "FAILED_WITH_EVIDENCE":
        report["failed_probe_evidence"] = "probe failed deterministically"
    return report


def test_mock_worker_default_handoff_uses_schema_version_1():
    assert _default_report(_patchlet())["schema_version"] == "1.0"


def test_mock_worker_default_handoff_uses_task_completion_kind():
    assert _default_report(_patchlet())["kind"] == "task_worker_completion_handoff"


def test_mock_worker_default_report_has_no_acceptance_criteria_result():
    assert "acceptance_criteria_result" not in _default_report(_patchlet())


def test_mock_worker_complete_handoff_remains_task_only():
    report = _report_with_status("COMPLETE")
    assert (report["schema_version"], report["kind"]) == (
        "1.0",
        "task_worker_completion_handoff",
    )


def test_mock_worker_failed_handoff_remains_task_only():
    report = _report_with_status("FAILED_WITH_EVIDENCE")
    assert (report["schema_version"], report["kind"]) == (
        "1.0",
        "task_worker_completion_handoff",
    )


def test_mock_worker_blocked_handoff_remains_task_only():
    report = _report_with_status("BLOCKED_WITH_EVIDENCE")
    assert (report["schema_version"], report["kind"]) == (
        "1.0",
        "task_worker_completion_handoff",
    )


def test_mock_worker_handoff_validates_against_task_handoff_schema():
    assert validate_json(
        _default_report(_patchlet()),
        "task_worker_completion_handoff.schema.json",
    ) == []


def test_mock_worker_report_contains_no_worker_owned_semantic_claims():
    assert "worker_semantic_claims" not in _default_report(_patchlet())
