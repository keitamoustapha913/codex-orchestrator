from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import append_jsonl
from codex_orchestrator.state import now_iso
from codex_orchestrator.workflow_identity import read_workflow_identity


EVENT_ID_RE = re.compile(r"^OE(\d{6})$")
VALID_SEVERITIES = {"info", "warning", "error", "success", "debug"}


def operator_events_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / ".codex-orchestrator" / "operator_events.jsonl"


def append_operator_event(
    repo_root: Path | str,
    event_type: str,
    severity: str = "info",
    stage: str | None = None,
    summary: str | None = None,
    artifact_paths: list[str] | None = None,
    run_id: str | None = None,
    workflow_id: str | None = None,
    patchlet_id: str | None = None,
    attempt_id: str | None = None,
    transaction_group_id: str | None = None,
    repair_plan_id: str | None = None,
    failure_id: str | None = None,
    verifier_id: str | None = None,
    prompt_id: str | None = None,
    prompt_path: str | None = None,
    next_action: str | None = None,
    terminal_hint: str | None = None,
    details: dict[str, Any] | None = None,
    invocation_id: str | None = None,
) -> dict[str, Any]:
    if not event_type:
        raise ValueError("event_type must be non-empty")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"severity must be one of {sorted(VALID_SEVERITIES)}")
    path = operator_events_path(repo_root)
    identity = read_workflow_identity(repo_root) or {}
    event = {
        "schema_version": "1.0",
        "kind": "operator_event",
        "event_id": _next_event_id(path),
        "created_at": now_iso(),
        "event_type": event_type,
        "severity": severity,
        "stage": stage,
        "summary": summary or event_type.replace("_", " "),
        "artifact_paths": artifact_paths or [],
    }
    optional = {
        "run_id": run_id or identity.get("run_id"),
        "workflow_id": workflow_id or identity.get("workflow_id"),
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "transaction_group_id": transaction_group_id,
        "repair_plan_id": repair_plan_id,
        "failure_id": failure_id,
        "verifier_id": verifier_id,
        "prompt_id": prompt_id,
        "prompt_path": prompt_path,
        "next_action": next_action,
        "terminal_hint": terminal_hint,
        "details": details,
        "invocation_id": invocation_id or os.environ.get("CXOR_INVOCATION_ID"),
    }
    event.update({key: value for key, value in optional.items() if value is not None})
    append_jsonl(path, event)
    return event


def read_operator_events(
    repo_root: Path | str,
    since: str | None = None,
    limit: int | None = None,
    attempt_id: str | None = None,
    patchlet_id: str | None = None,
    event_type: str | None = None,
    workflow_id: str | None = None,
    invocation_id: str | None = None,
) -> list[dict[str, Any]]:
    path = operator_events_path(repo_root)
    events = _read_valid_events(path)
    if since:
        events = [event for event in events if _event_number(event.get("event_id")) > _event_number(since)]
    if attempt_id:
        events = [event for event in events if event.get("attempt_id") == attempt_id]
    if patchlet_id:
        events = [event for event in events if event.get("patchlet_id") == patchlet_id]
    if event_type:
        events = [event for event in events if event.get("event_type") == event_type]
    if workflow_id:
        events = [event for event in events if event.get("workflow_id") == workflow_id]
    if invocation_id:
        events = [event for event in events if event.get("invocation_id") == invocation_id]
    if limit is not None:
        events = events[-limit:] if limit >= 0 else []
    return events


def summarize_latest_operator_event(repo_root: Path | str) -> dict[str, Any] | None:
    events = read_operator_events(repo_root, limit=1)
    return events[-1] if events else None


def _next_event_id(path: Path) -> str:
    events = _read_valid_events(path)
    last = max((_event_number(event.get("event_id")) for event in events), default=0)
    return f"OE{last + 1:06d}"


def _read_valid_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                continue
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _event_number(event_id: object) -> int:
    if not isinstance(event_id, str):
        return 0
    match = EVENT_ID_RE.match(event_id)
    return int(match.group(1)) if match else 0
