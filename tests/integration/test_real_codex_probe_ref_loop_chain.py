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
    p = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"report_override": {"probe_artifact_refs": refs}}), encoding="utf-8")


def test_fake_real_codex_string_probe_refs_are_normalized_and_accepted(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json", ".artifacts/probes/P0001/run_001/after_state.json"])
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.report_valid is True


def test_fake_real_codex_raw_report_is_preserved(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.reports_dir / "P0001.raw.json").exists()


def test_fake_real_codex_canonical_report_has_object_probe_refs(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert isinstance(read_json(ctx.paths.reports_dir / "P0001.json")["probe_artifact_refs"][0], dict)


def test_fake_real_codex_ingestion_result_records_normalization(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")["normalization_applied"] is True


def test_fake_real_codex_wrapper_gate_uses_canonical_report(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/wrapper_gate_result.json")["report_gate"] == "pass"


def test_fake_real_codex_unsafe_probe_ref_fails_with_specific_signature(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, ["/etc/passwd"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert read_json(ctx.paths.failures_dir / "F0001.json")["failure_signature"] == "probe_artifact_refs_unsafe_path"


def test_fake_real_codex_repeated_probe_ref_shape_failure_warns_with_specific_signature(git_repo: Path):
    from codex_orchestrator.loop_governor import record_failure_signature

    for i in range(1, 4):
        record_failure_signature(git_repo, failure_record={"failure_id": f"F{i:04d}", "source_id": f"P{i:04d}", "source_patchlet_ids": [f"P{i:04d}"], "failure_signature": "probe_artifact_refs_not_objects"})
    event = [event for event in read_operator_events(git_repo) if event["event_type"] == "loop_governor_warning"][-1]
    assert "probe_artifact_refs_not_objects" in event["summary"]


def test_fake_real_codex_repeated_probe_ref_shape_failure_does_not_use_unknown_signature(git_repo: Path):
    from codex_orchestrator.loop_governor import record_failure_signature, read_loop_governor

    for i in range(1, 4):
        record_failure_signature(git_repo, failure_record={"failure_id": f"F{i:04d}", "source_id": f"P{i:04d}", "source_patchlet_ids": [f"P{i:04d}"], "failure_signature": "probe_artifact_refs_not_objects"})
    assert read_loop_governor(git_repo)["failure_signatures"][0]["message_fingerprint"] != "unknown_repeated_failure"


def test_fake_real_codex_report_shape_failure_does_not_regenerate_full_patchlet_when_normalized(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert not list(ctx.paths.failures_dir.glob("F*.json"))


def test_fake_real_codex_report_shape_safe_fail_preserves_evidence(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, ["/etc/passwd"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json").exists()


def test_fake_real_codex_repair_prompt_contains_object_ref_example(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert '"probe_root": ".artifacts/probes/P0001"' in (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")


def test_fake_real_codex_product_failure_still_routes_to_full_repair(git_repo: Path):
    ctx = _ctx(git_repo)
    p = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"unauthorized_files": {"other.py": "x"}}), encoding="utf-8")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert "failure_signature" not in failure
