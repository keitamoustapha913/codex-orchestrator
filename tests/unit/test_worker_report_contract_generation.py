from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from codex_orchestrator.report_contract import (
    FIELD_METADATA,
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
    assert set(payload) == {"name", "fields", "extension_policy"}
    assert contract_fingerprint() == contract_fingerprint()


def test_contract_output_is_deterministic_and_fingerprint_changes_on_contract_change(monkeypatch: pytest.MonkeyPatch):
    before = contract_fingerprint()
    assert before == contract_fingerprint()
    monkeypatch.setitem(FIELD_METADATA, "deliberate_test_field", {"json_type": "string", "python_types": (str,), "required": False, "description": "test", "reference_class": "NONE"})
    assert contract_fingerprint() != before


def test_prompt_only_field_without_contract_is_drift():
    prompt_fields = set(FIELD_METADATA) | {"prompt_only_field"}
    with pytest.raises(AssertionError, match="prompt_only_field"):
        assert prompt_fields == set(FIELD_METADATA), "prompt_only_field"


def test_production_contract_artifacts_have_no_drift():
    assert contract_drift_errors() == []


def test_contract_drift_has_dedicated_failure_code(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(FIELD_METADATA, "stale_runtime_field", {"json_type": "string", "python_types": (str,), "required": True, "description": "stale", "reference_class": "NONE"})
    assert any(error.startswith("WORKER_REPORT_CONTRACT_DRIFT:") for error in contract_drift_errors())
