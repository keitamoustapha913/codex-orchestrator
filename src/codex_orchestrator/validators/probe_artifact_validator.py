from __future__ import annotations

import json
from pathlib import Path


def _error(code: str, path: Path, message: str) -> dict:
    return {
        "code": code,
        "path": str(path).replace("\\", "/"),
        "message": message,
    }


def _repo_relative_probe_root(probe_root: Path) -> str:
    parts = list(probe_root.parts)
    try:
        idx = parts.index(".artifacts")
    except ValueError:
        return str(probe_root).replace("\\", "/")
    return "/".join(parts[idx:])


def _load_json_file(path: Path, *, missing_code: str, invalid_code: str) -> tuple[dict | None, list[dict]]:
    if not path.exists():
        return None, [_error(missing_code, path, f"Missing required file: {path.name}")]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, [_error(invalid_code, path, f"Invalid JSON in {path.name}")]
    if not isinstance(data, dict):
        return None, [_error(invalid_code, path, f"{path.name} must contain a JSON object")]
    return data, []


def _validate_jsonl_file(path: Path, *, missing_code: str, empty_code: str, invalid_code: str) -> list[dict]:
    if not path.exists():
        return [_error(missing_code, path, f"Missing required file: {path.name}")]
    text = path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return [_error(empty_code, path, f"{path.name} must contain at least one JSON object line")]
    errors: list[dict] = []
    for index, line in enumerate(lines, start=1):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            errors.append(_error(invalid_code, path, f"Invalid JSON object line {index} in {path.name}"))
            continue
        if not isinstance(data, dict):
            errors.append(_error(invalid_code, path, f"Line {index} in {path.name} must be a JSON object"))
    return errors


def validate_probe_artifact_run(run_dir: Path, *, patchlet_id: str) -> dict:
    probe_root = run_dir.parent
    errors: list[dict] = []
    checked_files: list[str] = []

    if not probe_root.exists():
        return {
            "valid": False,
            "patchlet_id": patchlet_id,
            "probe_root": _repo_relative_probe_root(probe_root),
            "run_id": run_dir.name,
            "checked_files": [],
            "errors": [_error("MISSING_PROBE_ROOT", probe_root, f"Missing probe root for patchlet {patchlet_id}")],
        }

    if probe_root.name != patchlet_id:
        errors.append(_error("PATCHLET_ID_MISMATCH", probe_root, f"Probe root name {probe_root.name} does not match patchlet_id {patchlet_id}"))

    if not run_dir.exists():
        errors.append(_error("MISSING_RUN_DIRECTORY", run_dir, f"Missing probe run directory: {run_dir.name}"))

    probe_executable = probe_root / "probe.py"
    checked_files.append(str(probe_executable).replace("\\", "/"))
    if not probe_executable.exists():
        errors.append(_error("MISSING_PROBE_EXECUTABLE", probe_executable, "Missing probe executable probe.py"))

    row_ledger = run_dir / "row_ledger.jsonl"
    checked_files.append(str(row_ledger).replace("\\", "/"))
    errors.extend(_validate_jsonl_file(
        row_ledger,
        missing_code="MISSING_ROW_LEDGER",
        empty_code="EMPTY_ROW_LEDGER",
        invalid_code="INVALID_ROW_LEDGER_JSONL",
    ))

    trace_ledger = run_dir / "trace_ledger.jsonl"
    checked_files.append(str(trace_ledger).replace("\\", "/"))
    errors.extend(_validate_jsonl_file(
        trace_ledger,
        missing_code="MISSING_TRACE_LEDGER",
        empty_code="EMPTY_TRACE_LEDGER",
        invalid_code="INVALID_TRACE_LEDGER_JSONL",
    ))

    before_state = run_dir / "before_state.json"
    checked_files.append(str(before_state).replace("\\", "/"))
    _, before_errors = _load_json_file(
        before_state,
        missing_code="MISSING_BEFORE_STATE",
        invalid_code="INVALID_BEFORE_STATE_JSON",
    )
    errors.extend(before_errors)

    after_state = run_dir / "after_state.json"
    checked_files.append(str(after_state).replace("\\", "/"))
    _, after_errors = _load_json_file(
        after_state,
        missing_code="MISSING_AFTER_STATE",
        invalid_code="INVALID_AFTER_STATE_JSON",
    )
    errors.extend(after_errors)

    cleanup_proof = run_dir / "cleanup_proof.json"
    checked_files.append(str(cleanup_proof).replace("\\", "/"))
    cleanup_data, cleanup_errors = _load_json_file(
        cleanup_proof,
        missing_code="MISSING_CLEANUP_PROOF",
        invalid_code="INVALID_CLEANUP_PROOF_JSON",
    )
    errors.extend(cleanup_errors)
    if cleanup_data is not None and cleanup_data.get("cleanup_passed") is not True:
        errors.append(_error("CLEANUP_NOT_PASSED", cleanup_proof, "cleanup_proof.json must declare cleanup_passed=true"))

    return {
        "valid": not errors,
        "patchlet_id": patchlet_id,
        "probe_root": _repo_relative_probe_root(probe_root),
        "run_id": run_dir.name,
        "checked_files": checked_files,
        "errors": errors,
    }
