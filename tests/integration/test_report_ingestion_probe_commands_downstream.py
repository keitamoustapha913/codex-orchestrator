from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from codex_orchestrator.goal_coverage import evaluate_goal_coverage_gate
from codex_orchestrator.independent_probe_rerun import run_independent_probe_rerun_gate

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.report_ingestion import ingest_patchlet_report
from codex_orchestrator.target_repo import resolve_target_repo


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def _ctx(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test User"], repo)
    (repo / "control.plan").write_text("flag=off\n", encoding="utf-8")
    (repo / "master_prompt.md").write_text("Turn the control flag on and prove it.\n", encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "initial"], repo)
    ctx = resolve_target_repo(repo, allow_self_target=True)
    for path in [ctx.paths.workflow_dir, ctx.paths.reports_dir, ctx.paths.runs_dir, ctx.paths.probe_dir / "P0100" / "run_001"]:
        path.mkdir(parents=True, exist_ok=True)
    artifact = ctx.paths.probe_dir / "P0100" / "run_001" / "proof.txt"
    artifact.write_text("flag=on\n", encoding="utf-8")
    return ctx, artifact


def _patchlet() -> dict[str, Any]:
    return {
        "patchlet_id": "P0100",
        "work_slice_id": "WS0100",
        "allowed_product_runtime_file": "control.plan",
        "goal_item_ids": ["GI0100"],
        "proof_obligation_ids": ["PO0100"],
    }


def _object_command() -> dict[str, Any]:
    return {
        "phase": "proof_of_fix",
        "command": "grep -qx 'flag=on' control.plan",
        "runs": "5/5",
        "expected_exit_code": 0,
    }


def _report(ctx, artifact: Path, probe_commands: list[Any]) -> dict[str, Any]:
    rel = artifact.relative_to(ctx.root).as_posix()
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {
        "schema_version": "1.0",
        "kind": "patchlet_report",
        "patchlet_id": "P0100",
        "status": "COMPLETE",
        "final_status_marker": "FINAL_STATUS: PASS",
        "changed_product_runtime_file": "control.plan",
        "changed_artifact_files": [".codex-orchestrator/reports/P0100.json"],
        "probe_commands": probe_commands,
        "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "flag off",
            "immediate_cause": "control flag disabled",
            "why_immediate_cause_happened": "initial target state sets flag=off",
            "deeper_owner_boundary": "target configuration",
            "producer_transformer_consumer_boundary": "repo file -> worker report -> report validator",
            "not_downstream_of_unprobed_state_proof": "string probe command reports validate with the same fixture",
            "negative_control_proof": "unrelated rows remain unchanged",
            "recursive_why_audit": ["why"],
        },
        "before_after_state": [{"key": "flag", "before": "off", "after": "on"}],
        "row_ledger": [{"path": rel, "kind": "row"}],
        "trace_ledger": [{"path": rel, "kind": "trace"}],
        "cleanup_proof": "temporary target only",
        "probe_artifact_refs": [
            {
                "patchlet_id": "P0100",
                "probe_root": ".artifacts/probes/P0100/run_001",
                "run_id": "run_001",
                "files": [{"path": rel, "kind": "proof", "sha256": digest, "size_bytes": artifact.stat().st_size}],
            }
        ],
        "acceptance_criteria_result": "pass",
    }


def _proof_obligations():
    return {
        "schema_version": "1.0",
        "workflow_id": "WF-TEST",
        "run_id": "R-TEST",
        "master_prompt_sha256": "0" * 64,
        "obligations": [
            {
                "obligation_id": "PO0100",
                "goal_item_ids": ["GI0100"],
                "required": True,
                "claim": "control flag must be on",
            }
        ],
    }


def _probe_plan():
    return {
        "schema_version": "1.0",
        "workflow_id": "WF-TEST",
        "run_id": "R-TEST",
        "probes": [
            {
                "probe_id": "GP0100",
                "obligation_ids": ["PO0100"],
                "rerunnable_by_orchestrator": True,
                "execution_context": "target_repo",
                "command": "grep -qx 'flag=on' control.plan",
                "expected_observation": {"type": "exit_code_zero", "value": 0},
            }
        ],
    }


def _run_path(tmp_path: Path, probe_commands):
    ctx, artifact = _ctx(tmp_path)
    (ctx.root / "control.plan").write_text("flag=on\n", encoding="utf-8")
    report_path = ctx.paths.reports_dir / "P0100.json"
    write_json(report_path, _report(ctx, artifact, probe_commands))
    ingestion = ingest_patchlet_report(ctx, patchlet=_patchlet(), attempt_id="P0100_attempt1", report_path=report_path)
    if not ingestion["accepted"]:
        return ingestion, None, None
    proof_obligations = _proof_obligations()
    probe_plan = _probe_plan()
    independent = run_independent_probe_rerun_gate(
        repo_root=ctx.root,
        workflow_root=ctx.paths.workflow_dir,
        attempt_id="P0100_attempt1",
        patchlet_id="P0100",
        proof_obligations=proof_obligations,
        probe_plan=probe_plan,
        integration_ref=None,
        execution_root=ctx.root,
        patchlet=_patchlet(),
        scope="patchlet",
    )
    coverage = evaluate_goal_coverage_gate(
        proof_obligations=proof_obligations,
        probe_plan=probe_plan,
        independent_probe_rerun_result=independent,
        patchlet_id="P0100",
        attempt_id="P0100_attempt1",
    )
    return ingestion, independent, coverage


def test_object_probe_commands_reach_independent_probe_rerun_after_normalization(tmp_path: Path):
    ingestion, independent, _ = _run_path(tmp_path, [_object_command()])

    assert ingestion["accepted"] is True
    assert independent["accepted"] is True
    assert independent["proven_obligation_ids"] == ["PO0100"]


def test_object_probe_commands_reach_goal_coverage_after_normalization(tmp_path: Path):
    ingestion, _, coverage = _run_path(tmp_path, [_object_command()])

    assert ingestion["accepted"] is True
    assert coverage["accepted"] is True
    assert coverage["accepted_for_patchlet_progress"] is True


def test_string_probe_commands_still_reach_downstream_gates(tmp_path: Path):
    ingestion, independent, coverage = _run_path(tmp_path, ["grep -qx 'flag=on' control.plan"])

    assert ingestion["accepted"] is True
    assert independent["accepted"] is True
    assert coverage["accepted"] is True


def test_malformed_object_probe_commands_do_not_reach_independent_probe(tmp_path: Path):
    ingestion, independent, coverage = _run_path(tmp_path, [{"phase": "baseline"}])

    assert ingestion["accepted"] is False
    assert independent is None
    assert coverage is None
