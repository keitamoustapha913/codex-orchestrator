from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from conftest import read_json

from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.report_ingestion import ingest_patchlet_report
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


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


def _scenario(ctx, refs):
    path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"report_override": {"probe_artifact_refs": refs}}), encoding="utf-8")


def _report_with_changed_runtime_file_alias() -> dict:
    return {
        "schema_version": "2.0",
        "kind": "worker_patchlet_report",
        "patchlet_id": "P0001",
        "status": "COMPLETE",
        "changed_runtime_file": "app.py",
        "changed_artifact_files": [],
        "probe_commands": ["python app.py"],
        "deterministic_run_counts": {},
        "root_cause_classification": {},
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "clean",
        "probe_artifact_refs": [],
        "semantic_goal_results": [],
    }


def test_changed_runtime_file_is_unknown_v2_extension(git_repo: Path):
    ctx = _ctx(git_repo)
    source = git_repo / "P0001.alias.json"
    write_json(source, _report_with_changed_runtime_file_alias())

    result = ingest_patchlet_report(
        ctx,
        patchlet={
            "patchlet_id": "P0001",
            "goal_item_ids": ["GI001"],
            "proof_obligation_ids": ["PO001"],
            "probe_ids": ["GP001"],
        },
        attempt_id="P0001_attempt1",
        report_path=source,
    )

    assert result["unknown_fields"] == ["changed_runtime_file"]
    assert "legacy_field_mappings" not in result


def test_changed_runtime_file_never_populates_changed_product_runtime_file(git_repo: Path):
    ctx = _ctx(git_repo)
    source = git_repo / "P0001.alias.json"
    write_json(source, _report_with_changed_runtime_file_alias())

    result = ingest_patchlet_report(
        ctx,
        patchlet={
            "patchlet_id": "P0001",
            "goal_item_ids": ["GI001"],
            "proof_obligation_ids": ["PO001"],
            "probe_ids": ["GP001"],
        },
        attempt_id="P0001_attempt1",
        report_path=source,
    )

    canonical = read_json(ctx.paths.reports_dir / "P0001.json")
    assert result["accepted"] is False
    assert "changed_product_runtime_file" not in canonical


def test_report_ingestion_preserves_raw_report(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert (ctx.paths.reports_dir / "P0001.raw.json").exists()


def test_p0005_v2_unknown_acceptance_criteria_result_is_warning_and_does_not_block(git_repo: Path):
    ctx = _ctx(git_repo)
    scenario = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    scenario.parent.mkdir(parents=True, exist_ok=True)
    scenario.write_text(json.dumps({"report_override": {
        "schema_version": "2.0",
        "kind": "worker_patchlet_report",
        "acceptance_criteria_result": {"status": "PASS"},
    }}), encoding="utf-8")

    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert result.status != "FAILED_WITH_EVIDENCE"
    raw_path = ctx.paths.reports_dir / "P0001.raw.json"
    ingestion = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")
    assert raw_path.read_bytes() == raw_path.read_bytes()
    assert ingestion["raw_envelope"]["parseable"] is True
    assert ingestion["unknown_fields"] == ["acceptance_criteria_result"]
    assert ingestion["unknown_field_status"] == "WARNING"
    assert ingestion["report_reorganization_used"] is True
    assert ingestion["report_reorganization_result"] == "ACCEPTED"
    assert read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/worker_report_integrity_result.json")["accepted"] is True
    assert not any("repair" in path.name.lower() for path in ctx.paths.patchlets_dir.glob("*.json"))


def test_v2_report_without_acceptance_criteria_result_is_valid_and_no_repair(git_repo: Path):
    ctx = _ctx(git_repo)
    report = {
        "schema_version": "2.0", "kind": "worker_patchlet_report", "patchlet_id": "P0001",
        "status": "COMPLETE", "changed_product_runtime_file": "app.py", "changed_artifact_files": [],
        "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
        "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "baseline failed", "immediate_cause": "wrong value",
            "why_immediate_cause_happened": "stale implementation", "deeper_owner_boundary": "app.py",
            "producer_transformer_consumer_boundary": "app.py -> probe",
            "not_downstream_of_unprobed_state_proof": "direct probe", "negative_control_proof": "adjacent values unchanged",
            "recursive_why_audit": ["why1", "why2"],
        },
        "before_after_state": [], "row_ledger": [], "trace_ledger": [], "cleanup_proof": "clean",
        "probe_artifact_refs": [{"patchlet_id": "P0001", "probe_root": ".artifacts/probes/P0001", "run_id": "default"}],
        "semantic_goal_results": [],
    }
    source = git_repo / "P0001.v2-no-acceptance.json"
    write_json(source, report)
    result = ingest_patchlet_report(ctx, patchlet={"patchlet_id": "P0001", "goal_item_ids": ["GI001"], "proof_obligation_ids": ["PO001"], "probe_ids": ["GP001"]}, attempt_id="P0001_attempt1", report_path=source)
    assert result["accepted"] is True, json.dumps(result, indent=2)
    assert result["unknown_fields"] == []
    assert result["validation"]["valid"] is True
    assert not any("repair" in path.name.lower() for path in ctx.paths.patchlets_dir.glob("*.json"))


@pytest.mark.parametrize("repeat", range(5))
def test_exact_p0005_attempt1_report_ingestion_identity_and_hash(git_repo: Path, repeat: int):
    ctx = _ctx(git_repo)
    report = {
        "schema_version": "2.0", "kind": "worker_patchlet_report", "patchlet_id": "P0005",
        "status": "COMPLETE", "changed_product_runtime_file": "owner.mjs",
        "changed_artifact_files": [], "probe_commands": ["probe GP005"],
        "deterministic_run_counts": {"baseline": "1/1", "negative_controls": "1/1", "proof_of_fix": "1/1"}, "root_cause_classification": {
            "observed_failure": "observed", "immediate_cause": "cause", "why_immediate_cause_happened": "why",
            "deeper_owner_boundary": "owner.mjs", "producer_transformer_consumer_boundary": "boundary",
            "not_downstream_of_unprobed_state_proof": "direct", "negative_control_proof": "negative",
            "recursive_why_audit": ["why"],
        },
        "before_after_state": [], "row_ledger": [], "trace_ledger": [],
        "cleanup_proof": "clean", "semantic_goal_results": [],
        "probe_artifact_refs": [{"patchlet_id": "P0005", "probe_root": ".artifacts/probes/P0005", "run_id": "default"}],
        "acceptance_criteria_result": {"status": "PASS"},
    }
    source = git_repo / "P0005.worker.json"
    write_json(source, report)
    expected_bytes = source.read_bytes()
    result = ingest_patchlet_report(ctx, patchlet={
        "patchlet_id": "P0005", "goal_item_ids": ["GI005"],
        "proof_obligation_ids": ["PO005"], "probe_ids": ["GP005"],
    }, attempt_id="P0005_attempt1", report_path=source)
    assert result["accepted"] is True, json.dumps(result, indent=2)
    assert result["attempt_id"] == "P0005_attempt1"
    assert result["patchlet_id"] == "P0005"
    assert (ctx.paths.reports_dir / "P0005.raw.json").read_bytes() == expected_bytes
    assert result["raw_report_sha256"] == hashlib.sha256(expected_bytes).hexdigest()
    assert result["unknown_fields"] == ["acceptance_criteria_result"]


def test_report_ingestion_writes_canonical_report(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    report = read_json(ctx.paths.reports_dir / "P0001.json")
    assert isinstance(report["probe_artifact_refs"][0], dict)


def test_report_ingestion_normalizes_probe_ref_strings(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json", ".artifacts/probes/P0001/run_001/after_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    result = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")
    assert result["normalization_applied"] is True
    assert result["canonical_probe_artifact_refs"][0]["files"][0]["path"].endswith("after_state.json")


def test_report_ingestion_records_raw_and_canonical_paths(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    result = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")
    assert result["raw_report_path"] == ".codex-orchestrator/reports/P0001.raw.json"
    assert result["canonical_report_path"] == ".codex-orchestrator/reports/P0001.json"


def test_report_ingestion_records_normalization_kinds(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    result = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")
    assert result["normalization_kinds"] == ["probe_artifact_refs_string_paths_to_objects"]


def test_report_ingestion_writes_result_json(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json").exists()


def test_report_ingestion_writes_validation_errors_json(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json").exists()


def test_report_ingestion_result_schema_validates(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert validate_json_file(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json", "report_ingestion_result.schema.json") == []


def test_report_ingestion_errors_schema_validates(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert validate_json_file(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json", "report_validation_errors.schema.json") == []


def test_report_ingestion_rejects_unsafe_path(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, ["/etc/passwd"])

    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    errors = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json")["errors"]
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_report_ingestion_rejects_missing_probe_file(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/missing.txt"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    errors = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json")["errors"]
    assert errors[0]["normalized_signature"] == "probe_artifact_refs_missing_file"


def test_report_ingestion_rejects_patchlet_mismatch(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json", ".artifacts/probes/P9999/file.txt"])
    bad = git_repo / ".artifacts/probes/P9999/file.txt"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("x", encoding="utf-8")

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    errors = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json")["errors"]
    assert any(error["normalized_signature"] == "probe_artifact_refs_patchlet_mismatch" for error in errors)


def test_report_ingestion_rejects_symlink_escape(git_repo: Path, tmp_path: Path):
    ctx = _ctx(git_repo)
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    link = git_repo / ".artifacts/probes/P0001/symlink_to_outside"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)
    _scenario(ctx, [".artifacts/probes/P0001/symlink_to_outside"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    errors = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json")["errors"]
    assert errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_report_ingestion_emits_normalized_operator_event(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert any(event["event_type"] == "report_ingestion_normalized" for event in read_operator_events(ctx.root))


def test_report_ingestion_emits_failed_operator_event(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, ["/etc/passwd"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    events = [event for event in read_operator_events(ctx.root) if event["event_type"] == "report_ingestion_failed"]
    assert events[-1]["details"]["failure_signature"] == "probe_artifact_refs_unsafe_path"


def test_wrapper_gate_uses_canonical_report_after_ingestion(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/wrapper_gate_result.json")
    assert gate["report_gate"] == "pass"
    assert gate["accepted"] is True


def test_wrapper_gate_rejects_failed_ingestion_with_structured_error(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, ["/etc/passwd"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/wrapper_gate_result.json")
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert gate["accepted"] is False
    assert failure["failure_signature"] == "probe_artifact_refs_unsafe_path"
