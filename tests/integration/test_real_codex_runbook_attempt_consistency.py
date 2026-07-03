from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.real_codex_operator_runbook import CommandCapture, run_real_codex_smoke_runbook
from codex_orchestrator.real_codex_smoke import _smoke_result
from codex_orchestrator.real_codex_smoke_runbook_export import export_real_codex_smoke_runbook
from codex_orchestrator.real_codex_smoke_runbook_listing import list_real_codex_smoke_runbooks
from codex_orchestrator.run_records import init_run_manifest
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.real_codex_smoke_runbook_validator import validate_real_codex_smoke_runbook


def _init_ctx(repo: Path):
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "app.py").write_text("def main():\n    return 'ok'\n", encoding="utf-8")
    (repo / "master_prompt.md").write_text("Make app return ok and prove it.\n", encoding="utf-8")
    ctx = resolve_target_repo(repo=repo, allow_non_git=True)
    init_workflow(ctx, master=repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return ctx


def _write_attempt_artifacts(ctx, attempt_id: str) -> Path:
    run_dir = ctx.paths.runs_dir / attempt_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run_dir / "command.json",
        {
            "timeout_seconds": 600,
            "selected_model": "gpt-5.4-mini",
            "selected_reasoning": "medium",
            "timed_out": False,
        },
    )
    for name in ["stdout.txt", "stderr.txt", "output.jsonl", "progress.jsonl"]:
        (run_dir / name).write_text("", encoding="utf-8")
    return run_dir


def _write_manifest(ctx, attempt_id: str, patchlet_id: str = "P0004") -> None:
    manifest = init_run_manifest(ctx)
    manifest["runs"].append(
        {
            "run_id": "R0001",
            "attempt_id": attempt_id,
            "patchlet_id": patchlet_id,
            "worker_mode": "real_codex",
            "status": "VERIFIED_NO_CHANGE_NEEDED",
            "report_valid": True,
            "paths": {"run_dir": f".codex-orchestrator/runs/{attempt_id}"},
        }
    )
    write_json(ctx.paths.run_manifest, manifest)


def _fake_runner(explicit_stdout: str):
    def runner(args: list[str], cwd: Path, env: dict[str, str]) -> CommandCapture:
        if args[:2] == ["git", "status"]:
            return CommandCapture(exit_code=0, stdout="", stderr="")
        if args[:2] == ["codex", "--version"]:
            return CommandCapture(exit_code=0, stdout="codex-cli 0.142.4\n", stderr="")
        if "--run-real-codex" in args:
            return CommandCapture(exit_code=0, stdout=explicit_stdout, stderr="")
        return CommandCapture(exit_code=0, stdout="s\n1 skipped in 0.01s\n", stderr="")

    return runner


def _consistency(valid: bool = True) -> dict:
    return {
        "valid": valid,
        "run_dir_attempt_id": "P0004_attempt1",
        "manifest_attempt_id": "P0004_attempt1" if valid else "P0003_attempt1",
        "diagnosis_attempt_id": "P0004_attempt1" if valid else "P0003_attempt1",
        "stdout_attempt_id": "P0004_attempt1",
        "stderr_attempt_id": "P0004_attempt1",
        "output_jsonl_attempt_id": "P0004_attempt1",
        "progress_attempt_id": "P0004_attempt1",
        "mismatches": [] if valid else ["run_dir_attempt_id != manifest_attempt_id", "run_dir_attempt_id != diagnosis_attempt_id"],
    }


def test_runbook_result_attempt_consistency_valid_for_matching_attempt(tmp_path: Path):
    ctx = _init_ctx(tmp_path / "target")
    _write_attempt_artifacts(ctx, "P0004_attempt1")
    _write_manifest(ctx, "P0004_attempt1")

    result = _smoke_result(ctx, master=ctx.root / "master_prompt.md", until="DONE", max_iterations=1, outcome="success", state_stage="DONE")

    assert result["attempt_consistency"]["valid"] is True
    assert result["run_manifest_entry"]["attempt_id"] == "P0004_attempt1"


def test_runbook_detects_p0004_run_dir_with_p0003_manifest_entry(tmp_path: Path):
    ctx = _init_ctx(tmp_path / "target")
    _write_attempt_artifacts(ctx, "P0004_attempt1")
    _write_manifest(ctx, "P0003_attempt1", patchlet_id="P0003")

    result = _smoke_result(
        ctx,
        master=ctx.root / "master_prompt.md",
        until="DONE",
        max_iterations=1,
        outcome="safe_failure",
        state_stage="PATCHLET_EXECUTION_IN_PROGRESS",
        error_type="WorkerExecutionError",
        error_message="integration artifact validation failed",
    )

    assert result["attempt_consistency"]["valid"] is False
    assert "run_dir_attempt_id != manifest_attempt_id" in result["attempt_consistency"]["mismatches"]
    assert result["diagnosis_primary_category"] == "runbook_attempt_evidence_mismatch"


def test_runbook_does_not_use_stale_manifest_entry_for_latest_run_dir(tmp_path: Path):
    ctx = _init_ctx(tmp_path / "target")
    _write_attempt_artifacts(ctx, "P0004_attempt1")
    _write_manifest(ctx, "P0003_attempt1", patchlet_id="P0003")

    result = _smoke_result(ctx, master=ctx.root / "master_prompt.md", until="DONE", max_iterations=1, outcome="success", state_stage="DONE")

    assert result["run_manifest_entry"] is None
    assert result["attempt_consistency"]["manifest_attempt_id"] == "P0003_attempt1"


def test_runbook_synthesizes_incomplete_current_attempt_when_manifest_entry_missing(tmp_path: Path):
    ctx = _init_ctx(tmp_path / "target")
    _write_attempt_artifacts(ctx, "P0004_attempt1")
    init_run_manifest(ctx)

    result = _smoke_result(ctx, master=ctx.root / "master_prompt.md", until="DONE", max_iterations=1, outcome="safe_failure", state_stage="FAILED")

    assert result["run_manifest_entry"] is None
    assert result["attempt_consistency"]["run_dir_attempt_id"] == "P0004_attempt1"
    assert result["attempt_consistency"]["valid"] is False


def test_runbook_result_records_attempt_mismatch(tmp_path: Path):
    payload = {
        "outcome": "safe_failure",
        "attempt_consistency": _consistency(valid=False),
    }
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T20-00-00",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps(payload)),
    )

    saved = read_json(Path(result["operator_run_dir"]) / "result.json")
    assert saved["attempt_consistency"]["valid"] is False
    assert "run_dir_attempt_id != manifest_attempt_id" in saved["attempt_consistency"]["mismatches"]


def test_validate_real_codex_smoke_runbook_warns_or_errors_on_attempt_mismatch(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T20-00-01",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps({"outcome": "safe_failure", "attempt_consistency": _consistency(valid=False)})),
    )

    validation = validate_real_codex_smoke_runbook(Path(result["operator_run_dir"]))

    assert any("attempt consistency mismatch" in warning["message"] for warning in validation["warnings"])


def test_list_real_codex_smoke_runbooks_surfaces_attempt_mismatch(tmp_path: Path):
    run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T20-00-02",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps({"outcome": "safe_failure", "attempt_consistency": _consistency(valid=False)})),
    )

    listing = list_real_codex_smoke_runbooks(tmp_path / "runs" / "real-codex-smoke")

    assert listing["bundles"][0]["attempt_consistency_valid"] is False
    assert "run_dir_attempt_id != manifest_attempt_id" in listing["bundles"][0]["attempt_consistency_mismatches"]


def test_export_manifest_includes_attempt_consistency(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T20-00-03",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps({"outcome": "success", "attempt_consistency": _consistency(valid=True)})),
    )

    export = export_real_codex_smoke_runbook(Path(result["operator_run_dir"]))
    manifest = read_json(Path(export["manifest_path"]))

    assert manifest["attempt_consistency"]["valid"] is True


def test_new_successful_bundle_has_attempt_consistency_valid_true(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T20-00-04",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps({"outcome": "success", "attempt_consistency": _consistency(valid=True)})),
    )

    saved = read_json(Path(result["operator_run_dir"]) / "result.json")
    validation = validate_real_codex_smoke_runbook(Path(result["operator_run_dir"]))

    assert saved["attempt_consistency"]["valid"] is True
    assert validation["valid"] is True
