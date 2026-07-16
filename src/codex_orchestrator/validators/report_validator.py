from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib

from codex_orchestrator.jsonio import read_json
from codex_orchestrator.report_validation_errors import detail_from_jsonschema_error, report_validation_error_detail
from codex_orchestrator.report_contract import contract_drift_errors
from codex_orchestrator.semantic_goals import load_semantic_goal_spec, required_structured_criteria

from .probe_artifact_validator import validate_probe_artifact_run
from .schema_validator import iter_jsonschema_errors


class ReportValidationError(Exception):
    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.errors = errors or []


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


def _error(field: str, message: str, *, signature: str = "patchlet_report_schema_violation", pointer: str = "") -> dict[str, Any]:
    return report_validation_error_detail(
        field=field,
        json_pointer=pointer,
        schema_path="",
        message=message,
        normalized_signature=signature,
        repair_hint=message,
    )


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _semantic_probe_ref_errors(report: dict, *, patchlet: dict | None, repo_root: Path | None) -> list[dict[str, Any]]:
    root = repo_root.resolve() if repo_root else None
    errors: list[dict[str, Any]] = []
    for index, ref in enumerate(report.get("probe_artifact_refs") or []):
        pointer = f"/probe_artifact_refs/{index}"
        if patchlet is not None and ref.get("patchlet_id") != patchlet.get("patchlet_id"):
            errors.append(_error("probe_artifact_refs", "Report probe_artifact_refs patchlet_id does not match report patchlet_id", signature="probe_artifact_refs_patchlet_mismatch", pointer=pointer))
        if ref.get("patchlet_id") != report.get("patchlet_id"):
            errors.append(_error("probe_artifact_refs", "Report probe_artifact_refs patchlet_id does not match report patchlet_id", signature="probe_artifact_refs_patchlet_mismatch", pointer=pointer))
        if root is None:
            continue
        probe_root = (root / ref["probe_root"]).resolve()
        artifacts_root = root / ".artifacts" / "probes"
        if not _is_under(probe_root, artifacts_root):
            errors.append(_error("probe_artifact_refs", "Report probe_artifact_refs probe_root must be under .artifacts/probes/", signature="probe_artifact_refs_unsafe_path", pointer=f"{pointer}/probe_root"))
            continue
        files = ref.get("files")
        if files is None:
            run_dir = probe_root / ref["run_id"]
            if ref["run_id"] != "default":
                result = validate_probe_artifact_run(run_dir, patchlet_id=ref["patchlet_id"])
                if not result["valid"]:
                    codes = ", ".join(error["code"] for error in result["errors"])
                    errors.append(_error("probe_artifact_refs", f"Invalid probe artifact reference: {codes}; probe artifact validation failed", pointer=pointer))
            continue
        for file_index, file_item in enumerate(files):
            path = (root / file_item["path"]).resolve()
            file_pointer = f"{pointer}/files/{file_index}"
            if not _is_under(path, probe_root):
                errors.append(_error("probe_artifact_refs", "Probe artifact file must be under probe_root", signature="probe_artifact_refs_unsafe_path", pointer=f"{file_pointer}/path"))
                continue
            if not path.exists():
                errors.append(_error("probe_artifact_refs", f"Probe artifact file does not exist: {file_item['path']}", signature="probe_artifact_refs_missing_file", pointer=f"{file_pointer}/path"))
                continue
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if file_item.get("sha256") != digest:
                errors.append(_error("probe_artifact_refs", f"Probe artifact sha256 mismatch: {file_item['path']}", signature="probe_artifact_refs_unsafe_path", pointer=f"{file_pointer}/sha256"))
            if file_item.get("size_bytes") != path.stat().st_size:
                errors.append(_error("probe_artifact_refs", f"Probe artifact size_bytes mismatch: {file_item['path']}", signature="probe_artifact_refs_unsafe_path", pointer=f"{file_pointer}/size_bytes"))
    return errors


def _semantic_goal_result_errors(report: dict, *, repo_root: Path | None) -> list[dict[str, Any]]:
    spec = load_semantic_goal_spec(repo_root) if repo_root else None
    criteria = required_structured_criteria(spec)
    if not criteria:
        return []
    errors: list[dict[str, Any]] = []
    results = report.get("semantic_goal_results")
    if not isinstance(results, list):
        return [
            _error(
                "semantic_goal_results",
                "Structured semantic goals require semantic_goal_results in patchlet reports",
                signature="semantic_goal_results_missing",
                pointer="/semantic_goal_results",
            )
        ]
    by_id = {item.get("criterion_id"): item for item in results if isinstance(item, dict)}
    for criterion in criteria:
        criterion_id = criterion["criterion_id"]
        result = by_id.get(criterion_id)
        if result is None:
            errors.append(_error("semantic_goal_results", f"Missing semantic result for required criterion {criterion_id}", signature="semantic_goal_results_missing_required_criterion", pointer="/semantic_goal_results"))
            continue
        if result.get("expected_value") != criterion.get("expected_value"):
            errors.append(_error("semantic_goal_results", f"Semantic result {criterion_id} expected_value does not match semantic goal spec", signature="semantic_goal_results_wrong_expected_value", pointer="/semantic_goal_results"))
        actual = result.get("actual_value")
        expected = result.get("expected_value")
        if result.get("passed") is True and actual != expected:
            errors.append(_error("semantic_goal_results", f"Semantic result {criterion_id} cannot pass when actual_value differs from expected_value", signature="semantic_goal_results_self_contradictory", pointer="/semantic_goal_results"))
        if report.get("status") in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"} and result.get("passed") is not True:
            errors.append(_error("semantic_goal_results", f"{report.get('status')} requires semantic result {criterion_id} to pass", signature="semantic_goal_results_failed", pointer="/semantic_goal_results"))
    return errors


def validate_patchlet_report_structured(report: dict, patchlet: dict | None = None, *, repo_root: Path | None = None) -> dict[str, Any]:
    contract_errors = contract_drift_errors()
    if contract_errors:
        errors = [_error("report_contract", message, signature="WORKER_REPORT_CONTRACT_DRIFT") for message in contract_errors]
        return {"valid": False, "errors": errors, "message": "; ".join(error["message"] for error in errors)}
    structured = [
        detail_from_jsonschema_error(error, error_id=f"RVE{index:06d}", patchlet_id=report.get("patchlet_id") or (patchlet or {}).get("patchlet_id"))
        for index, error in enumerate(iter_jsonschema_errors(report, "worker_patchlet_report_v2.schema.json" if report.get("schema_version") == "2.0" else "patchlet_report.schema.json"), start=1)
    ]
    if structured:
        return {"valid": False, "errors": structured, "message": "; ".join(error["message"] for error in structured)}

    semantic_errors: list[dict[str, Any]] = []
    status = report.get("status")
    if status not in VALID_STATUSES:
        semantic_errors.append(_error("status", f"Invalid patchlet report status: {status}"))

    if patchlet is not None and report.get("patchlet_id") != patchlet.get("patchlet_id"):
        semantic_errors.append(_error("patchlet_id", "Report patchlet_id does not match patchlet manifest"))

    if not report.get("probe_commands"):
        semantic_errors.append(_error("probe_commands", "Report must include at least one probe command"))

    if not _nonempty(report.get("cleanup_proof")):
        semantic_errors.append(_error("cleanup_proof", "Report must include cleanup_proof"))
    if _contains_forbidden_timing_luck_language(report):
        semantic_errors.append(_error("report", "Report contains forbidden timing-luck language"))

    run_counts = report.get("deterministic_run_counts") or {}
    probe_artifact_refs = report.get("probe_artifact_refs") or []
    if status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}:
        if not _nonempty(run_counts.get("baseline")):
            semantic_errors.append(_error("deterministic_run_counts", "Report must declare baseline deterministic run count"))
        if not _nonempty(run_counts.get("negative_controls")):
            semantic_errors.append(_error("deterministic_run_counts", "Report must declare negative control deterministic run count"))
        if not probe_artifact_refs:
            semantic_errors.append(_error("probe_artifact_refs", "Report must include probe_artifact_refs"))

    root = report.get("root_cause_classification") or {}
    if status == "COMPLETE":
        if not _nonempty(report.get("changed_product_runtime_file")):
            semantic_errors.append(_error("changed_product_runtime_file", "COMPLETE requires changed_product_runtime_file"))
        if report.get("schema_version") != "2.0" and report.get("acceptance_criteria_result") != "pass":
            semantic_errors.append(_error("acceptance_criteria_result", "COMPLETE requires acceptance_criteria_result=pass"))
        if not _nonempty(run_counts.get("proof_of_fix")):
            semantic_errors.append(_error("deterministic_run_counts", "COMPLETE requires proof_of_fix deterministic run count"))
        for field in REQUIRED_ROOT_CAUSE_FIELDS:
            if not _nonempty(root.get(field)):
                semantic_errors.append(_error("root_cause_classification", f"COMPLETE requires root_cause_classification.{field}"))

    if status == "VERIFIED_NO_CHANGE_NEEDED":
        if report.get("changed_product_runtime_file") is not None:
            semantic_errors.append(_error("changed_product_runtime_file", "VERIFIED_NO_CHANGE_NEEDED cannot include a product/runtime diff"))
        if report.get("schema_version") != "2.0" and report.get("acceptance_criteria_result") != "pass":
            semantic_errors.append(_error("acceptance_criteria_result", "VERIFIED_NO_CHANGE_NEEDED requires acceptance_criteria_result=pass"))

    if status == "BLOCKED_WITH_EVIDENCE":
        if report.get("schema_version") != "2.0" and report.get("acceptance_criteria_result") != "blocked":
            semantic_errors.append(_error("acceptance_criteria_result", "BLOCKED_WITH_EVIDENCE requires acceptance_criteria_result=blocked"))
        if not _nonempty(root.get("observed_failure")):
            semantic_errors.append(_error("root_cause_classification", "BLOCKED_WITH_EVIDENCE requires observed_failure evidence"))
        if not _nonempty(report.get("blocking_boundary_reason")):
            semantic_errors.append(_error("blocking_boundary_reason", "BLOCKED_WITH_EVIDENCE requires blocking_boundary_reason"))

    if status == "FAILED_WITH_EVIDENCE":
        if report.get("schema_version") != "2.0" and report.get("acceptance_criteria_result") != "fail":
            semantic_errors.append(_error("acceptance_criteria_result", "FAILED_WITH_EVIDENCE requires acceptance_criteria_result=fail"))
        if not _nonempty(root.get("observed_failure")):
            semantic_errors.append(_error("root_cause_classification", "FAILED_WITH_EVIDENCE requires observed_failure evidence"))
        if not _nonempty(report.get("failed_probe_evidence")):
            semantic_errors.append(_error("failed_probe_evidence", "FAILED_WITH_EVIDENCE requires failed_probe_evidence"))
    semantic_errors.extend(_semantic_probe_ref_errors(report, patchlet=patchlet, repo_root=repo_root))
    semantic_errors.extend(_semantic_goal_result_errors(report, repo_root=repo_root))
    if semantic_errors:
        for index, error in enumerate(semantic_errors, start=1):
            error["error_id"] = f"RVE{index:06d}"
        return {"valid": False, "errors": semantic_errors, "message": "; ".join(error["message"] for error in semantic_errors)}
    return {"valid": True, "errors": [], "message": None}


def validate_patchlet_report(report: dict, patchlet: dict | None = None) -> None:
    result = validate_patchlet_report_structured(report, patchlet)
    if not result["valid"]:
        raise ReportValidationError(result["message"], result["errors"])


def validate_patchlet_report_file(path: Path, patchlet: dict | None = None) -> dict:
    report = read_json(path)
    repo_root = path.parents[2] if len(path.parents) >= 3 else path.parent
    result = validate_patchlet_report_structured(report, patchlet, repo_root=repo_root)
    if not result["valid"]:
        raise ReportValidationError(result["message"], result["errors"])
    return report
