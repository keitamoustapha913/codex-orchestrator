from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json
from codex_orchestrator.validators.real_codex_smoke_runbook_validator import validate_real_codex_smoke_runbook
from codex_orchestrator.validators.schema_validator import validate_json_file


DEFAULT_OPERATOR_RUNBOOK_ROOT = Path(".operator-runs") / "real-codex-smoke"
RUNBOOK_SUFFIX = "-real-codex-smoke"


def summarize_real_codex_smoke_runbook(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    validation = validate_real_codex_smoke_runbook(run_dir)
    errors = [dict(error) for error in validation.get("errors", [])]
    warnings = [dict(warning) for warning in validation.get("warnings", [])]

    result = _read_json_object(run_dir / "result.json")
    selected_policy = _read_json_object(run_dir / "selected_policy.json")
    _validate_validation_result(run_dir, errors)

    valid = not errors
    timestamp = _timestamp_from_name(run_dir.name)
    result_exists = (run_dir / "result.json").exists()
    selected_policy_exists = (run_dir / "selected_policy.json").exists()
    diagnosis_paths_exists = (run_dir / "diagnosis_paths.json").exists()
    validation_result_exists = (run_dir / "validation_result.json").exists()

    explicit_smoke = result.get("explicit_smoke") if isinstance(result.get("explicit_smoke"), dict) else {}
    attempt_consistency = result.get("attempt_consistency") if isinstance(result.get("attempt_consistency"), dict) else {}
    policy_timeout = selected_policy.get("codex_patchlet_timeout_seconds")
    result_timeout = result.get("timeout_seconds")
    return {
        "schema_version": "1.0",
        "kind": "real_codex_smoke_runbook_summary",
        "run_dir": str(run_dir),
        "timestamp": timestamp,
        "name": run_dir.name,
        "valid": valid,
        "validation_status": "valid" if valid else "invalid",
        "outcome": _string_or_default(result.get("outcome"), "unknown"),
        "explicit_smoke": {
            "run": explicit_smoke.get("run") if isinstance(explicit_smoke.get("run"), bool) else False,
            "outcome": _string_or_default(explicit_smoke.get("outcome"), "unknown"),
        },
        "selected_policy": {
            "model": _string_or_none(selected_policy.get("codex_model")),
            "reasoning": _string_or_none(selected_policy.get("codex_reasoning")),
            "timeout_seconds": policy_timeout if isinstance(policy_timeout, int) else result_timeout if isinstance(result_timeout, int) else None,
            "progress_interval_seconds": selected_policy.get("codex_progress_interval_seconds")
            if isinstance(selected_policy.get("codex_progress_interval_seconds"), int)
            else None,
            "live_progress_enabled": selected_policy.get("live_progress_enabled")
            if isinstance(selected_policy.get("live_progress_enabled"), bool)
            else None,
        },
        "timed_out": result.get("timed_out") if isinstance(result.get("timed_out"), bool) else None,
        "diagnosis_primary_category": _string_or_none(result.get("diagnosis_primary_category")),
        "attempt_consistency_valid": attempt_consistency.get("valid") if isinstance(attempt_consistency.get("valid"), bool) else None,
        "attempt_consistency_mismatches": attempt_consistency.get("mismatches")
        if isinstance(attempt_consistency.get("mismatches"), list)
        else [],
        "paths": {
            "result": "result.json" if result_exists else None,
            "selected_policy": "selected_policy.json" if selected_policy_exists else None,
            "diagnosis_paths": "diagnosis_paths.json" if diagnosis_paths_exists else None,
            "validation_result": "validation_result.json" if validation_result_exists else None,
        },
        "errors": errors,
        "warnings": warnings,
    }


def list_real_codex_smoke_runbooks(
    root: Path | None = None,
    *,
    latest: bool = False,
    only_invalid: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    selected_root = Path(root) if root is not None else DEFAULT_OPERATOR_RUNBOOK_ROOT
    if limit is not None and limit < 1:
        raise ValueError("limit must be a positive integer")

    bundles: list[dict[str, Any]] = []
    if selected_root.exists():
        for child in selected_root.iterdir():
            if child.is_dir():
                bundles.append(summarize_real_codex_smoke_runbook(child))

    bundles.sort(key=_sort_key, reverse=True)
    if only_invalid:
        bundles = [bundle for bundle in bundles if not bundle["valid"]]
    if latest:
        bundles = bundles[:1]
    if limit is not None:
        bundles = bundles[:limit]

    valid_count = sum(1 for bundle in bundles if bundle["valid"])
    invalid_count = len(bundles) - valid_count
    return {
        "schema_version": "1.0",
        "kind": "real_codex_smoke_runbook_list",
        "root": str(selected_root),
        "count": len(bundles),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "bundles": bundles,
    }


def format_real_codex_smoke_runbook_table(result: dict[str, Any]) -> str:
    bundles = result.get("bundles", [])
    root = result.get("root", DEFAULT_OPERATOR_RUNBOOK_ROOT.as_posix())
    if not bundles:
        return "\n".join(
            [
                f"No real-Codex smoke runbooks found under {root}.",
                "Use --json for structured output.",
            ]
        )

    lines = [
        "Run timestamp              Outcome       Valid   Model         Timeout  Timed out  Diagnosis",
    ]
    for bundle in bundles:
        policy = bundle.get("selected_policy", {})
        lines.append(
            "  ".join(
                [
                    _fit(bundle.get("timestamp") or bundle.get("name") or "n/a", 24),
                    _fit(bundle.get("outcome") or "unknown", 12),
                    _fit("yes" if bundle.get("valid") else "invalid", 7),
                    _fit(policy.get("model") or "n/a", 12),
                    _fit(str(policy.get("timeout_seconds") or "n/a"), 7),
                    _fit(_timed_out_text(bundle.get("timed_out")), 9),
                    str(bundle.get("diagnosis_primary_category") or "n/a"),
                ]
            )
        )
    lines.extend(
        [
            "Use --json for full paths and validation details.",
            "Use cxor validate-real-codex-smoke-runbook --run-dir <dir> for one bundle.",
        ]
    )
    return "\n".join(lines)


def _validate_validation_result(run_dir: Path, errors: list[dict[str, str]]) -> None:
    path = run_dir / "validation_result.json"
    if not path.exists():
        errors.append(
            {
                "path": "validation_result.json",
                "schema": "real_codex_smoke_runbook_validation.schema.json",
                "message": "missing validation_result.json",
            }
        )
        return
    try:
        read_json(path)
    except Exception as exc:
        errors.append(
            {
                "path": "validation_result.json",
                "schema": "real_codex_smoke_runbook_validation.schema.json",
                "message": f"invalid JSON: {exc}",
            }
        )
        return
    for message in validate_json_file(path, "real_codex_smoke_runbook_validation.schema.json"):
        errors.append(
            {
                "path": "validation_result.json",
                "schema": "real_codex_smoke_runbook_validation.schema.json",
                "message": message,
            }
        )


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = read_json(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _timestamp_from_name(name: str) -> str | None:
    if not name.endswith(RUNBOOK_SUFFIX):
        return None
    timestamp = name[: -len(RUNBOOK_SUFFIX)]
    return timestamp or None


def _sort_key(bundle: dict[str, Any]) -> tuple[int, str]:
    timestamp = bundle.get("timestamp")
    if isinstance(timestamp, str):
        return (1, timestamp)
    return (0, str(bundle.get("name", "")))


def _string_or_default(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _timed_out_text(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "n/a"


def _fit(value: str, width: int) -> str:
    if len(value) >= width:
        return value
    return value + " " * (width - len(value))
