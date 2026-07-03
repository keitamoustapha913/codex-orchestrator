from __future__ import annotations

import json
import os
import time
from pathlib import Path

from codex_orchestrator.activity_classifier import classify_activity


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _workflow(root: Path, *, progress: bool = True):
    wf = root / ".codex-orchestrator"
    run_dir = wf / "runs" / "P0001_attempt1"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        wf / "state.json",
        {
            "schema_version": "1.0",
            "kind": "workflow_state",
            "workflow_id": "W1",
            "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
            "current_patchlet_id": "P0001",
        },
    )
    _write_json(
        wf / "run_manifest.json",
        {
            "schema_version": "1.0",
            "kind": "run_manifest",
            "runs": [
                {
                    "attempt_id": "P0001_attempt1",
                    "patchlet_id": "P0001",
                    "lifecycle_status": "ATTEMPT_STARTED",
                    "paths": {
                        "run_dir": ".codex-orchestrator/runs/P0001_attempt1",
                        "progress_jsonl": ".codex-orchestrator/runs/P0001_attempt1/progress.jsonl",
                        "output_jsonl": ".codex-orchestrator/runs/P0001_attempt1/output.jsonl",
                        "stdout": ".codex-orchestrator/runs/P0001_attempt1/stdout.txt",
                        "stderr": ".codex-orchestrator/runs/P0001_attempt1/stderr.txt",
                    },
                }
            ],
        },
    )
    _write_json(
        wf / "prompt_index.json",
        {
            "schema_version": "1.0",
            "kind": "prompt_index",
            "prompts": [
                {
                    "prompt_id": "PR000001",
                    "kind": "patchlet_worker_prompt",
                    "attempt_id": "P0001_attempt1",
                    "path": ".codex-orchestrator/runs/P0001_attempt1/codex_task_prompt.md",
                }
            ],
        },
    )
    if progress:
        (run_dir / "progress.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "output.jsonl").write_text("{}\n", encoding="utf-8")
    return wf, run_dir


def test_activity_classifier_returns_unknown_for_missing_workflow(tmp_path: Path):
    result = classify_activity(tmp_path)

    assert result["classification"] == "unknown"


def test_activity_classifier_returns_done_for_done_state(tmp_path: Path):
    wf, _ = _workflow(tmp_path)
    state = json.loads((wf / "state.json").read_text(encoding="utf-8"))
    state["stage"] = "DONE"
    _write_json(wf / "state.json", state)

    result = classify_activity(tmp_path)

    assert result["classification"] == "done"


def test_activity_classifier_returns_active_for_recent_progress_file(tmp_path: Path):
    _workflow(tmp_path)

    result = classify_activity(tmp_path, recent_progress_seconds=120)

    assert result["classification"] == "active"


def test_activity_classifier_returns_silent_but_active_for_recent_worker_file_without_terminal(tmp_path: Path):
    _, run_dir = _workflow(tmp_path)
    (run_dir / "progress.jsonl").unlink()

    result = classify_activity(tmp_path, recent_progress_seconds=120)

    assert result["classification"] == "silent_but_active"


def test_activity_classifier_returns_likely_stalled_for_old_progress_file(tmp_path: Path):
    _, run_dir = _workflow(tmp_path)
    old = time.time() - 1000
    for path in run_dir.iterdir():
        os.utime(path, (old, old))

    result = classify_activity(tmp_path, recent_progress_seconds=1, likely_stalled_seconds=600)

    assert result["classification"] == "likely_stalled"


def test_activity_classifier_uses_latest_attempt_from_manifest(tmp_path: Path):
    wf, run_dir = _workflow(tmp_path)
    second = wf / "runs" / "P0002_attempt1"
    second.mkdir(parents=True)
    (second / "progress.jsonl").write_text("{}\n", encoding="utf-8")
    manifest = json.loads((wf / "run_manifest.json").read_text(encoding="utf-8"))
    manifest["runs"].append(
        {
            "attempt_id": "P0002_attempt1",
            "patchlet_id": "P0002",
            "lifecycle_status": "ATTEMPT_STARTED",
            "paths": {"progress_jsonl": ".codex-orchestrator/runs/P0002_attempt1/progress.jsonl"},
        }
    )
    _write_json(wf / "run_manifest.json", manifest)

    result = classify_activity(tmp_path)

    assert result["current_attempt_id"] == "P0002_attempt1"


def test_activity_classifier_handles_missing_progress_file(tmp_path: Path):
    _, run_dir = _workflow(tmp_path)
    (run_dir / "progress.jsonl").unlink()

    result = classify_activity(tmp_path)

    assert result["classification"] == "silent_but_active"


def test_activity_classifier_handles_missing_manifest(tmp_path: Path):
    wf, _ = _workflow(tmp_path)
    (wf / "run_manifest.json").unlink()

    result = classify_activity(tmp_path)

    assert result["classification"] == "unknown"


def test_activity_classifier_reports_last_progress_path_and_age(tmp_path: Path):
    _workflow(tmp_path)

    result = classify_activity(tmp_path)

    assert result["last_progress_path"] == ".codex-orchestrator/runs/P0001_attempt1/progress.jsonl"
    assert isinstance(result["last_progress_age_seconds"], int)


def test_activity_classifier_reports_next_action_for_active_worker(tmp_path: Path):
    _workflow(tmp_path)

    result = classify_activity(tmp_path)

    assert "Waiting" in result["next_action"]
