from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.stages.apply_repair import apply_repair
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.classify_failures import classify_failures
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.plan_repair import plan_repair
from codex_orchestrator.stages.regenerate_patchlets import regenerate_patchlets
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


def _events(ctx):
    return read_operator_events(ctx.root)


def _event_types(ctx) -> list[str]:
    return [event["event_type"] for event in _events(ctx)]


def _event(ctx, event_type: str) -> dict:
    matches = [event for event in _events(ctx) if event["event_type"] == event_type]
    assert matches, f"missing event {event_type}"
    return matches[-1]


def _write_invalid_report_scenario(ctx) -> None:
    scenario = {
        "report_production_override": {
            "probe_artifact_refs": ["bad-probe-ref"],
        }
    }
    scenario_path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")


def _run_invalid_patchlet(ctx):
    _write_invalid_report_scenario(ctx)
    return run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)


def test_run_next_emits_patchlet_started_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    event = _event(ctx, "patchlet_started")
    assert event["patchlet_id"] == "P0001"
    assert event["attempt_id"] == "P0001_attempt1"
    assert "Started patchlet P0001" in event["summary"]


def test_run_next_emits_prompt_written_event_before_worker_start(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    types = _event_types(ctx)
    assert types.index("patchlet_prompt_written") < types.index("patchlet_worker_started")
    event = _event(ctx, "patchlet_prompt_written")
    assert event["prompt_path"] == ".codex-orchestrator/runs/P0001_attempt1/codex_task_prompt.md"


def test_run_next_emits_worker_started_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    event = _event(ctx, "patchlet_worker_started")
    assert event["details"]["worker_mode"] == "mock"
    assert event["next_action"] == "Waiting for worker to finish."


def test_run_next_emits_worker_exited_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    event = _event(ctx, "patchlet_worker_exited")
    assert event["severity"] == "success"
    assert event["details"]["exit_code"] == 0


def test_run_next_emits_report_validated_event_for_valid_report(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    event = _event(ctx, "patchlet_report_validated")
    assert event["severity"] == "success"
    assert event["details"]["report_valid"] is True


def test_run_next_emits_report_validated_event_for_invalid_report(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    result = _run_invalid_patchlet(ctx)

    event = _event(ctx, "patchlet_report_validated")
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert event["severity"] == "error"
    assert event["details"]["report_valid"] is False


def test_run_next_emits_wrapper_gate_passed_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert _event(ctx, "patchlet_wrapper_gate_passed")["severity"] == "success"


def test_run_next_emits_wrapper_gate_failed_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_invalid_patchlet(ctx)

    assert _event(ctx, "patchlet_wrapper_gate_failed")["severity"] == "error"


def test_run_next_emits_target_hygiene_event_when_hygiene_runs(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    event = _event(ctx, "patchlet_target_hygiene_passed")
    assert event["artifact_paths"][0].endswith("target_hygiene_gate_result.json")


def test_run_next_emits_patchlet_accepted_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    event = _event(ctx, "patchlet_accepted")
    assert event["severity"] == "success"
    assert event["details"]["report_status"] == "VERIFIED_NO_CHANGE_NEEDED"


def test_run_next_emits_patchlet_failed_with_evidence_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_invalid_patchlet(ctx)

    event = _event(ctx, "patchlet_failed_with_evidence")
    assert event["severity"] == "error"
    assert "failed with evidence" in event["summary"]


def test_failure_record_creation_emits_operator_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_invalid_patchlet(ctx)

    event = _event(ctx, "failure_record_created")
    assert event["failure_id"] == "F0001"
    assert event["artifact_paths"] == [
        ".codex-orchestrator/failures/F0001.json",
        ".codex-orchestrator/failures/F0001.md",
    ]


def test_repair_planning_emits_repair_plan_created_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_invalid_patchlet(ctx)
    classify_failures(ctx)

    plan_repair(ctx)

    event = _event(ctx, "repair_plan_created")
    assert event["repair_plan_id"] == "RP0001"
    assert ".codex-orchestrator/repair_plans/RP0001.json" in event["artifact_paths"]


def test_patchlet_regeneration_emits_repair_patchlets_regenerated_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_invalid_patchlet(ctx)
    classify_failures(ctx)
    plan_repair(ctx)
    apply_repair(ctx)

    result = regenerate_patchlets(ctx)

    event = _event(ctx, "repair_patchlets_regenerated")
    assert result["patchlet_ids"] == ["P0002"]
    assert event["repair_plan_id"] == "RP0001"
    assert event["details"]["patchlet_ids"] == ["P0002"]


def test_operator_events_include_artifact_paths(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert any(event["artifact_paths"] for event in _events(ctx))
    assert ".codex-orchestrator/runs/P0001_attempt1/output.jsonl" in _event(ctx, "patchlet_worker_exited")["artifact_paths"]


def test_operator_events_include_prompt_path_and_next_action(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    event = _event(ctx, "patchlet_prompt_written")
    assert event["prompt_path"].endswith("codex_task_prompt.md")
    assert event["next_action"] == "Starting worker."


def test_operator_events_are_in_lifecycle_order(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    types = _event_types(ctx)
    ordered = [
        "patchlet_started",
        "patchlet_prompt_written",
        "patchlet_worker_started",
        "patchlet_worker_exited",
        "patchlet_report_validated",
        "patchlet_wrapper_gate_passed",
        "patchlet_target_hygiene_passed",
        "patchlet_checkpoint_written",
        "patchlet_integration_validated",
        "patchlet_accepted",
    ]
    assert [event for event in types if event in ordered] == ordered


def test_late_failure_still_emits_failure_event(git_repo: Path, monkeypatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)

    monkeypatch.setattr(
        run_patchlet_stage,
        "_write_integration_validation_result",
        lambda _ctx: {
            "schema_version": "1.0",
            "kind": "integration_artifact_validation",
            "valid": False,
            "repo": str(git_repo),
            "validated": {},
            "errors": [{"path": ".codex-orchestrator/integration/checkpoints/P0001.json", "message": "forced"}],
            "warnings": [],
        },
    )

    try:
        run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    except Exception as exc:
        assert "integration artifact validation failed" in str(exc)

    event = _event(ctx, "patchlet_failed_with_evidence")
    assert "integration artifact validation failed" in event["summary"]
    assert read_json(ctx.paths.run_manifest)["runs"][0]["attempt_id"] == "P0001_attempt1"
