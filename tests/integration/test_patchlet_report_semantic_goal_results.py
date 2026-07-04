from __future__ import annotations

from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.report_validator import validate_patchlet_report_structured
from codex_orchestrator.validators.schema_validator import validate_json
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path):
    prompt = git_repo / "master_prompt_me.md"
    prompt.write_text("Make app return me and prove it.\n", encoding="utf-8")
    run(["git", "add", "master_prompt_me.md"], git_repo)
    run(["git", "commit", "-m", "add semantic prompt"], git_repo)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=prompt, invocation_argv=["cxor", "init"])
    write_workflow_identity(ctx, build_workflow_identity(ctx, master=prompt, worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001"))
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _report(status: str = "VERIFIED_NO_CHANGE_NEEDED", *, expected="me", actual="me", passed=True):
    return {
        "schema_version": "1.0",
        "kind": "patchlet_report",
        "patchlet_id": "P0001",
        "status": status,
        "final_status_marker": "FINAL_STATUS: PASS",
        "changed_product_runtime_file": "app.py" if status == "COMPLETE" else None,
        "changed_artifact_files": [".artifacts/probes/P0001/probe.py"],
        "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
        "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "x",
            "immediate_cause": "x",
            "why_immediate_cause_happened": "x",
            "deeper_owner_boundary": "app.py",
            "producer_transformer_consumer_boundary": "x",
            "not_downstream_of_unprobed_state_proof": "x",
            "negative_control_proof": "x",
            "recursive_why_audit": ["x", "y", "z"],
        },
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "ok",
        "probe_artifact_refs": [{"patchlet_id": "P0001", "probe_root": ".artifacts/probes/P0001", "run_id": "default"}],
        "semantic_goal_results": [{
            "criterion_id": "SGC001",
            "kind": "python_module_function_returns",
            "expected_value": expected,
            "actual_value": actual,
            "passed": passed,
        }],
        "acceptance_criteria_result": "pass",
    }


def test_report_schema_accepts_semantic_goal_results():
    assert validate_json(_report(), "patchlet_report.schema.json") == []


def test_report_validator_requires_semantic_results_for_structured_goal(git_repo: Path):
    ctx = _ctx(git_repo)
    report = _report()
    del report["semantic_goal_results"]
    result = validate_patchlet_report_structured(report, read_json(ctx.paths.patchlet_index)["patchlets"][0], repo_root=ctx.root)
    assert any(error["normalized_signature"] == "semantic_goal_results_missing" for error in result["errors"])


def test_report_validator_rejects_missing_required_criterion(git_repo: Path):
    ctx = _ctx(git_repo)
    report = _report()
    report["semantic_goal_results"] = []
    result = validate_patchlet_report_structured(report, read_json(ctx.paths.patchlet_index)["patchlets"][0], repo_root=ctx.root)
    assert any(error["normalized_signature"] == "semantic_goal_results_missing_required_criterion" for error in result["errors"])


def test_report_validator_rejects_wrong_expected_value(git_repo: Path):
    ctx = _ctx(git_repo)
    result = validate_patchlet_report_structured(_report(expected="ok", actual="ok"), read_json(ctx.paths.patchlet_index)["patchlets"][0], repo_root=ctx.root)
    assert any(error["normalized_signature"] == "semantic_goal_results_wrong_expected_value" for error in result["errors"])


def test_report_validator_rejects_pass_true_when_actual_differs(git_repo: Path):
    ctx = _ctx(git_repo)
    result = validate_patchlet_report_structured(_report(actual="ok", passed=True), read_json(ctx.paths.patchlet_index)["patchlets"][0], repo_root=ctx.root)
    assert any(error["normalized_signature"] == "semantic_goal_results_self_contradictory" for error in result["errors"])


def test_report_validator_accepts_verified_no_change_when_semantic_result_passes(git_repo: Path):
    ctx = _ctx(git_repo)
    assert validate_patchlet_report_structured(_report(), read_json(ctx.paths.patchlet_index)["patchlets"][0], repo_root=ctx.root)["valid"] is True


def test_report_validator_rejects_verified_no_change_when_semantic_result_fails(git_repo: Path):
    ctx = _ctx(git_repo)
    result = validate_patchlet_report_structured(_report(actual="ok", passed=False), read_json(ctx.paths.patchlet_index)["patchlets"][0], repo_root=ctx.root)
    assert any(error["normalized_signature"] == "semantic_goal_results_failed" for error in result["errors"])


def test_report_validator_rejects_complete_when_semantic_result_fails(git_repo: Path):
    ctx = _ctx(git_repo)
    result = validate_patchlet_report_structured(_report("COMPLETE", actual="ok", passed=False), read_json(ctx.paths.patchlet_index)["patchlets"][0], repo_root=ctx.root)
    assert any(error["normalized_signature"] == "semantic_goal_results_failed" for error in result["errors"])


def test_report_contract_includes_semantic_goal_results_section(git_repo: Path):
    ctx = _ctx(git_repo)
    from codex_orchestrator.stages.run_patchlet import run_next_patchlet

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")
    assert "## semantic_goal_results" in text


def test_report_contract_shows_invalid_ok_for_me_example(git_repo: Path):
    ctx = _ctx(git_repo)
    from codex_orchestrator.stages.run_patchlet import run_next_patchlet

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    text = (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/REPORT_SCHEMA_CONTRACT.md").read_text(encoding="utf-8")
    assert '"actual_value": "ok"' in text
    assert '"expected_value": "me"' in text
