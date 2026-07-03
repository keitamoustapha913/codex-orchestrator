from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import read_json

from codex_orchestrator.errors import WorkerExecutionError
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


def _compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _run_entry(ctx, attempt_id: str = "P0001_attempt1") -> dict:
    manifest = read_json(ctx.paths.run_manifest)
    matches = [run for run in manifest["runs"] if run.get("attempt_id") == attempt_id]
    assert len(matches) == 1
    return matches[0]


def _event_stages(entry: dict) -> list[str]:
    return [event["stage"] for event in entry.get("lifecycle_events", [])]


def test_run_manifest_entry_created_before_worker_execution(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _run_entry(ctx)
    assert entry["attempt_id"] == "P0001_attempt1"
    assert _event_stages(entry)[0] == "ATTEMPT_STARTED"
    assert entry["paths"]["run_dir"] == ".codex-orchestrator/runs/P0001_attempt1"


def test_run_manifest_updates_same_attempt_id_after_worker_exit(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _run_entry(ctx)
    assert "WORKER_EXITED" in _event_stages(entry)
    assert entry["exit_code"] == 0


def test_run_manifest_records_report_validation_stage(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _run_entry(ctx)
    assert "REPORT_VALIDATED" in _event_stages(entry)
    assert entry["report_valid"] is True
    assert entry["report_validation"]["valid"] is True


def test_run_manifest_records_wrapper_gate_stage(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _run_entry(ctx)
    assert "WRAPPER_GATE_EVALUATED" in _event_stages(entry)
    assert entry["wrapper_gate_accepted"] is True
    assert entry["wrapper_gate_result"].endswith("wrapper_gate_result.json")


def test_run_manifest_records_target_hygiene_stage(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _run_entry(ctx)
    assert "TARGET_HYGIENE_EVALUATED" in _event_stages(entry)
    assert entry["target_hygiene_accepted"] is True
    assert entry["target_hygiene_gate_result"].endswith("target_hygiene_gate_result.json")


def test_run_manifest_records_checkpoint_written_stage(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _run_entry(ctx)
    assert "INTEGRATION_CHECKPOINT_WRITTEN" in _event_stages(entry)
    assert entry["integration_checkpoint_path"] == ".codex-orchestrator/integration/checkpoints/P0001.json"
    assert entry["target_cleanliness_report_path"] == ".codex-orchestrator/integration/checkpoints/P0001_cleanliness.json"


def test_run_manifest_records_integration_validation_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)

    def invalid_integration_validation(_ctx):
        return {
            "schema_version": "1.0",
            "kind": "integration_artifact_validation",
            "valid": False,
            "repo": str(git_repo),
            "validated": {},
            "errors": [
                {
                    "path": ".codex-orchestrator/integration/checkpoints/P0001.json",
                    "schema": "integration_checkpoint.schema.json",
                    "message": "forced integration validation failure",
                }
            ],
            "warnings": [],
        }

    monkeypatch.setattr(run_patchlet_stage, "_write_integration_validation_result", invalid_integration_validation)

    with pytest.raises(WorkerExecutionError, match="integration artifact validation failed"):
        run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _run_entry(ctx)
    assert "ATTEMPT_FAILED_WITH_EVIDENCE" in _event_stages(entry)
    assert entry["failed_stage"] == "INTEGRATION_ARTIFACTS_VALIDATION_FAILED"
    assert entry["integration_artifact_validation"]["valid"] is False
    assert entry["integration_artifact_validation"]["errors"][0]["message"] == "forced integration validation failure"


def test_p0004_like_failure_still_has_p0004_manifest_entry(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)
    state = read_json(ctx.paths.state)
    state["attempts"] = {"P0001": 3}
    ctx.paths.state.write_text(json.dumps(state), encoding="utf-8")

    monkeypatch.setattr(
        run_patchlet_stage,
        "_write_integration_validation_result",
        lambda _ctx: {
            "schema_version": "1.0",
            "kind": "integration_artifact_validation",
            "valid": False,
            "repo": str(git_repo),
            "validated": {},
            "errors": [{"path": ".codex-orchestrator/integration/checkpoints/P0001.json", "message": "late failure"}],
            "warnings": [],
        },
    )

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _run_entry(ctx, "P0001_attempt4")
    assert entry["attempt_id"] == "P0001_attempt4"
    assert entry["failed_stage"] == "INTEGRATION_ARTIFACTS_VALIDATION_FAILED"


def test_run_manifest_update_is_atomic(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    manifest = read_json(ctx.paths.run_manifest)
    assert manifest["kind"] == "run_manifest"
    assert manifest["runs"][0]["attempt_id"] == "P0001_attempt1"


def test_no_duplicate_manifest_entries_for_same_attempt(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    manifest = read_json(ctx.paths.run_manifest)
    assert [run["attempt_id"] for run in manifest["runs"]].count("P0001_attempt1") == 1


def test_existing_manifest_consumers_still_read_runs_list(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    manifest = read_json(ctx.paths.run_manifest)
    assert isinstance(manifest["runs"], list)
    assert manifest["runs"][0]["run_id"] == "R0001"
    assert manifest["runs"][0]["status"] in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
