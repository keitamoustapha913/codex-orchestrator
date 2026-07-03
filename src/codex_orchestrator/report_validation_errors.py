from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import Any


PROBE_REFS_NOT_OBJECTS = "probe_artifact_refs_not_objects"


def _json_pointer(parts: list[Any]) -> str:
    if not parts:
        return ""
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped)


def _type_name(value: Any) -> str:
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def _excerpt(value: Any, *, limit: int = 240) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def canonical_probe_ref_example(patchlet_id: str = "P0001", path: str = ".artifacts/probes/P0001/summary.json") -> dict[str, Any]:
    probe_root = "/".join(path.split("/")[:3])
    run_id = "default"
    parts = path.split("/")
    if len(parts) > 4:
        probe_root = "/".join(parts[:-1])
        run_id = parts[-2]
    kind = parts[-1].rsplit(".", 1)[0].lower().replace(" ", "_")
    return {
        "patchlet_id": patchlet_id,
        "probe_root": probe_root,
        "run_id": run_id,
        "files": [
            {
                "path": path,
                "kind": kind,
                "sha256": "<sha256>",
                "size_bytes": 123,
            }
        ],
    }


def report_validation_error_detail(
    *,
    error_id: str = "RVE000001",
    field: str,
    message: str,
    json_pointer: str | None = None,
    schema_path: str | None = None,
    validator: str | None = None,
    expected_type: str | None = None,
    actual_type: str | None = None,
    invalid_value_excerpt: str | None = None,
    normalized_signature: str = "unknown_report_validation_error",
    repair_hint: str | None = None,
    canonical_example: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "report_validation_error",
        "error_id": error_id,
        "field": field,
        "json_pointer": json_pointer or "",
        "schema_path": schema_path or "",
        "message": message,
        "validator": validator,
        "expected_type": expected_type,
        "actual_type": actual_type,
        "invalid_value_excerpt": invalid_value_excerpt,
        "normalized_signature": normalized_signature,
        "repair_hint": repair_hint
        or "Use object-shaped probe_artifact_refs entries with patchlet_id, probe_root, run_id, and optional files metadata.",
        "canonical_example": canonical_example,
    }


def detail_from_jsonschema_error(error: Any, *, error_id: str, patchlet_id: str | None = None) -> dict[str, Any]:
    path = list(getattr(error, "absolute_path", []))
    schema_path = list(getattr(error, "absolute_schema_path", []))
    field = str(path[0]) if path else "report"
    validator = getattr(error, "validator", None)
    validator_value = getattr(error, "validator_value", None)
    instance = getattr(error, "instance", None)
    expected_type = validator_value if validator == "type" and isinstance(validator_value, str) else None
    actual_type = _type_name(instance)
    signature = "unknown_report_validation_error"
    if field == "probe_artifact_refs":
        if validator == "type" and expected_type == "object" and actual_type == "string":
            signature = PROBE_REFS_NOT_OBJECTS
        elif validator == "required":
            signature = "probe_artifact_refs_missing_required_field"
        else:
            signature = "patchlet_report_schema_violation"
    elif validator:
        signature = "patchlet_report_schema_violation"
    path_text = _excerpt(instance)
    return report_validation_error_detail(
        error_id=error_id,
        field=field,
        json_pointer=_json_pointer(path),
        schema_path=_json_pointer(schema_path),
        message=getattr(error, "message", str(error)),
        validator=validator,
        expected_type=expected_type,
        actual_type=actual_type,
        invalid_value_excerpt=path_text,
        normalized_signature=signature,
        canonical_example=canonical_probe_ref_example(patchlet_id or "P0001", path_text)
        if signature == PROBE_REFS_NOT_OBJECTS and isinstance(instance, str)
        else None,
    )


def errors_artifact(
    *,
    attempt_id: str,
    patchlet_id: str,
    report_path: str | None,
    canonical_report_path: str | None,
    valid: bool,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "report_validation_errors",
        "attempt_id": attempt_id,
        "patchlet_id": patchlet_id,
        "report_path": report_path,
        "canonical_report_path": canonical_report_path,
        "valid": valid,
        "errors": errors,
    }


def assign_error_ids(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assigned: list[dict[str, Any]] = []
    for index, error in zip(count(1), errors):
        item = dict(error)
        item["error_id"] = f"RVE{index:06d}"
        assigned.append(item)
    return assigned
