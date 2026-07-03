from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json
from codex_orchestrator.operator_events import summarize_latest_operator_event
from codex_orchestrator.prompt_index import read_prompt_index


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = read_json(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _latest_run(manifest: dict[str, Any]) -> dict[str, Any] | None:
    runs = manifest.get("runs", [])
    if not isinstance(runs, list) or not runs:
        return None
    return runs[-1] if isinstance(runs[-1], dict) else None


def _path_age_seconds(path: Path, now: float) -> float | None:
    if not path.exists():
        return None
    return max(0.0, now - path.stat().st_mtime)


def _repo_path(repo_root: Path, rel_or_abs: str | None) -> Path | None:
    if not rel_or_abs:
        return None
    path = Path(rel_or_abs)
    return path if path.is_absolute() else repo_root / path


def _latest_prompt_for_attempt(repo_root: Path, attempt_id: str | None) -> str | None:
    if not attempt_id:
        return None
    prompts = read_prompt_index(repo_root).get("prompts", [])
    for prompt in reversed(prompts):
        if prompt.get("attempt_id") == attempt_id:
            return prompt.get("path")
    return None


def classify_activity(
    repo_root: Path | str,
    *,
    recent_progress_seconds: float = 120.0,
    likely_stalled_seconds: float = 600.0,
    now: float | None = None,
) -> dict[str, Any]:
    root = Path(repo_root)
    workflow_dir = root / ".codex-orchestrator"
    if not workflow_dir.exists():
        return {
            "classification": "unknown",
            "last_progress_path": None,
            "last_progress_age_seconds": None,
            "next_action": "No workflow artifacts found.",
        }
    now_value = time.time() if now is None else now
    state = _safe_json(workflow_dir / "state.json")
    manifest = _safe_json(workflow_dir / "run_manifest.json")
    latest_run = _latest_run(manifest)
    final_verification = _safe_json(workflow_dir / "final_verification.json")
    loop_governor = _safe_json(workflow_dir / "loop_governor.json")
    last_event = summarize_latest_operator_event(root)

    if state.get("stage") == "DONE" or final_verification.get("done") is True:
        return {
            "classification": "done",
            "last_event": last_event,
            "last_progress_path": None,
            "last_progress_age_seconds": None,
            "next_action": "Workflow reached DONE.",
        }
    if loop_governor.get("blocked") is True:
        return {
            "classification": "failed",
            "current_attempt_id": latest_run.get("attempt_id") if latest_run else None,
            "active_prompt_path": _latest_prompt_for_attempt(root, latest_run.get("attempt_id") if latest_run else None),
            "last_event": last_event,
            "last_progress_path": None,
            "last_progress_age_seconds": None,
            "next_action": loop_governor.get("blocked_reason") or "Loop governor blocked workflow.",
        }

    attempt_id = latest_run.get("attempt_id") if latest_run else None
    paths = latest_run.get("paths", {}) if latest_run else {}
    progress_path = _repo_path(root, paths.get("progress_jsonl") or latest_run.get("progress_path") if latest_run else None)
    output_path = _repo_path(root, paths.get("output_jsonl") if paths else None)
    stdout_path = _repo_path(root, paths.get("stdout") if paths else None)
    stderr_path = _repo_path(root, paths.get("stderr") if paths else None)
    candidate_paths = [path for path in [progress_path, output_path, stdout_path, stderr_path] if path is not None]
    ages = [(path, _path_age_seconds(path, now_value)) for path in candidate_paths]
    ages = [(path, age) for path, age in ages if age is not None]
    latest_path, latest_age = min(ages, key=lambda item: item[1]) if ages else (None, None)
    progress_age = _path_age_seconds(progress_path, now_value) if progress_path is not None else None
    reported_progress_path = progress_path if progress_age is not None else latest_path
    reported_progress_age = progress_age if progress_age is not None else latest_age

    if latest_run and latest_run.get("lifecycle_status") == "ATTEMPT_FAILED_WITH_EVIDENCE":
        classification = "failed"
        next_action = "Inspect failure evidence."
    elif progress_age is not None and progress_age <= recent_progress_seconds:
        classification = "active"
        next_action = "Waiting for worker or orchestrator progress."
    elif latest_age is not None and latest_age <= recent_progress_seconds:
        classification = "silent_but_active"
        next_action = "Durable worker artifacts are changing."
    elif latest_age is not None and latest_age >= likely_stalled_seconds:
        classification = "likely_stalled"
        next_action = "Inspect current attempt artifacts and worker process state."
    else:
        classification = "unknown"
        next_action = "Insufficient activity evidence."

    return {
        "classification": classification,
        "current_attempt_id": attempt_id,
        "active_prompt_path": _latest_prompt_for_attempt(root, attempt_id),
        "last_progress_path": str(reported_progress_path.relative_to(root)) if reported_progress_path and reported_progress_path.is_relative_to(root) else str(reported_progress_path) if reported_progress_path else None,
        "last_progress_age_seconds": int(reported_progress_age) if reported_progress_age is not None else None,
        "last_event": last_event,
        "next_action": next_action,
    }
