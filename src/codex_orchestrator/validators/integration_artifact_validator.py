from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json
from codex_orchestrator.paths import build_paths, relative_to_repo

from .schema_validator import validate_json, validate_json_file


def validate_integration_artifacts(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    paths = build_paths(repo_root)
    errors: list[dict[str, Any]] = []
    validated = {
        "integration_state": False,
        "accepted_changes": False,
        "checkpoints": False,
        "apply_results": False,
        "final_diff": False,
    }

    state = _validate_json_file(
        errors,
        repo_root=repo_root,
        path=paths.integration_state,
        schema_name="integration_state.schema.json",
    )
    validated["integration_state"] = state is not None

    if paths.accepted_changes.exists():
        _validate_accepted_changes(errors, repo_root=repo_root, path=paths.accepted_changes)
        validated["accepted_changes"] = not any(
            error.get("path") == relative_to_repo(repo_root, paths.accepted_changes) for error in errors
        )
    else:
        _add_error(
            errors,
            repo_root=repo_root,
            path=paths.accepted_changes,
            schema_name="accepted_change.schema.json",
            message="missing accepted_changes.jsonl",
        )

    if paths.integration_checkpoints_dir.exists():
        for checkpoint in sorted(paths.integration_checkpoints_dir.glob("*.json")):
            if checkpoint.name.endswith("_cleanliness.json"):
                continue
            checkpoint_data = _validate_json_file(
                errors,
                repo_root=repo_root,
                path=checkpoint,
                schema_name="integration_checkpoint.schema.json",
            )
            if checkpoint_data is not None:
                _validate_checkpoint_cleanliness_sidecar(errors, repo_root=repo_root, checkpoint=checkpoint_data)
    validated["checkpoints"] = not any(
        error.get("schema") in {
            "integration_checkpoint.schema.json",
            "target_cleanliness_report.schema.json",
            "target_hygiene_gate_result.schema.json",
            "checkpoint_cleanliness_sidecar",
        }
        for error in errors
    )

    apply_results_dir = paths.integration_dir / "apply_results"
    if apply_results_dir.exists():
        for result_path in sorted(apply_results_dir.glob("*_result.json")):
            _validate_json_file(
                errors,
                repo_root=repo_root,
                path=result_path,
                schema_name="apply_results_result.schema.json",
            )
    validated["apply_results"] = not any(error.get("schema") == "apply_results_result.schema.json" for error in errors)

    if _final_diff_required(paths, state):
        final_diff_path = repo_root / str(state.get("final_diff_path", "")) if state else paths.final_diff_path
        if final_diff_path.exists():
            validated["final_diff"] = True
        else:
            _add_error(
                errors,
                repo_root=repo_root,
                path=final_diff_path,
                schema_name="final_diff.patch",
                message="missing final_diff.patch",
            )
    else:
        validated["final_diff"] = True

    return {
        "schema_version": "1.0",
        "kind": "integration_artifact_validation",
        "valid": not errors,
        "validated": validated,
        "errors": errors,
    }


def _validate_json_file(
    errors: list[dict[str, Any]],
    *,
    repo_root: Path,
    path: Path,
    schema_name: str,
) -> dict[str, Any] | None:
    if not path.exists():
        _add_error(errors, repo_root=repo_root, path=path, schema_name=schema_name, message=f"missing {path.name}")
        return None
    try:
        data = read_json(path)
    except Exception as exc:
        _add_error(errors, repo_root=repo_root, path=path, schema_name=schema_name, message=f"invalid JSON: {exc}")
        return None
    schema_errors = validate_json_file(path, schema_name)
    for message in schema_errors:
        _add_error(errors, repo_root=repo_root, path=path, schema_name=schema_name, message=message)
    return data if not schema_errors else None


def _validate_accepted_changes(errors: list[dict[str, Any]], *, repo_root: Path, path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _add_error(
            errors,
            repo_root=repo_root,
            path=path,
            schema_name="accepted_change.schema.json",
            message=f"cannot read accepted_changes.jsonl: {exc}",
        )
        return

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            _add_error(
                errors,
                repo_root=repo_root,
                path=path,
                schema_name="accepted_change.schema.json",
                message=f"line {line_number}: invalid JSON: {exc.msg}",
                line=line_number,
            )
            continue
        if not isinstance(data, dict):
            _add_error(
                errors,
                repo_root=repo_root,
                path=path,
                schema_name="accepted_change.schema.json",
                message=f"line {line_number}: expected JSON object",
                line=line_number,
            )
            continue
        for message in validate_json(data, "accepted_change.schema.json"):
            _add_error(
                errors,
                repo_root=repo_root,
                path=path,
                schema_name="accepted_change.schema.json",
                message=f"line {line_number}: {message}",
                line=line_number,
            )


def _final_diff_required(paths, state: dict[str, Any] | None) -> bool:
    if state is None:
        return False
    apply_results_dir = paths.integration_dir / "apply_results"
    return paths.final_verification_json.exists() or any(apply_results_dir.glob("*_result.json")) if apply_results_dir.exists() else paths.final_verification_json.exists()


def _validate_checkpoint_cleanliness_sidecar(
    errors: list[dict[str, Any]],
    *,
    repo_root: Path,
    checkpoint: dict[str, Any],
) -> None:
    summary = checkpoint.get("target_cleanliness")
    if not isinstance(summary, dict):
        return
    report_path_value = summary.get("report_path")
    if not isinstance(report_path_value, str) or not report_path_value:
        _add_error(
            errors,
            repo_root=repo_root,
            path=repo_root / ".codex-orchestrator" / "integration" / "checkpoints",
            schema_name="checkpoint_cleanliness_sidecar",
            message="checkpoint target_cleanliness missing report_path",
        )
        return
    sidecar_path = repo_root / report_path_value
    sidecar = _validate_json_file(
        errors,
        repo_root=repo_root,
        path=sidecar_path,
        schema_name="target_cleanliness_report.schema.json",
    )
    if sidecar is None:
        if not sidecar_path.exists():
            _add_error(
                errors,
                repo_root=repo_root,
                path=sidecar_path,
                schema_name="checkpoint_cleanliness_sidecar",
                message="missing cleanliness sidecar",
            )
        return
    if sidecar.get("patchlet_id") != checkpoint.get("patchlet_id"):
        _add_error(
            errors,
            repo_root=repo_root,
            path=sidecar_path,
            schema_name="checkpoint_cleanliness_sidecar",
            message="cleanliness sidecar patchlet_id mismatch",
        )
    if sidecar.get("attempt_id") != checkpoint.get("attempt_id"):
        _add_error(
            errors,
            repo_root=repo_root,
            path=sidecar_path,
            schema_name="checkpoint_cleanliness_sidecar",
            message="cleanliness sidecar attempt_id mismatch",
        )
    if sidecar.get("target_working_tree_clean_after_checkpoint") is not checkpoint.get("target_working_tree_clean_after_checkpoint"):
        _add_error(
            errors,
            repo_root=repo_root,
            path=sidecar_path,
            schema_name="checkpoint_cleanliness_sidecar",
            message="cleanliness sidecar target_working_tree_clean_after_checkpoint mismatch",
        )
    hygiene_path_value = sidecar.get("hygiene_gate_result_path")
    if isinstance(hygiene_path_value, str) and hygiene_path_value:
        _validate_json_file(
            errors,
            repo_root=repo_root,
            path=repo_root / hygiene_path_value,
            schema_name="target_hygiene_gate_result.schema.json",
        )


def _add_error(
    errors: list[dict[str, Any]],
    *,
    repo_root: Path,
    path: Path,
    schema_name: str,
    message: str,
    line: int | None = None,
) -> None:
    error: dict[str, Any] = {
        "path": relative_to_repo(repo_root, path),
        "schema": schema_name,
        "message": message,
    }
    if line is not None:
        error["line"] = line
    errors.append(error)
