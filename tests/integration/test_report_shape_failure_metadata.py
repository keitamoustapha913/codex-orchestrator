from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.loop_governor import normalize_failure_signature, record_failure_signature
from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _bad(ctx):
    path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"report_production_override": {"probe_artifact_refs": ["/etc/passwd"]}}), encoding="utf-8")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)


def test_failure_record_includes_report_validation_errors(git_repo: Path):
    ctx = _ctx(git_repo)
    _bad(ctx)
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert failure["report_validation_errors"]


def test_failure_record_includes_failure_signature(git_repo: Path):
    ctx = _ctx(git_repo)
    _bad(ctx)
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert failure["failure_signature"] == "probe_artifact_refs_unsafe_path"


def test_failure_record_does_not_claim_ingestion_ran_after_pre_submission_failure(
    git_repo: Path,
):
    ctx = _ctx(git_repo)
    _bad(ctx)
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert "report_ingestion_result_path" not in failure


def test_failure_record_links_report_validation_errors_artifact(git_repo: Path):
    ctx = _ctx(git_repo)
    _bad(ctx)
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert failure["report_validation_errors_path"].endswith("report_validation_errors.json")


def test_operator_event_includes_report_failure_signature(git_repo: Path):
    ctx = _ctx(git_repo)
    _bad(ctx)
    event = [event for event in read_operator_events(ctx.root) if event["event_type"] == "patchlet_report_validated"][-1]
    assert event["details"]["failure_signature"] == "probe_artifact_refs_unsafe_path"


def test_operator_event_includes_report_validation_error_artifact_path(git_repo: Path):
    ctx = _ctx(git_repo)
    _bad(ctx)
    event = [event for event in read_operator_events(ctx.root) if event["event_type"] == "patchlet_report_validated"][-1]
    assert event["details"]["report_validation_errors_path"].endswith("report_validation_errors.json")


def test_diagnosis_includes_probe_artifact_refs_not_objects_signature(git_repo: Path):
    category, fingerprint = normalize_failure_signature({"field": "probe_artifact_refs", "expected_type": "object", "actual_type": "string", "observed_failure": "'.artifacts/probes/P0002/comparison.txt' is not of type 'object'"})
    assert category == "patchlet_report_schema_violation"
    assert fingerprint == "probe_artifact_refs_not_objects"


def test_loop_governor_prefers_failure_record_signature(git_repo: Path):
    governor = record_failure_signature(git_repo, failure_record={"failure_id": "F0001", "source_id": "P0001", "source_patchlet_ids": ["P0001"], "failure_signature": "probe_artifact_refs_not_objects", "observed_failure": "generic"})
    assert governor["failure_signatures"][0]["message_fingerprint"] == "probe_artifact_refs_not_objects"


def test_loop_governor_prefers_structured_report_validation_error_signature(git_repo: Path):
    governor = record_failure_signature(git_repo, failure_record={"failure_id": "F0001", "source_id": "P0001", "source_patchlet_ids": ["P0001"], "report_validation_errors": [{"normalized_signature": "probe_artifact_refs_not_objects"}]})
    assert governor["failure_signatures"][0]["message_fingerprint"] == "probe_artifact_refs_not_objects"


def test_loop_governor_no_longer_emits_unknown_for_probe_ref_string_type_error(git_repo: Path):
    for i in range(1, 4):
        record_failure_signature(git_repo, failure_record={"failure_id": f"F{i:04d}", "source_id": f"P{i:04d}", "source_patchlet_ids": [f"P{i:04d}"], "failure_signature": "probe_artifact_refs_not_objects"})
    event = [event for event in read_operator_events(git_repo) if event["event_type"] == "loop_governor_warning"][-1]
    assert "unknown_repeated_failure" not in event["summary"]


def test_loop_governor_text_fallback_recognizes_exact_live_jsonschema_message_when_field_context_exists():
    _category, fingerprint = normalize_failure_signature({"field": "probe_artifact_refs", "expected_type": "object", "actual_type": "string", "observed_failure": "'.artifacts/probes/P0002/comparison.txt' is not of type 'object'"})
    assert fingerprint == "probe_artifact_refs_not_objects"
