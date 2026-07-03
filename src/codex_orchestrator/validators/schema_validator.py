from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

import jsonschema

from codex_orchestrator.jsonio import read_json


def load_schema(schema_name: str) -> dict[str, Any]:
    resource = files("codex_orchestrator.schemas").joinpath(schema_name)
    return read_json(Path(str(resource))) if Path(str(resource)).exists() else __import__("json").loads(resource.read_text())


def validate_json(data: dict[str, Any], schema_name: str) -> list[str]:
    schema = load_schema(schema_name)
    validator = jsonschema.Draft202012Validator(schema)
    return [error.message for error in sorted(validator.iter_errors(data), key=lambda e: e.path)]


def iter_jsonschema_errors(data: dict[str, Any], schema_name: str):
    schema = load_schema(schema_name)
    validator = jsonschema.Draft202012Validator(schema)
    return sorted(validator.iter_errors(data), key=lambda e: list(e.path))


def validate_json_file(path: Path, schema_name: str) -> list[str]:
    return validate_json(read_json(path), schema_name)
