from __future__ import annotations

from importlib.resources import files


def _schema_exists(name: str) -> bool:
    return files("codex_orchestrator.schemas").joinpath(name).is_file()


def test_integration_state_schema_file_exists():
    assert _schema_exists("integration_state.schema.json")


def test_accepted_change_schema_file_exists():
    assert _schema_exists("accepted_change.schema.json")


def test_integration_checkpoint_schema_file_exists():
    assert _schema_exists("integration_checkpoint.schema.json")


def test_apply_results_result_schema_file_exists():
    assert _schema_exists("apply_results_result.schema.json")
