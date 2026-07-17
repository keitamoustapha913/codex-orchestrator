from __future__ import annotations

from pathlib import Path
import hashlib
import subprocess
from typing import Any

from codex_orchestrator.validators.schema_validator import validate_json, validate_json_file

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
        "schema_version": "2.0",
        "kind": "worker_patchlet_report",
        "patchlet_id": "P0100",
        "status": "COMPLETE",
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
    }


def test_worker_patchlet_report_v2_schema_keeps_canonical_probe_commands_as_strings(tmp_path: Path):
    ctx, artifact = _ctx(tmp_path)
    report = _report(ctx, artifact, ["grep -qx 'flag=on' control.plan"])

    assert validate_json(report, "worker_patchlet_report_v2.schema.json") == []


def test_worker_patchlet_report_v2_schema_rejects_raw_probe_command_objects_in_canonical_probe_commands(tmp_path: Path):
    ctx, artifact = _ctx(tmp_path)
    report = _report(ctx, artifact, [_object_command()])

    errors = validate_json(report, "worker_patchlet_report_v2.schema.json")
    assert errors


def test_probe_command_metadata_is_a_gate_artifact_not_canonical_report_payload(tmp_path: Path):
    ctx, artifact = _ctx(tmp_path)
    report_path = ctx.paths.reports_dir / "P0100.json"
    write_json(report_path, _report(ctx, artifact, [_object_command()]))

    ingest_patchlet_report(ctx, patchlet={"patchlet_id": "P0100"}, attempt_id="P0100_attempt1", report_path=report_path)

    report = read_json(ctx.paths.reports_dir / "P0100.json")
    gate_artifact = ctx.paths.runs_dir / "P0100_attempt1/gates/probe_commands_normalization_result.json"
    assert gate_artifact.exists()
    assert "probe_commands_raw" not in report
    assert "probe_command_metadata" not in report


def test_probe_command_normalization_artifact_schema_validates(tmp_path: Path):
    ctx, artifact = _ctx(tmp_path)
    report_path = ctx.paths.reports_dir / "P0100.json"
    write_json(report_path, _report(ctx, artifact, [_object_command()]))

    ingest_patchlet_report(ctx, patchlet={"patchlet_id": "P0100"}, attempt_id="P0100_attempt1", report_path=report_path)

    assert validate_json_file(
        ctx.paths.runs_dir / "P0100_attempt1/gates/probe_commands_normalization_result.json",
        "probe_commands_normalization_result.schema.json",
    ) == []
