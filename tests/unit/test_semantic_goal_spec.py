from __future__ import annotations

from pathlib import Path

from codex_orchestrator.semantic_goals import compile_semantic_goal_spec
from codex_orchestrator.validators.schema_validator import validate_json


def _spec(prompt: str = "Make app return me and prove it."):
    return compile_semantic_goal_spec(
        master_prompt_text=prompt,
        master_prompt_path=Path("master_prompt.md"),
        master_prompt_sha256="a" * 64,
        workflow_id="WF000001",
        run_id="R0001",
    )


def test_semantic_goal_spec_schema_accepts_python_main_return_criterion():
    assert validate_json(_spec(), "semantic_goal_spec.schema.json") == []


def test_semantic_goal_spec_schema_rejects_missing_expected_value_for_return_criterion():
    spec = _spec()
    del spec["criteria"][0]["expected_value"]
    assert validate_json(spec, "semantic_goal_spec.schema.json")


def test_semantic_goal_spec_records_source_master_prompt_hash():
    assert _spec()["source_master_prompt_sha256"] == "a" * 64


def test_semantic_goal_spec_records_workflow_and_run_id():
    spec = _spec()
    assert spec["workflow_id"] == "WF000001"
    assert spec["run_id"] == "R0001"


def test_semantic_goal_spec_supports_unsupported_mode():
    spec = _spec("Make the project better.")
    assert spec["semantic_mode"] == "unsupported"
    assert spec["semantic_status"] == "UNSUPPORTED"
    assert validate_json(spec, "semantic_goal_spec.schema.json") == []


def test_semantic_goal_spec_rejects_unknown_semantic_status():
    spec = _spec()
    spec["semantic_status"] = "MAYBE"
    assert validate_json(spec, "semantic_goal_spec.schema.json")


def test_semantic_goal_spec_rejects_unknown_criterion_kind():
    spec = _spec()
    spec["criteria"][0]["kind"] = "mystery"
    assert validate_json(spec, "semantic_goal_spec.schema.json")


def test_criterion_ids_are_stable_and_ordered():
    assert [criterion["criterion_id"] for criterion in _spec()["criteria"]] == ["SGC001"]
