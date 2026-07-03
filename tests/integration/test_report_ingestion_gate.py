from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

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


def test_report_ingestion_preserves_raw_report(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert (ctx.paths.reports_dir / "P0001.raw.json").exists()


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
