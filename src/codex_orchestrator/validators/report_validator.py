from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json
from codex_orchestrator.paths import relative_to_repo

from .schema_validator import validate_json


class ReportValidationError(Exception):
    pass


VALID_STATUSES = {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED", "BLOCKED_WITH_EVIDENCE", "FAILED_WITH_EVIDENCE"}
REQUIRED_ROOT_CAUSE_FIELDS = [
    "observed_failure",
    "immediate_cause",
    "why_immediate_cause_happened",
    "deeper_owner_boundary",
    "producer_transformer_consumer_boundary",
    "not_downstream_of_unprobed_state_proof",
    "negative_control_proof",
    "recursive_why_audit",
]
FORBIDDEN_TIMING_LUCK_PHRASES = [
    "flaky",
    "transient",
    "temporary",
    "ignore",
    "rerun fixed it",
]


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)


def _contains_forbidden_timing_luck_language(report: dict) -> bool:
    for text in _iter_strings(report.get("root_cause_classification") or {}):
        lowered = text.lower()
        if any(phrase in lowered for phrase in FORBIDDEN_TIMING_LUCK_PHRASES):
            return True
    for text in _iter_strings(report.get("failed_probe_evidence")):
        lowered = text.lower()
        if any(phrase in lowered for phrase in FORBIDDEN_TIMING_LUCK_PHRASES):
            return True
    for text in _iter_strings(report.get("blocking_boundary_reason")):
        lowered = text.lower()
        if any(phrase in lowered for phrase in FORBIDDEN_TIMING_LUCK_PHRASES):
            return True
    return False


def validate_patchlet_report(report: dict, patchlet: dict | None = None) -> None:
    schema_errors = validate_json(report, "patchlet_report.schema.json")
    if schema_errors:
        raise ReportValidationError("; ".join(schema_errors))

    status = report.get("status")
    if status not in VALID_STATUSES:
        raise ReportValidationError(f"Invalid patchlet report status: {status}")

    if patchlet is not None and report.get("patchlet_id") != patchlet.get("patchlet_id"):
        raise ReportValidationError("Report patchlet_id does not match patchlet manifest")

    if not report.get("probe_commands"):
        raise ReportValidationError("Report must include at least one probe command")

    if not _nonempty(report.get("cleanup_proof")):
        raise ReportValidationError("Report must include cleanup_proof")
    if _contains_forbidden_timing_luck_language(report):
        raise ReportValidationError("Report contains forbidden timing-luck language")

    run_counts = report.get("deterministic_run_counts") or {}
    if status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}:
        if not _nonempty(run_counts.get("baseline")):
            raise ReportValidationError("Report must declare baseline deterministic run count")
        if not _nonempty(run_counts.get("negative_controls")):
            raise ReportValidationError("Report must declare negative control deterministic run count")

    root = report.get("root_cause_classification") or {}
    if status == "COMPLETE":
        if not _nonempty(report.get("changed_product_runtime_file")):
            raise ReportValidationError("COMPLETE requires changed_product_runtime_file")
        if report.get("acceptance_criteria_result") != "pass":
            raise ReportValidationError("COMPLETE requires acceptance_criteria_result=pass")
        if not _nonempty(run_counts.get("proof_of_fix")):
            raise ReportValidationError("COMPLETE requires proof_of_fix deterministic run count")
        for field in REQUIRED_ROOT_CAUSE_FIELDS:
            if not _nonempty(root.get(field)):
                raise ReportValidationError(f"COMPLETE requires root_cause_classification.{field}")

    if status == "VERIFIED_NO_CHANGE_NEEDED":
        if report.get("changed_product_runtime_file") is not None:
            raise ReportValidationError("VERIFIED_NO_CHANGE_NEEDED cannot include a product/runtime diff")
        if report.get("acceptance_criteria_result") != "pass":
            raise ReportValidationError("VERIFIED_NO_CHANGE_NEEDED requires acceptance_criteria_result=pass")

    if status == "BLOCKED_WITH_EVIDENCE":
        if report.get("acceptance_criteria_result") != "blocked":
            raise ReportValidationError("BLOCKED_WITH_EVIDENCE requires acceptance_criteria_result=blocked")
        if not _nonempty(root.get("observed_failure")):
            raise ReportValidationError("BLOCKED_WITH_EVIDENCE requires observed_failure evidence")
        if not _nonempty(report.get("blocking_boundary_reason")):
            raise ReportValidationError("BLOCKED_WITH_EVIDENCE requires blocking_boundary_reason")

    if status == "FAILED_WITH_EVIDENCE":
        if report.get("acceptance_criteria_result") != "fail":
            raise ReportValidationError("FAILED_WITH_EVIDENCE requires acceptance_criteria_result=fail")
        if not _nonempty(root.get("observed_failure")):
            raise ReportValidationError("FAILED_WITH_EVIDENCE requires observed_failure evidence")
        if not _nonempty(report.get("failed_probe_evidence")):
            raise ReportValidationError("FAILED_WITH_EVIDENCE requires failed_probe_evidence")


def validate_patchlet_report_file(path: Path, patchlet: dict | None = None) -> dict:
    report = read_json(path)
    validate_patchlet_report(report, patchlet)
    return report
