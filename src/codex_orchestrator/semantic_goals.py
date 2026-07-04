from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SAFE_UNQUOTED_RE = re.compile(r"^[A-Za-z0-9_-]+$")
PATTERNS = [
    re.compile(r"^\s*make\s+app\s+return\s+(?P<value>.+?)\s+and\s+prove\s+it\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*make\s+app\.py\s+return\s+(?P<value>.+?)\s+and\s+prove\s+it\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*make\s+app\s+main\s+return\s+(?P<value>.+?)\s+and\s+prove\s+it\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*make\s+app\.main(?:\(\))?\s+return\s+(?P<value>.+?)\s+and\s+prove\s+it\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*make\s+the\s+app\s+pipeline\s+return\s+(?P<value>.+?)\s+through\s+the\s+entrypoint\s+and\s+prove\s+it\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*make\s+app\s+process\s+the\s+input\s+through\s+validation,\s+transformation,\s+and\s+formatting\s+so\s+main\s+returns\s+(?P<value>.+?)\s+and\s+prove\s+it\.?\s*$", re.IGNORECASE),
]


def parse_builtin_python_main_return_goal(master_prompt_text: str) -> list[dict[str, Any]]:
    text = _first_meaningful_line(master_prompt_text)
    for pattern in PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        value = _parse_expected_value(match.group("value"))
        if value is None:
            return []
        return [
            {
                "criterion_id": "SGC001",
                "kind": "python_module_function_returns",
                "title": "app.main returns expected string",
                "target_file": "app.py",
                "module_name": "app",
                "function_name": "main",
                "expected_value": value,
                "expected_value_type": "string",
                "comparison": "equals",
                "required": True,
                "source": {
                    "parser": "builtin_app_main_return_prompt_v1",
                    "matched_text": text,
                },
                "probe": {
                    "command_template": f"PYTHONDONTWRITEBYTECODE=1 python -B -c 'import app; assert app.main() == {json.dumps(value)}'",
                    "execution_context": "integration_root",
                },
            }
        ]
    return []


def compile_semantic_goal_spec(
    *,
    master_prompt_text: str,
    master_prompt_path: Path,
    master_prompt_sha256: str,
    workflow_id: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    criteria = parse_builtin_python_main_return_goal(master_prompt_text)
    excerpt = _first_meaningful_line(master_prompt_text)
    if criteria:
        mode = "structured"
        status = "PENDING"
        unsupported_reasons: list[str] = []
    else:
        mode = "unsupported"
        status = "UNSUPPORTED"
        unsupported_reasons = ["No built-in semantic goal parser matched the master prompt."]
    spec = {
        "schema_version": "1.0",
        "kind": "semantic_goal_spec",
        "workflow_id": workflow_id,
        "run_id": run_id,
        "source_master_prompt_path": str(master_prompt_path),
        "source_master_prompt_sha256": master_prompt_sha256,
        "source_master_prompt_text_excerpt": excerpt,
        "semantic_mode": mode,
        "semantic_status": status,
        "criteria": criteria,
        "unsupported_reasons": unsupported_reasons,
    }
    spec["semantic_goal_fingerprint"] = semantic_goal_fingerprint(spec)
    return spec


def semantic_goal_fingerprint(spec: dict[str, Any]) -> str:
    payload = {
        "schema_version": spec.get("schema_version"),
        "semantic_mode": spec.get("semantic_mode"),
        "criteria": spec.get("criteria", []),
        "unsupported_reasons": spec.get("unsupported_reasons", []),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def semantic_goal_summary(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "semantic_goal_spec_path": ".codex-orchestrator/semantic_goal_spec.json",
        "semantic_mode": spec.get("semantic_mode"),
        "semantic_criteria_count": len(spec.get("criteria", [])),
        "semantic_goal_fingerprint": spec.get("semantic_goal_fingerprint") or semantic_goal_fingerprint(spec),
    }


def load_semantic_goal_spec(repo_root: Path | str) -> dict[str, Any] | None:
    path = Path(repo_root) / ".codex-orchestrator" / "semantic_goal_spec.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def required_structured_criteria(spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not spec or spec.get("semantic_mode") != "structured":
        return []
    return [criterion for criterion in spec.get("criteria", []) if criterion.get("required") is True]


def _first_meaningful_line(text: str) -> str:
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped:
            return stripped
    return ""


def _parse_expected_value(raw: str) -> str | None:
    value = raw.strip()
    if value.endswith("."):
        value = value[:-1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        inner = value[1:-1]
        if any(token in inner for token in ["\n", "\r", "`", "$(", ";"]):
            return None
        return inner
    lowered = value.lower()
    if any(token in lowered for token in ["os.environ", "secret", "current date", "network", "(", ")", "[", "]", "{", "}", ";", "`", "$"]):
        return None
    if not SAFE_UNQUOTED_RE.match(value):
        return None
    return value
