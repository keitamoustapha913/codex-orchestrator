from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import summarize_latest_operator_event
from codex_orchestrator.state import now_iso
from codex_orchestrator.workflow_identity import read_workflow_identity


def invocations_dir(repo_root: Path | str) -> Path:
    return Path(repo_root) / ".codex-orchestrator" / "invocations"


def create_invocation(
    repo_root: Path | str,
    *,
    command: str,
    live_progress: bool,
    progress_format: str,
) -> dict[str, Any]:
    root = Path(repo_root)
    directory = invocations_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    invocation_id = _next_invocation_id(directory)
    latest = summarize_latest_operator_event(root)
    identity = read_workflow_identity(root) or {}
    invocation = {
        "schema_version": "1.0",
        "kind": "cxor_invocation",
        "invocation_id": invocation_id,
        "created_at": now_iso(),
        "command": command,
        "workflow_id": identity.get("workflow_id"),
        "run_id": identity.get("run_id"),
        "event_cursor_at_start": latest.get("event_id") if latest else None,
        "live_progress": bool(live_progress),
        "progress_format": progress_format,
    }
    write_json(directory / f"{invocation_id}.json", invocation)
    return invocation


def _next_invocation_id(directory: Path) -> str:
    highest = 0
    for path in directory.glob("INV*.json"):
        stem = path.stem
        if stem.startswith("INV") and stem[3:].isdigit():
            highest = max(highest, int(stem[3:]))
    return f"INV{highest + 1:06d}"
