from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json

from .schema_validator import validate_json, validate_json_file


REQUIRED_FILES = [
    "README.md",
    "environment.txt",
    "git_status.txt",
    "codex_version.txt",
    "selected_policy.json",
    "default_skip_stdout.txt",
    "default_skip_stderr.txt",
    "explicit_smoke_stdout.txt",
    "explicit_smoke_stderr.txt",
    "result.json",
    "diagnosis_paths.json",
]


def validate_real_codex_smoke_runbook(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    validated = {
        "required_files": False,
        "selected_policy": False,
        "result": False,
        "diagnosis_paths": False,
        "text_evidence": False,
        "copied_diagnosis_files": False,
    }

    if not run_dir.exists():
        _add_message(errors, path=str(run_dir), schema="run_dir", message="run directory does not exist")
        return _result(run_dir, validated, errors, warnings)
    if not run_dir.is_dir():
        _add_message(errors, path=str(run_dir), schema="run_dir", message="run path is not a directory")
        return _result(run_dir, validated, errors, warnings)

    missing = [name for name in REQUIRED_FILES if not (run_dir / name).exists()]
    for name in missing:
        _add_message(errors, path=name, schema="required_files", message="missing required file")
    validated["required_files"] = not missing

    selected_policy = _validate_json_artifact(
        errors,
        run_dir=run_dir,
        name="selected_policy.json",
        schema_name="real_codex_smoke_selected_policy.schema.json",
    )
    validated["selected_policy"] = selected_policy is not None

    result = _validate_json_artifact(
        errors,
        run_dir=run_dir,
        name="result.json",
        schema_name="real_codex_smoke_operator_result.schema.json",
    )
    validated["result"] = result is not None

    diagnosis_paths = _validate_json_artifact(
        errors,
        run_dir=run_dir,
        name="diagnosis_paths.json",
        schema_name="real_codex_smoke_diagnosis_paths.schema.json",
    )
    validated["diagnosis_paths"] = diagnosis_paths is not None

    _validate_text_evidence(errors, run_dir=run_dir, result=result)
    validated["text_evidence"] = not any(error["schema"] == "text_evidence" for error in errors)

    _validate_copied_diagnosis_files(errors, warnings, run_dir=run_dir, result=result, diagnosis_paths=diagnosis_paths)
    validated["copied_diagnosis_files"] = not any(error["schema"] == "copied_diagnosis_files" for error in errors)

    return _result(run_dir, validated, errors, warnings)


def _validate_json_artifact(
    errors: list[dict[str, str]],
    *,
    run_dir: Path,
    name: str,
    schema_name: str,
) -> dict[str, Any] | None:
    path = run_dir / name
    if not path.exists():
        return None
    try:
        data = read_json(path)
    except Exception as exc:
        _add_message(errors, path=name, schema=schema_name, message=f"invalid JSON: {exc}")
        return None
    for message in validate_json_file(path, schema_name):
        _add_message(errors, path=name, schema=schema_name, message=message)
    return data if not any(error["path"] == name and error["schema"] == schema_name for error in errors) else None


def _validate_text_evidence(errors: list[dict[str, str]], *, run_dir: Path, result: dict[str, Any] | None) -> None:
    _require_non_empty_text(errors, run_dir=run_dir, name="README.md")
    environment = _require_non_empty_text(errors, run_dir=run_dir, name="environment.txt")
    if environment is not None and "repo_root=" not in environment and "cwd=" not in environment:
        _add_message(errors, path="environment.txt", schema="text_evidence", message="environment.txt should mention repo_root or cwd")
    _require_non_empty_text(errors, run_dir=run_dir, name="codex_version.txt")

    default_stdout = _require_non_empty_text(errors, run_dir=run_dir, name="default_skip_stdout.txt")
    if default_stdout is not None and "skipped" not in default_stdout.lower():
        _add_message(errors, path="default_skip_stdout.txt", schema="text_evidence", message="default skip stdout should show skipped smoke")

    explicit_stdout = _require_non_empty_text(errors, run_dir=run_dir, name="explicit_smoke_stdout.txt")
    if result and result.get("outcome") == "dry_run" and explicit_stdout is not None:
        if "explicit real Codex smoke was not run" not in explicit_stdout:
            _add_message(
                errors,
                path="explicit_smoke_stdout.txt",
                schema="text_evidence",
                message="dry-run explicit stdout should state that explicit real Codex was not run",
            )


def _require_non_empty_text(errors: list[dict[str, str]], *, run_dir: Path, name: str) -> str | None:
    path = run_dir / name
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        _add_message(errors, path=name, schema="text_evidence", message="file must be non-empty")
        return text
    return text


def _validate_copied_diagnosis_files(
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
    *,
    run_dir: Path,
    result: dict[str, Any] | None,
    diagnosis_paths: dict[str, Any] | None,
) -> None:
    if diagnosis_paths is None:
        return
    for key in ["copied_diagnosis_json", "copied_diagnosis_md"]:
        value = diagnosis_paths.get(key)
        if not value:
            continue
        path = run_dir / str(value)
        if not path.exists():
            _add_message(errors, path=str(value), schema="copied_diagnosis_files", message=f"{key} references a missing file")
    if result and result.get("outcome") == "safe_failure":
        if not diagnosis_paths.get("diagnosis_json_path") and not diagnosis_paths.get("diagnosis_md_path"):
            _add_message(
                warnings,
                path="diagnosis_paths.json",
                schema="copied_diagnosis_files",
                message="safe_failure result does not reference diagnosis artifacts",
            )


def _add_message(messages: list[dict[str, str]], *, path: str, schema: str, message: str) -> None:
    messages.append({"path": path, "schema": schema, "message": message})


def _result(
    run_dir: Path,
    validated: dict[str, bool],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "real_codex_smoke_runbook_validation",
        "valid": not errors,
        "run_dir": str(run_dir),
        "validated": validated,
        "errors": errors,
        "warnings": warnings,
    }
