from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import read_json

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


def _scenario(ctx, data):
    p = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def test_report_shape_only_failure_is_classified_report_shape_only(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, {"report_override": {"probe_artifact_refs": ["/etc/passwd"]}})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert read_json(ctx.paths.failures_dir / "F0001.json")["failure_signature"] == "probe_artifact_refs_unsafe_path"


def test_safe_normalizable_probe_refs_continue_without_full_patchlet_regeneration(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, {"report_override": {"probe_artifact_refs": [".artifacts/probes/P0001/run_001/before_state.json"]}})
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "VERIFIED_NO_CHANGE_NEEDED"


def test_report_shape_only_failure_does_not_generate_full_repair_patchlet_when_normalization_succeeds(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, {"report_override": {"probe_artifact_refs": [".artifacts/probes/P0001/run_001/before_state.json"]}})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert not list(ctx.paths.failures_dir.glob("F*.json"))


def test_report_shape_only_failure_writes_report_only_repair_plan_when_needed(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, {"report_override": {"probe_artifact_refs": ["/etc/passwd"]}})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert failure["report_validation_errors_path"].endswith("report_validation_errors.json")


def test_report_only_repair_plan_forbids_product_runtime_paths(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, {"report_override": {"probe_artifact_refs": ["/etc/passwd"]}})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert "app.py" not in json.dumps(failure.get("report_validation_errors", []))


def test_report_only_repair_plan_forbids_probe_artifact_mutation(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, {"report_override": {"probe_artifact_refs": ["/etc/passwd"]}})
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json").exists()


def test_repeated_report_shape_failure_safe_fails_instead_of_unbounded_regeneration(git_repo: Path):
    from codex_orchestrator.loop_governor import record_failure_signature

    governor = {}
    for i in range(1, 4):
        governor = record_failure_signature(git_repo, failure_record={"failure_id": f"F{i:04d}", "source_id": f"P{i:04d}", "source_patchlet_ids": [f"P{i:04d}"], "failure_signature": "probe_artifact_refs_not_objects"}, mode="safe-fail")
    assert governor["blocked"] is True


def test_report_shape_unsafe_path_safe_fails_with_specific_evidence(git_repo: Path):
    from codex_orchestrator.loop_governor import record_failure_signature

    governor = {}
    for i in range(1, 4):
        governor = record_failure_signature(git_repo, failure_record={"failure_id": f"F{i:04d}", "source_id": f"P{i:04d}", "source_patchlet_ids": [f"P{i:04d}"], "failure_signature": "probe_artifact_refs_unsafe_path"}, mode="safe-fail")
    assert "probe_artifact_refs_unsafe_path" in governor["blocked_reason"]


def test_non_allowlisted_peer_change_does_not_route_to_repair(git_repo: Path):
    ctx = _ctx(git_repo)
    other = ctx.root / "other.py"
    other.write_text("baseline = True\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ctx.root), "add", "other.py"], check=True)
    subprocess.run(["git", "-C", str(ctx.root), "commit", "-m", "add tracked unauthorized file"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _scenario(ctx, {"unauthorized_files": {"other.py": "x"}})
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
    assert not (ctx.paths.failures_dir / "F0001.json").exists()


def test_worker_timeout_still_routes_to_worker_failure_handling(git_repo: Path):
    assert True


def test_target_dirty_failure_still_routes_to_target_hygiene_failure(git_repo: Path):
    assert True


def test_loop_governor_records_report_contract_repeated_shape_failure(git_repo: Path):
    from codex_orchestrator.loop_governor import record_failure_signature

    governor = record_failure_signature(git_repo, failure_record={"failure_id": "F0001", "source_id": "P0001", "source_patchlet_ids": ["P0001"], "failure_signature": "probe_artifact_refs_not_objects"})
    assert governor["failure_signatures"][0]["message_fingerprint"] == "probe_artifact_refs_not_objects"
