from __future__ import annotations

from pathlib import Path

import pytest

from codex_orchestrator.activity_classifier import classify_activity
from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.loop_governor import loop_governor_path, normalize_failure_signature, record_failure_signature
from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.operator_progress import format_operator_event_compact
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.regenerate_patchlets import regenerate_patchlets
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import resolve_target_repo


def _failure(failure_id: str, patchlet_id: str, message: str) -> dict:
    return {
        "schema_version": "1.0",
        "kind": "failure_record",
        "failure_id": failure_id,
        "source_type": "patchlet",
        "source_id": patchlet_id,
        "source_patchlet_ids": [patchlet_id],
        "observed_failure": message,
    }


def test_loop_governor_json_created_after_failure_signature(git_repo: Path):
    record_failure_signature(git_repo, failure_record=_failure("F0001", "P0001", "first failure"))

    assert loop_governor_path(git_repo).exists()


def test_loop_governor_records_failure_signature(git_repo: Path):
    governor = record_failure_signature(git_repo, failure_record=_failure("F0001", "P0001", "first failure"))

    assert governor["failure_signatures"][0]["signature_id"] == "FS000001"


def test_loop_governor_normalizes_probe_artifact_refs_not_objects():
    category, fingerprint = normalize_failure_signature(
        "probe_artifact_refs entries must be JSON objects"
    )

    assert category == "patchlet_report_schema_violation"
    assert fingerprint == "probe_artifact_refs_not_objects"


def test_loop_governor_increments_repeated_signature_count(git_repo: Path):
    message = "probe_artifact_refs entries must be JSON objects"

    record_failure_signature(git_repo, failure_record=_failure("F0001", "P0001", message))
    governor = record_failure_signature(git_repo, failure_record=_failure("F0002", "P0002", message))

    assert governor["failure_signatures"][0]["count"] == 2


def test_loop_governor_records_patchlet_and_failure_ids(git_repo: Path):
    message = "probe artifact refs are not JSON objects"

    governor = record_failure_signature(git_repo, failure_record=_failure("F0001", "P0001", message))

    signature = governor["failure_signatures"][0]
    assert signature["patchlet_ids"] == ["P0001"]
    assert signature["failure_ids"] == ["F0001"]


def test_loop_governor_emits_warning_after_threshold(git_repo: Path):
    message = "probe artifact refs are not JSON objects"

    for index in range(1, 4):
        governor = record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", message))

    assert governor["warnings"][0]["message_fingerprint"] == "probe_artifact_refs_not_objects"
    assert governor["warnings"][0]["count"] == 3


def test_loop_governor_warning_operator_event_written(git_repo: Path):
    message = "probe artifact refs are not JSON objects"

    for index in range(1, 4):
        record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", message))

    events = [event for event in read_operator_events(git_repo) if event["event_type"] == "loop_governor_warning"]
    assert events
    assert "probe_artifact_refs_not_objects" in events[-1]["summary"]


def test_live_progress_prints_loop_governor_warning(git_repo: Path):
    message = "probe artifact refs are not JSON objects"
    for index in range(1, 4):
        record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", message))
    warning = [event for event in read_operator_events(git_repo) if event["event_type"] == "loop_governor_warning"][-1]

    assert "probe_artifact_refs_not_objects" in format_operator_event_compact(warning)


def test_loop_governor_warning_mode_does_not_block(git_repo: Path):
    message = "probe artifact refs are not JSON objects"

    for index in range(1, 4):
        governor = record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", message), mode="warning")

    assert governor["blocked"] is False
    assert governor["blocked_reason"] is None


def test_loop_governor_does_not_treat_distinct_failures_as_same_signature(git_repo: Path):
    record_failure_signature(git_repo, failure_record=_failure("F0001", "P0001", "probe artifact refs are not JSON objects"))
    governor = record_failure_signature(git_repo, failure_record=_failure("F0002", "P0002", "wrapper gate final status marker missing"))

    assert len(governor["failure_signatures"]) == 2


def test_loop_governor_safe_fail_blocks_after_repeated_signature_threshold(git_repo: Path):
    message = "probe artifact refs are not JSON objects"

    for index in range(1, 4):
        governor = record_failure_signature(
            git_repo,
            failure_record=_failure(f"F{index:04d}", f"P{index:04d}", message),
            mode="safe-fail",
            max_repeated_failure_signature=3,
        )

    assert governor["blocked"] is True
    assert "probe_artifact_refs_not_objects" in governor["blocked_reason"]


def test_loop_governor_safe_failure_preserves_evidence(git_repo: Path):
    message = "probe artifact refs are not JSON objects"

    for index in range(1, 4):
        record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", message), mode="safe-fail")

    assert loop_governor_path(git_repo).exists()
    assert read_operator_events(git_repo)


def test_loop_governor_safe_failure_does_not_generate_new_patchlet(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    state = load_state(ctx)
    transition(ctx, state, "PATCHLET_REGENERATION_REQUIRED", reason="test blocked regeneration")
    write_json(ctx.paths.patchlet_index, {"schema_version": "1.0", "kind": "patchlet_index", "patchlets": []})
    for index in range(1, 4):
        record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", "probe artifact refs are not JSON objects"), mode="safe-fail")

    with pytest.raises(StagePreconditionError):
        regenerate_patchlets(ctx)

    assert read_operator_events(git_repo)
    assert ctx.paths.patchlet_index.exists()


def test_loop_governor_safe_failure_records_no_blind_retry(git_repo: Path):
    for index in range(1, 4):
        governor = record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", "probe artifact refs are not JSON objects"), mode="safe-fail")

    assert "prevent unbounded repair loop" in governor["blocked_reason"]


def test_loop_governor_safe_failure_emits_blocked_event(git_repo: Path):
    for index in range(1, 4):
        record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", "probe artifact refs are not JSON objects"), mode="safe-fail")

    events = [event for event in read_operator_events(git_repo) if event["event_type"] == "loop_governor_blocked"]
    assert events


def test_loop_governor_safe_failure_records_blocked_reason(git_repo: Path):
    for index in range(1, 4):
        governor = record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", "probe artifact refs are not JSON objects"), mode="safe-fail")

    assert governor["blocked_reason"].startswith("Repeated failure signature")


def test_loop_governor_threshold_configurable(git_repo: Path):
    for index in range(1, 3):
        governor = record_failure_signature(
            git_repo,
            failure_record=_failure(f"F{index:04d}", f"P{index:04d}", "probe artifact refs are not JSON objects"),
            mode="safe-fail",
            max_repeated_failure_signature=2,
        )

    assert governor["blocked"] is True


def test_loop_governor_warning_mode_still_does_not_block(git_repo: Path):
    for index in range(1, 5):
        governor = record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", "probe artifact refs are not JSON objects"), mode="warning")

    assert governor["blocked"] is False


def test_loop_governor_safe_fail_does_not_block_distinct_failure_signatures(git_repo: Path):
    record_failure_signature(git_repo, failure_record=_failure("F0001", "P0001", "probe artifact refs are not JSON objects"), mode="safe-fail", max_repeated_failure_signature=2)
    governor = record_failure_signature(git_repo, failure_record=_failure("F0002", "P0002", "wrapper gate final status marker missing"), mode="safe-fail", max_repeated_failure_signature=2)

    assert governor["blocked"] is False


def test_loop_governor_safe_fail_updates_status_classification(git_repo: Path):
    wf = git_repo / ".codex-orchestrator"
    write_json(wf / "state.json", {"schema_version": "1.0", "kind": "workflow_state", "stage": "REPAIR_PLANNING_REQUIRED"})
    write_json(wf / "run_manifest.json", {"schema_version": "1.0", "kind": "run_manifest", "runs": []})
    for index in range(1, 4):
        record_failure_signature(git_repo, failure_record=_failure(f"F{index:04d}", f"P{index:04d}", "probe artifact refs are not JSON objects"), mode="safe-fail")

    result = classify_activity(git_repo)

    assert result["classification"] == "failed"
    assert "Repeated failure signature" in result["next_action"]
