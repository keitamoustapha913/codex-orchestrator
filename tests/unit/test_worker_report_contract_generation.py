from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import codex_orchestrator.report_contract as report_contract
from worker_report_fixtures import (
    blocked_worker_patchlet_report_v2,
    complete_worker_patchlet_report_v2,
    failed_worker_patchlet_report_v2,
    verified_no_change_worker_patchlet_report_v2,
    worker_patchlet_report_v2,
)
from codex_orchestrator.report_contract import (
    FIELD_METADATA,
    SEMANTIC_GOAL_RESULT_SHORTHAND_FIELDS,
    canonical_example_report,
    contract_drift_errors,
    contract_fingerprint,
    contract_payload,
    generated_v2_schema,
    known_field_type_table,
    render_primary_worker_report_template,
    render_reorganization_worker_instructions,
    required_field_list,
)


ROOT = Path(__file__).parents[2]


def test_schema_fields_and_required_fields_equal_contract():
    schema = json.loads((ROOT / "src/codex_orchestrator/schemas/worker_patchlet_report_v2.schema.json").read_text())
    assert set(schema["properties"]) == set(FIELD_METADATA)
    assert schema["required"] == required_field_list()
    assert set(known_field_type_table()) == set(schema["properties"])


def test_generated_schema_and_examples_validate():
    validator = jsonschema.Draft202012Validator(generated_v2_schema())
    assert list(validator.iter_errors(canonical_example_report())) == []
    for path in (ROOT / "examples/worker_patchlet_report_v2.json", ROOT / "docs/worker_patchlet_report_v2_example.json"):
        assert list(validator.iter_errors(json.loads(path.read_text()))) == []


def test_rendered_prompt_and_reorganization_instructions_are_contract_derived():
    assert (ROOT / "src/codex_orchestrator/prompt_templates/worker_patchlet_report_v2.md").read_text() == render_primary_worker_report_template()
    assert (ROOT / "src/codex_orchestrator/prompt_templates/report_reorganization_worker_instructions.md").read_text() == render_reorganization_worker_instructions()


def test_worker_report_contract_contains_no_legacy_alias_table():
    payload = contract_payload()
    assert "legacy_aliases" not in payload
    assert "changed_runtime_file" not in json.dumps(payload, sort_keys=True)


def test_contract_fingerprint_contains_no_legacy_alias_payload():
    payload = contract_payload()
    assert set(payload) == {
        "name",
        "worker_input_fields",
        "derived_canonical_fields",
        "semantic_goal_result_shorthand",
        "extension_policy",
    }
    assert payload["semantic_goal_result_shorthand"]["required"] == ["goal_item_id", "result"]
    assert "goal_item" not in payload["semantic_goal_result_shorthand"]["fields"]
    assert contract_fingerprint() == contract_fingerprint()


def test_contract_output_is_deterministic_and_fingerprint_changes_on_contract_change(monkeypatch: pytest.MonkeyPatch):
    before = contract_fingerprint()
    assert before == contract_fingerprint()
    monkeypatch.setitem(FIELD_METADATA, "deliberate_test_field", {"json_type": "string", "python_types": (str,), "required": False, "description": "test", "reference_class": "NONE"})
    assert contract_fingerprint() != before


def test_contract_fingerprint_changes_on_semantic_shorthand_change(monkeypatch: pytest.MonkeyPatch):
    before = contract_fingerprint()
    monkeypatch.setitem(
        SEMANTIC_GOAL_RESULT_SHORTHAND_FIELDS,
        "prompt_only_semantic_field",
        {"json_type": "string", "required": False, "description": "test"},
    )
    assert contract_fingerprint() != before


def test_worker_input_contract_excludes_worker_semantic_claims():
    assert "worker_semantic_claims" not in FIELD_METADATA


def test_worker_input_schema_excludes_worker_semantic_claims():
    assert "worker_semantic_claims" not in generated_v2_schema()["properties"]


def test_primary_worker_template_excludes_worker_semantic_claims():
    assert "worker_semantic_claims" not in render_primary_worker_report_template()


def test_reorganization_known_fields_exclude_worker_semantic_claims():
    assert "worker_semantic_claims" not in render_reorganization_worker_instructions()


def test_contract_payload_separates_worker_input_and_derived_fields():
    payload = contract_payload()
    assert set(payload) == {
        "name",
        "worker_input_fields",
        "derived_canonical_fields",
        "semantic_goal_result_shorthand",
        "extension_policy",
    }
    assert "worker_semantic_claims" not in payload["worker_input_fields"]
    assert "worker_semantic_claims" in payload["derived_canonical_fields"]
    assert not set(required_field_list()) & set(payload["derived_canonical_fields"])


def test_contract_fingerprint_covers_derived_field_ownership(monkeypatch: pytest.MonkeyPatch):
    derived_fields = getattr(report_contract, "DERIVED_CANONICAL_REPORT_FIELD_METADATA", {})
    assert "worker_semantic_claims" in derived_fields
    before = contract_fingerprint()
    monkeypatch.setitem(
        derived_fields,
        "deliberate_derived_field",
        {
            "json_type": "string",
            "description": "derived ownership fingerprint test",
            "producer": "orchestrator",
        },
    )
    assert contract_fingerprint() != before


def _generated_schema_report(**overrides):
    report = canonical_example_report()
    report.update(overrides)
    return report


def _generated_schema_errors(report):
    return list(jsonschema.Draft202012Validator(generated_v2_schema()).iter_errors(report))


def test_generated_v2_schema_requires_object_probe_artifact_refs():
    report = _generated_schema_report(probe_artifact_refs=[".artifacts/probes/P0005/result.json"])
    assert _generated_schema_errors(report)


def test_generated_v2_schema_requires_probe_ref_identity_fields():
    report = _generated_schema_report(
        probe_artifact_refs=[
            {"patchlet_id": "P0005", "probe_root": ".artifacts/probes/P0005"}
        ]
    )
    assert _generated_schema_errors(report)


def test_generated_v2_schema_requires_probe_file_metadata():
    report = _generated_schema_report(
        probe_artifact_refs=[
            {
                "patchlet_id": "P0005",
                "probe_root": ".artifacts/probes/P0005",
                "run_id": "run-1",
                "files": [
                    {
                        "path": ".artifacts/probes/P0005/result.json",
                        "kind": "probe_result",
                        "size_bytes": 1,
                    }
                ],
            }
        ]
    )
    assert _generated_schema_errors(report)


def test_generated_v2_schema_requires_string_probe_commands():
    report = _generated_schema_report(probe_commands=[{"command": "pytest -q"}])
    assert _generated_schema_errors(report)


def test_generated_v2_schema_accepts_canonical_semantic_result():
    report = _generated_schema_report(
        semantic_goal_results=[
            {
                "criterion_id": "PO001",
                "kind": "orchestrator_verified_proof_obligation_result",
                "expected_value": "ready",
                "actual_value": "ready",
                "passed": True,
            }
        ]
    )
    assert _generated_schema_errors(report) == []


def test_generated_v2_schema_accepts_goal_item_id_shorthand():
    report = _generated_schema_report(
        semantic_goal_results=[{"goal_item_id": "GI001", "result": "limits.mjs is ready"}]
    )
    assert _generated_schema_errors(report) == []


def test_generated_v2_schema_rejects_goal_item_alias():
    report = _generated_schema_report(
        semantic_goal_results=[{"goal_item": "GI001", "result": "limits.mjs is ready"}]
    )
    assert _generated_schema_errors(report)


def test_generated_v2_schema_rejects_semantic_shorthand_without_result():
    report = _generated_schema_report(semantic_goal_results=[{"goal_item_id": "GI001"}])
    assert _generated_schema_errors(report)


def test_generated_v2_schema_includes_blocked_boundary_reason_input():
    schema = generated_v2_schema()
    assert schema["properties"]["blocking_boundary_reason"]["type"] == "string"
    assert "blocking_boundary_reason" not in schema["required"]


def test_generated_v2_schema_includes_failed_probe_evidence_input():
    schema = generated_v2_schema()
    assert schema["properties"]["failed_probe_evidence"]["type"] == "string"
    assert "failed_probe_evidence" not in schema["required"]


def test_prompt_only_field_without_contract_is_drift():
    prompt_fields = set(FIELD_METADATA) | {"prompt_only_field"}
    with pytest.raises(AssertionError, match="prompt_only_field"):
        assert prompt_fields == set(FIELD_METADATA), "prompt_only_field"


def test_production_contract_artifacts_have_no_drift():
    assert contract_drift_errors() == []


def test_shared_test_report_fixture_validates_against_generated_v2_schema():
    validator = jsonschema.Draft202012Validator(generated_v2_schema())
    reports = [
        worker_patchlet_report_v2(),
        complete_worker_patchlet_report_v2(),
        verified_no_change_worker_patchlet_report_v2(),
        failed_worker_patchlet_report_v2(),
        blocked_worker_patchlet_report_v2(),
    ]
    assert [list(validator.iter_errors(report)) for report in reports] == [[], [], [], [], []]


def test_shared_test_report_fixture_contains_no_legacy_fields():
    for report in (
        worker_patchlet_report_v2(),
        complete_worker_patchlet_report_v2(),
        failed_worker_patchlet_report_v2(),
        blocked_worker_patchlet_report_v2(),
    ):
        assert report["schema_version"] == "2.0"
        assert report["kind"] == "worker_patchlet_report"
        assert "acceptance_criteria_result" not in report


def test_shared_test_report_fixture_contains_no_derived_worker_fields():
    report = worker_patchlet_report_v2()
    assert "worker_semantic_claims" not in report
    assert "worker_semantic_quality_warnings" not in report
    assert "semantic_goal_results_raw" not in report


def test_contract_drift_has_dedicated_failure_code(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(FIELD_METADATA, "stale_runtime_field", {"json_type": "string", "python_types": (str,), "required": True, "description": "stale", "reference_class": "NONE"})
    assert any(error.startswith("WORKER_REPORT_CONTRACT_DRIFT:") for error in contract_drift_errors())
