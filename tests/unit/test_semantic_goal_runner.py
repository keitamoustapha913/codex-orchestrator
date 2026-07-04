from __future__ import annotations

from pathlib import Path

from codex_orchestrator.semantic_goal_runner import run_semantic_goal_checks
from codex_orchestrator.semantic_goals import compile_semantic_goal_spec
from codex_orchestrator.validators.schema_validator import validate_json


def _spec(expected: str = "me"):
    return compile_semantic_goal_spec(
        master_prompt_text=f"Make app return {expected} and prove it.",
        master_prompt_path=Path("master_prompt.md"),
        master_prompt_sha256="c" * 64,
        workflow_id="WF000001",
        run_id="R0001",
    )


def _write_app(root: Path, value: str):
    (root / "app.py").write_text(f"def main():\n    return {value!r}\n", encoding="utf-8")


def test_runner_passes_when_app_main_returns_expected_value(tmp_path: Path):
    _write_app(tmp_path, "me")
    result = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert result["overall_status"] == "PASSED"


def test_runner_fails_when_app_main_returns_wrong_value(tmp_path: Path):
    _write_app(tmp_path, "ok")
    result = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert result["criteria"][0]["actual_value"] == "ok"
    assert result["overall_status"] == "FAILED"


def test_runner_records_expected_and_actual_values(tmp_path: Path):
    _write_app(tmp_path, "ok")
    row = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id=None, attempt_id=None)["criteria"][0]
    assert row["expected_value"] == "me"
    assert row["actual_value"] == "ok"


def test_runner_writes_stdout_and_stderr_artifacts(tmp_path: Path):
    _write_app(tmp_path, "me")
    row = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id=None, attempt_id=None)["criteria"][0]
    assert (tmp_path / row["stdout_path"]).exists()
    assert (tmp_path / row["stderr_path"]).exists()


def test_runner_uses_python_dash_b_and_dont_write_bytecode(tmp_path: Path):
    _write_app(tmp_path, "me")
    row = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id=None, attempt_id=None)["criteria"][0]
    assert "PYTHONDONTWRITEBYTECODE=1 python -B" in row["command"]


def test_runner_does_not_create_pycache(tmp_path: Path):
    _write_app(tmp_path, "me")
    run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id=None, attempt_id=None)
    assert not list(tmp_path.rglob("__pycache__"))


def test_runner_handles_missing_app_file_as_failed(tmp_path: Path):
    result = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id=None, attempt_id=None)
    assert result["overall_status"] == "FAILED"


def test_runner_handles_missing_main_function_as_failed(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    result = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id=None, attempt_id=None)
    assert result["overall_status"] == "FAILED"


def test_runner_handles_exception_from_main_as_failed(tmp_path: Path):
    (tmp_path / "app.py").write_text("def main():\n    raise RuntimeError('boom')\n", encoding="utf-8")
    result = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id=None, attempt_id=None)
    assert result["overall_status"] == "FAILED"


def test_runner_marks_unsupported_goal_as_unsupported(tmp_path: Path):
    spec = compile_semantic_goal_spec(master_prompt_text="Make it better.", master_prompt_path=Path("master_prompt.md"), master_prompt_sha256="d" * 64, workflow_id=None, run_id=None)
    result = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=spec, patchlet_id=None, attempt_id=None)
    assert result["overall_status"] == "UNSUPPORTED"


def test_runner_result_schema_validates(tmp_path: Path):
    _write_app(tmp_path, "me")
    result = run_semantic_goal_checks(repo_root=tmp_path, execution_root=tmp_path, integration_ref=None, semantic_goal_spec=_spec("me"), patchlet_id=None, attempt_id=None)
    assert validate_json(result, "semantic_goal_check_result.schema.json") == []
