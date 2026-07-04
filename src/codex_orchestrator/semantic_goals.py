from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_semantic_goal_spec(repo_root: Path | str) -> dict[str, Any] | None:
    path = Path(repo_root) / ".codex-orchestrator" / "semantic_goal_spec.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def required_structured_criteria(spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    return []


def semantic_goal_summary(spec: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "semantic_goal_spec_path": None,
        "semantic_mode": "removed_no_compatibility",
        "semantic_criteria_count": 0,
        "semantic_goal_fingerprint": None,
    }
