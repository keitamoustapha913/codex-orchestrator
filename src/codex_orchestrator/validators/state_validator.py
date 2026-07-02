from __future__ import annotations

from pathlib import Path

from .schema_validator import validate_json_file


def validate_state_file(path: Path) -> list[str]:
    return validate_json_file(path, "state.schema.json")
