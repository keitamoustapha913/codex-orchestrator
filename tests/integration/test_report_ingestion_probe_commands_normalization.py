from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
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


def _object_command(**overrides: Any) -> dict[str, Any]:
    row = {
        "phase": "proof_of_fix",
        "command": "grep -qx 'flag=on' control.plan",
        "runs": "5/5",
        "expected_exit_code": 0,
    }
    row.update(overrides)
    return row


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


def _ingest(tmp_path: Path, probe_commands: list[Any]):
    ctx, artifact = _ctx(tmp_path)
    report_path = ctx.paths.reports_dir / "P0100.json"
    write_json(report_path, _report(ctx, artifact, probe_commands))
    result = ingest_patchlet_report(ctx, patchlet=_patchlet(), attempt_id="P0100_attempt1", report_path=report_path)
    return ctx, result


def _normalization_result(ctx):
    return read_json(ctx.paths.runs_dir / "P0100_attempt1/gates/probe_commands_normalization_result.json")


def test_object_shaped_probe_commands_are_normalized_to_strings(tmp_path: Path):
    ctx, result = _ingest(tmp_path, [_object_command()])

    report = read_json(ctx.paths.reports_dir / "P0100.json")
    assert result["accepted"] is True
    assert report["probe_commands"] == ["grep -qx 'flag=on' control.plan"]


def test_object_shaped_probe_commands_preserve_raw_metadata_in_gate_artifact(tmp_path: Path):
    ctx, _ = _ingest(tmp_path, [_object_command()])

    artifact = _normalization_result(ctx)
    assert artifact["raw_probe_command_items"][0]["raw_item"]["phase"] == "proof_of_fix"
    assert artifact["raw_probe_command_items"][0]["raw_item"]["command"] == "grep -qx 'flag=on' control.plan"


def test_object_shaped_probe_commands_preserve_phase_runs_and_expected_exit_code(tmp_path: Path):
    ctx, _ = _ingest(tmp_path, [_object_command(phase="baseline", runs="7/7", expected_exit_code=1)])

    item = _normalization_result(ctx)["raw_probe_command_items"][0]["raw_item"]
    assert item["phase"] == "baseline"
    assert item["runs"] == "7/7"
    assert item["expected_exit_code"] == 1


def test_malformed_probe_command_object_without_command_is_rejected(tmp_path: Path):
    ctx, result = _ingest(tmp_path, [{"phase": "baseline", "runs": "5/5", "expected_exit_code": 1}])

    assert result["accepted"] is False
    assert result["normalized_failure_signature"] == "patchlet_report_schema_violation"
    assert _normalization_result(ctx)["rejected_probe_command_items"][0]["reason"] == "missing_or_empty_command"


def test_malformed_probe_command_object_with_empty_command_is_rejected(tmp_path: Path):
    ctx, result = _ingest(tmp_path, [_object_command(command="   ")])

    assert result["accepted"] is False
    assert result["normalized_failure_signature"] == "patchlet_report_schema_violation"
    assert _normalization_result(ctx)["rejected_probe_command_items"][0]["reason"] == "missing_or_empty_command"


def test_existing_string_probe_commands_remain_unchanged(tmp_path: Path):
    ctx, result = _ingest(tmp_path, ["grep -qx 'flag=on' control.plan"])

    report = read_json(ctx.paths.reports_dir / "P0100.json")
    assert result["accepted"] is True
    assert report["probe_commands"] == ["grep -qx 'flag=on' control.plan"]


def test_mixed_string_and_object_probe_commands_normalize_safely(tmp_path: Path):
    ctx, result = _ingest(tmp_path, ["printf ok", _object_command(command="grep -qx 'flag=on' control.plan")])

    report = read_json(ctx.paths.reports_dir / "P0100.json")
    assert result["accepted"] is True
    assert report["probe_commands"] == ["printf ok", "grep -qx 'flag=on' control.plan"]


def test_probe_command_normalization_result_records_rejected_items(tmp_path: Path):
    ctx, _ = _ingest(tmp_path, [_object_command(), {"phase": "negative_control"}])

    artifact = _normalization_result(ctx)
    assert artifact["accepted"] is False
    assert artifact["raw_probe_command_items"][0]["accepted"] is True
    assert artifact["rejected_probe_command_items"][0]["raw_item_index"] == 1


def test_canonical_report_does_not_include_schema_blocking_probe_command_raw_fields(tmp_path: Path):
    ctx, _ = _ingest(tmp_path, [_object_command()])

    report = read_json(ctx.paths.reports_dir / "P0100.json")
    assert "probe_commands_raw" not in report
    assert "probe_command_metadata" not in report
