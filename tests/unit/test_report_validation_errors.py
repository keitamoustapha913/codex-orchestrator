from __future__ import annotations

from codex_orchestrator.report_validation_errors import detail_from_jsonschema_error
from codex_orchestrator.validators.schema_validator import iter_jsonschema_errors, validate_json


def _bad_report():
    return {
        "schema_version": "1.0",
        "kind": "patchlet_report",
        "patchlet_id": "P0002",
        "status": "VERIFIED_NO_CHANGE_NEEDED",
        "changed_product_runtime_file": None,
        "changed_artifact_files": [],
        "probe_commands": ["probe"],
        "deterministic_run_counts": {"baseline": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {},
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "ok",
        "probe_artifact_refs": [".artifacts/probes/P0002/comparison.txt"],
        "acceptance_criteria_result": "pass",
    }


def _detail():
    error = next(iter(iter_jsonschema_errors(_bad_report(), "patchlet_report.schema.json")))
    return detail_from_jsonschema_error(error, error_id="RVE000001", patchlet_id="P0002")


def test_jsonschema_type_error_preserves_json_pointer():
    assert _detail()["json_pointer"] == "/probe_artifact_refs/0"


def test_jsonschema_type_error_preserves_schema_path():
    assert _detail()["schema_path"] == "/properties/probe_artifact_refs/items/type"


def test_jsonschema_type_error_preserves_expected_and_actual_type():
    detail = _detail()
    assert detail["expected_type"] == "object"
    assert detail["actual_type"] == "string"


def test_probe_artifact_refs_string_item_gets_specific_signature():
    assert _detail()["normalized_signature"] == "probe_artifact_refs_not_objects"


def test_probe_artifact_refs_missing_required_field_gets_specific_signature():
    report = _bad_report()
    report["probe_artifact_refs"] = [{"patchlet_id": "P0002", "probe_root": ".artifacts/probes/P0002"}]
    error = next(iter(iter_jsonschema_errors(report, "patchlet_report.schema.json")))
    detail = detail_from_jsonschema_error(error, error_id="RVE000001", patchlet_id="P0002")
    assert detail["normalized_signature"] == "probe_artifact_refs_missing_required_field"


def test_probe_artifact_refs_unsafe_path_gets_specific_signature():
    from codex_orchestrator.report_validation_errors import report_validation_error_detail

    detail = report_validation_error_detail(field="probe_artifact_refs", message="unsafe", normalized_signature="probe_artifact_refs_unsafe_path")
    assert detail["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_probe_artifact_refs_missing_file_gets_specific_signature():
    from codex_orchestrator.report_validation_errors import report_validation_error_detail

    detail = report_validation_error_detail(field="probe_artifact_refs", message="missing", normalized_signature="probe_artifact_refs_missing_file")
    assert detail["normalized_signature"] == "probe_artifact_refs_missing_file"


def test_unknown_schema_error_gets_unknown_report_validation_error():
    from codex_orchestrator.report_validation_errors import report_validation_error_detail

    detail = report_validation_error_detail(field="x", message="unknown")
    assert detail["normalized_signature"] == "unknown_report_validation_error"


def test_structured_error_includes_repair_hint():
    assert "object-shaped" in _detail()["repair_hint"]


def test_structured_error_includes_canonical_example_for_probe_ref_shape():
    example = _detail()["canonical_example"]
    assert example["patchlet_id"] == "P0002"
    assert example["files"][0]["path"] == ".artifacts/probes/P0002/comparison.txt"


def test_report_validation_errors_schema_validates_generated_artifact():
    from codex_orchestrator.report_validation_errors import errors_artifact

    artifact = errors_artifact(attempt_id="P0002_attempt1", patchlet_id="P0002", report_path="raw", canonical_report_path="canonical", valid=False, errors=[_detail()])
    assert validate_json(artifact, "report_validation_errors.schema.json") == []
