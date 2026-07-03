from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from conftest import read_json

from codex_orchestrator.errors import WorkerExecutionError
from codex_orchestrator.real_codex_smoke import _smoke_result
from codex_orchestrator.real_codex_operator_runbook import CommandCapture, run_real_codex_smoke_runbook
from codex_orchestrator.real_codex_smoke_runbook_export import export_real_codex_smoke_runbook
from codex_orchestrator.real_codex_smoke_runbook_listing import list_real_codex_smoke_runbooks
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.integration_artifact_validator import validate_integration_artifacts
from codex_orchestrator.workers.base import WorkerResult
from codex_orchestrator.workers.mock import MockWorker


class TargetSideEffectWorker:
    def __init__(self, *, pycache: bool = False, unknown_file: bool = False):
        self.pycache = pycache
        self.unknown_file = unknown_file
        self.mock = MockWorker()

    def run_patchlet(self, ctx, patchlet, *, run_dir=None, run_ctx=None):
        result = self.mock.run_patchlet(ctx, patchlet, run_dir=run_dir, run_ctx=run_ctx)
        if self.pycache:
            cache_dir = ctx.root / "__pycache__"
            cache_dir.mkdir(exist_ok=True)
            (cache_dir / "app.cpython-310.pyc").write_bytes(b"cache")
        if self.unknown_file:
            (ctx.root / "tmp.txt").write_text("unknown", encoding="utf-8")
        return WorkerResult(exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr, report_path=result.report_path)


def _compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _git_status(repo: Path) -> str:
    return subprocess.run(["git", "status", "--short"], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


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


def _attempt_consistency(valid: bool) -> dict:
    return {
        "valid": valid,
        "run_dir_attempt_id": "P0004_attempt1",
        "manifest_attempt_id": "P0004_attempt1" if valid else "P0003_attempt1",
        "diagnosis_attempt_id": "P0004_attempt1" if valid else "P0003_attempt1",
        "stdout_attempt_id": "P0004_attempt1",
        "stderr_attempt_id": "P0004_attempt1",
        "output_jsonl_attempt_id": "P0004_attempt1",
        "progress_attempt_id": "P0004_attempt1",
        "mismatches": [] if valid else ["run_dir_attempt_id != manifest_attempt_id"],
    }


def test_fake_p0004_pycache_leak_is_detected_and_recorded(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)
    monkeypatch.setattr(run_patchlet_stage, "worker_for_mode", lambda _mode: TargetSideEffectWorker(pycache=True))

    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "target_hygiene_gate_result.json")
    assert gate["cache_artifacts_detected"][0]["path"] == "__pycache__/app.cpython-310.pyc"
    assert gate["cache_artifacts_removed"][0]["path"] == "__pycache__/app.cpython-310.pyc"


def test_fake_p0004_pycache_leak_does_not_dirty_product_file(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)
    monkeypatch.setattr(run_patchlet_stage, "worker_for_mode", lambda _mode: TargetSideEffectWorker(pycache=True))

    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    assert subprocess.run(["git", "diff", "--", "app.py"], cwd=git_repo, text=True, stdout=subprocess.PIPE, check=True).stdout == ""


def test_fake_p0004_pycache_leak_checkpoint_validates_after_hygiene(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)
    monkeypatch.setattr(run_patchlet_stage, "worker_for_mode", lambda _mode: TargetSideEffectWorker(pycache=True))

    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    checkpoint = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")
    assert checkpoint["target_working_tree_clean_after_checkpoint"] is True
    assert validate_integration_artifacts(git_repo)["valid"] is True


def test_fake_p0004_pycache_leak_manifest_entry_exists(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)
    monkeypatch.setattr(run_patchlet_stage, "worker_for_mode", lambda _mode: TargetSideEffectWorker(pycache=True))

    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    entry = read_json(ctx.paths.run_manifest)["runs"][0]
    assert entry["attempt_id"] == "P0001_attempt1"
    assert entry["lifecycle_status"] == "ATTEMPT_ACCEPTED"


def test_fake_p0004_pycache_leak_runbook_attempt_consistency_valid(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)
    monkeypatch.setattr(run_patchlet_stage, "worker_for_mode", lambda _mode: TargetSideEffectWorker(pycache=True))

    run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)
    result = _smoke_result(ctx, master=git_repo / "master_prompt.md", until="DONE", max_iterations=1, outcome="success", state_stage="DONE")

    assert result["attempt_consistency"]["valid"] is True


def test_fake_p0004_unknown_dirty_path_fails_precisely(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)
    monkeypatch.setattr(run_patchlet_stage, "worker_for_mode", lambda _mode: TargetSideEffectWorker(unknown_file=True))

    with pytest.raises(WorkerExecutionError, match="target hygiene gate failed"):
        run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "target_hygiene_gate_result.json")
    assert gate["unknown_dirty_paths"] == ["tmp.txt"]


def test_fake_p0004_unknown_dirty_path_is_not_deleted(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)
    monkeypatch.setattr(run_patchlet_stage, "worker_for_mode", lambda _mode: TargetSideEffectWorker(unknown_file=True))

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    assert (git_repo / "tmp.txt").exists()


def test_fake_p0004_integration_validation_failure_has_manifest_entry(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as run_patchlet_stage

    ctx = _compiled_ctx(git_repo)
    monkeypatch.setattr(
        run_patchlet_stage,
        "_write_integration_validation_result",
        lambda _ctx: {
            "schema_version": "1.0",
            "kind": "integration_artifact_validation",
            "valid": False,
            "errors": [{"path": ".codex-orchestrator/integration/checkpoints/P0001.json", "message": "forced"}],
            "warnings": [],
        },
    )

    with pytest.raises(WorkerExecutionError, match="integration artifact validation failed"):
        run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = read_json(ctx.paths.run_manifest)["runs"][0]
    assert entry["attempt_id"] == "P0001_attempt1"
    assert entry["failed_stage"] == "INTEGRATION_ARTIFACTS_VALIDATION_FAILED"


def test_fake_p0004_runbook_uses_p0004_attempt_not_p0003(tmp_path: Path):
    payload = {
        "outcome": "safe_failure",
        "attempt_consistency": _attempt_consistency(True),
        "diagnosis_primary_category": "integration_artifact_validation_error",
    }
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T21-00-00",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps(payload)),
    )

    saved = read_json(Path(result["operator_run_dir"]) / "result.json")
    assert saved["attempt_consistency"]["run_dir_attempt_id"] == "P0004_attempt1"
    assert saved["attempt_consistency"]["manifest_attempt_id"] == "P0004_attempt1"


def test_fake_p0004_failure_diagnosis_not_network_error(tmp_path: Path):
    payload = {
        "outcome": "safe_failure",
        "attempt_consistency": _attempt_consistency(True),
        "diagnosis_primary_category": "integration_artifact_validation_error",
    }
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T21-00-01",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps(payload)),
    )

    saved = read_json(Path(result["operator_run_dir"]) / "result.json")
    assert saved["diagnosis_primary_category"] == "integration_artifact_validation_error"


def test_legacy_p0004_p0003_bundle_mismatch_is_detected(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T21-00-02",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps({"outcome": "safe_failure", "attempt_consistency": _attempt_consistency(False)})),
    )

    saved = read_json(Path(result["operator_run_dir"]) / "result.json")
    assert saved["attempt_consistency"]["valid"] is False


def test_legacy_p0004_p0003_bundle_mismatch_is_listed(tmp_path: Path):
    run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T21-00-03",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps({"outcome": "safe_failure", "attempt_consistency": _attempt_consistency(False)})),
    )

    listing = list_real_codex_smoke_runbooks(tmp_path / "runs" / "real-codex-smoke")
    assert listing["bundles"][0]["attempt_consistency_valid"] is False


def test_legacy_p0004_p0003_bundle_mismatch_is_exported_with_warning_or_error(tmp_path: Path):
    result = run_real_codex_smoke_runbook(
        repo_root=tmp_path,
        operator_root=tmp_path / "runs",
        timestamp="2026-07-03T21-00-04",
        dry_run=False,
        run_real_codex=True,
        runner=_fake_runner(json.dumps({"outcome": "safe_failure", "attempt_consistency": _attempt_consistency(False)})),
    )

    export = export_real_codex_smoke_runbook(Path(result["operator_run_dir"]))
    manifest = read_json(Path(export["manifest_path"]))

    assert manifest["attempt_consistency"]["valid"] is False
