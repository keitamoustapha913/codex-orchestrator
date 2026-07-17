from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = [
    "src/codex_orchestrator/patch_promotion.py",
    "src/codex_orchestrator/worker_evidence.py",
    "src/codex_orchestrator/report_contract.py",
    "src/codex_orchestrator/report_ingestion.py",
    "src/codex_orchestrator/report_reorganization.py",
    "src/codex_orchestrator/semantic_result_normalization.py",
    "src/codex_orchestrator/worker_capsule.py",
    "src/codex_orchestrator/stages/run_patchlet.py",
    "src/codex_orchestrator/stages/status.py",
]
REPORT_BOUNDARY_FILES = [
    "src/codex_orchestrator/report_contract.py",
    "src/codex_orchestrator/report_ingestion.py",
    "src/codex_orchestrator/real_codex_smoke.py",
    "src/codex_orchestrator/stages/compile_patchlets.py",
    "src/codex_orchestrator/stages/regenerate_patchlets.py",
    "src/codex_orchestrator/validators/report_validator.py",
    "src/codex_orchestrator/workers/mock.py",
    "src/codex_orchestrator/worker_capsule.py",
]
CURRENT_DOCS = [
    "README.md",
    "IMPLEMENTATION_STATUS.md",
    "docs/real_codex_smoke.md",
    "docs/cli.md",
    "docs/autonomous_loop.md",
    "docs/worktrees.md",
    "docs/report_contract.md",
    "docs/runbooks/real_codex_smoke_runbook.md",
]


def _source_text() -> str:
    return "\n".join((ROOT / relative).read_text(encoding="utf-8") for relative in SOURCE_FILES)


def _text(relative_paths: list[str]) -> str:
    return "\n".join((ROOT / relative).read_text(encoding="utf-8") for relative in relative_paths)


def test_worker_pipeline_has_no_legacy_evidence_classifier():
    text = _source_text()
    assert "LEGACY_" + "APPROVED_PROBE_EVIDENCE" not in text
    assert "classify_legacy_" + "worker_evidence" not in text
    assert "approved_legacy_" + "run_ids" not in text


def test_worker_pipeline_has_no_v1_report_alias_adapter():
    text = _source_text()
    assert "DOCUMENTED_LEGACY_" + "ALIASES" not in text
    assert "adapt_documented_" + "legacy_fields" not in text
    assert "WorkerPatchletReportV1-" + "to-V2-aliases" not in text


def test_worker_pipeline_has_no_semantic_goal_alias_table():
    assert "GOAL_ITEM_" + "ALIASES" not in _source_text()


def test_worker_pipeline_has_no_legacy_work_slice_fallback():
    assert "legacy-" + "invariant-slice" not in _source_text()


def test_worker_pipeline_has_no_direct_root_scratch_quarantine():
    text = _source_text()
    assert "_quarantine_execution_root_scratch_files" not in text
    assert "WORKER_SCRATCH_PATH_" + "CONTRACT_VIOLATION" not in text


def test_worker_classification_schema_has_no_old_classes():
    schema = json.loads(
        (ROOT / "src/codex_orchestrator/schemas/worker_change_classification_ledger.schema.json").read_text(
            encoding="utf-8"
        )
    )
    text = json.dumps(schema, sort_keys=True)
    old = {
        "APPROVED_PROBE_EVIDENCE",
        "BOUNDED_SCRATCH_WARNING",
        "FORBIDDEN_TRACKED_CHANGE",
        "PROTECTED_FILE_CHANGE",
        "UNKNOWN_WORKER_OUTPUT",
        "UNSAFE_PATH_OBJECT",
    }
    assert not any(value in text for value in old)


def test_worker_hygiene_schema_has_no_legacy_fields():
    schema = json.loads(
        (ROOT / "src/codex_orchestrator/schemas/worker_sandbox_hygiene_result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    text = json.dumps(schema, sort_keys=True)
    for field in (
        "warning_entries",
        "rejected_entries",
        "legacy_evidence_file_count",
        "unknown_worker_output_count",
        "protected_change_count",
    ):
        assert field not in text


def test_static_real_codex_patchlet_contract_file_is_absent():
    assert not (
        ROOT
        / "src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md"
    ).exists()


def test_compile_patchlets_has_no_external_contract_loader():
    text = (ROOT / "src/codex_orchestrator/stages/compile_patchlets.py").read_text(encoding="utf-8")
    assert "CXOR_REAL_CODEX_CONTRACT_PATH" not in text
    assert "_real_codex_contract_text" not in text


def test_regenerate_patchlets_has_no_external_contract_loader():
    text = (ROOT / "src/codex_orchestrator/stages/regenerate_patchlets.py").read_text(encoding="utf-8")
    assert "CXOR_REAL_CODEX_CONTRACT_PATH" not in text
    assert "_real_codex_contract_text" not in text


def test_real_codex_smoke_has_no_contract_injection_environment():
    text = (ROOT / "src/codex_orchestrator/real_codex_smoke.py").read_text(encoding="utf-8")
    assert "CXOR_REAL_CODEX_CONTRACT_PATH" not in text
    assert "inject_contract" not in text


def test_v1_patchlet_report_schema_is_absent():
    assert not (
        ROOT / "src/codex_orchestrator/schemas" / ("patchlet_" + "report.schema.json")
    ).exists()


def test_validator_has_no_v1_schema_fallback():
    text = (
        ROOT / "src/codex_orchestrator/validators/report_validator.py"
    ).read_text(encoding="utf-8")
    assert "patchlet_" + "report.schema.json" not in text
    assert 'report.get("schema_version") == "2.0"' not in text


def test_tests_do_not_validate_against_v1_report_schema():
    forbidden = "patchlet_" + "report.schema.json"
    matches = []
    for path in (ROOT / "tests").rglob("*.py"):
        if path == Path(__file__).resolve():
            continue
        if forbidden in path.read_text(encoding="utf-8"):
            matches.append(path.relative_to(ROOT).as_posix())
    assert matches == []


def test_worker_report_pipeline_has_no_v1_schema_file():
    schema = ROOT / "src/codex_orchestrator/schemas" / ("patchlet_" + "report.schema.json")
    assert not schema.exists()


def test_worker_report_pipeline_has_no_v1_validator_fallback():
    text = (ROOT / "src/codex_orchestrator/validators/report_validator.py").read_text(
        encoding="utf-8"
    )
    assert "patchlet_" + "report.schema.json" not in text
    assert 'iter_jsonschema_errors(report, "worker_patchlet_report_v2.schema.json")' in text


def test_worker_report_pipeline_has_no_acceptance_result_normalizer():
    text = _text(REPORT_BOUNDARY_FILES)
    assert "normalize_" + "acceptance_criteria_result" not in text
    assert "_normalize_report_" + "acceptance_criteria" not in text
    assert "ALLOWED_ACCEPTANCE_" + "STATUS_FORMS" not in text


def test_worker_report_pipeline_has_no_acceptance_result_status_event():
    text = _text(REPORT_BOUNDARY_FILES)
    assert "report_ingestion_" + "normalized_status" not in text
    assert "acceptance_criteria_result_" + "status_prefix" not in text


def test_worker_report_pipeline_has_no_static_real_codex_contract():
    path = ROOT / "src/codex_orchestrator/prompt_templates" / (
        "real_codex_" + "patchlet_contract.md"
    )
    assert not path.exists()


def test_worker_report_pipeline_has_no_external_contract_environment():
    assert "CXOR_REAL_CODEX_" + "CONTRACT_PATH" not in _text(REPORT_BOUNDARY_FILES)


def test_mock_worker_emits_task_handoff_not_formal_report_identity():
    text = (ROOT / "src/codex_orchestrator/workers/mock.py").read_text(encoding="utf-8")
    assert '"schema_version": "1.0"' in text
    assert '"kind": "task_worker_completion_handoff"' in text
    assert '"kind": "worker_patchlet_report"' not in text
    assert '"kind": "' + 'patchlet_report"' not in text


def test_mock_worker_has_no_acceptance_result_field():
    text = (ROOT / "src/codex_orchestrator/workers/mock.py").read_text(encoding="utf-8")
    assert "acceptance_criteria_" + "result" not in text


def test_worker_input_contract_has_no_derived_semantic_claims():
    from codex_orchestrator.report_contract import FIELD_METADATA, generated_v2_schema

    assert "worker_semantic_claims" not in FIELD_METADATA
    assert "worker_semantic_claims" not in generated_v2_schema()["properties"]


def test_worker_templates_have_no_derived_semantic_claims():
    template_files = [
        "src/codex_orchestrator/prompt_templates/worker_patchlet_report_v2.md",
        "src/codex_orchestrator/prompt_templates/report_reorganization_worker_instructions.md",
        "src/codex_orchestrator/worker_capsule.py",
    ]
    assert "worker_semantic_" + "claims" not in _text(template_files)


def test_worker_tests_have_no_v1_schema_validation():
    forbidden = "patchlet_" + "report.schema.json"
    offenders = []
    for path in (ROOT / "tests").rglob("*.py"):
        if path == Path(__file__).resolve():
            continue
        if forbidden in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_current_docs_have_no_static_contract_reference():
    text = _text(CURRENT_DOCS)
    assert "real_codex_" + "patchlet_contract.md" not in text
    assert "CXOR_REAL_CODEX_" + "CONTRACT_PATH" not in text
