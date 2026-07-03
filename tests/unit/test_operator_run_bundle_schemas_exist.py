from __future__ import annotations

from importlib.resources import files


def _schema_exists(name: str) -> bool:
    return files("codex_orchestrator.schemas").joinpath(name).is_file()


def test_real_codex_smoke_selected_policy_schema_file_exists():
    assert _schema_exists("real_codex_smoke_selected_policy.schema.json")


def test_real_codex_smoke_operator_result_schema_file_exists():
    assert _schema_exists("real_codex_smoke_operator_result.schema.json")


def test_real_codex_smoke_diagnosis_paths_schema_file_exists():
    assert _schema_exists("real_codex_smoke_diagnosis_paths.schema.json")


def test_real_codex_smoke_runbook_validation_schema_file_exists():
    assert _schema_exists("real_codex_smoke_runbook_validation.schema.json")
