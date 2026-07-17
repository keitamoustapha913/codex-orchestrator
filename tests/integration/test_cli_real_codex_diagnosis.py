from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.run_records import append_run_record
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.state import sha256_file
from codex_orchestrator.target_repo import resolve_target_repo


def _seed_failed_attempt(ctx) -> str:
    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "stdout.txt").write_text("", encoding="utf-8")
    (run_dir / "stderr.txt").write_text("authentication failed: session expired\n", encoding="utf-8")
    (run_dir / "output.jsonl").write_text(json.dumps({"event": "error", "message": "authentication failed"}) + "\n", encoding="utf-8")
    (run_dir / "command.json").write_text(
        json.dumps({"exit_code": 1, "args": ["codex", "exec", "--json", "prompt.md"]}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prompt_artifact = ctx.paths.subprompts_dir / "0001_app.md"
    prompt_artifact.parent.mkdir(parents=True, exist_ok=True)
    prompt_artifact.write_text(
        "# Task Completion Handoff Contract\nCXOR_TASK_COMPLETION_HANDOFF_PATH\n",
        encoding="utf-8",
    )
    append_run_record(
        ctx,
        {
            "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
            "worker": "real_codex",
            "worker_mode": "real_codex",
            "patchlet_id": "P0001",
            "attempt_id": "P0001_attempt1",
            "execution_mode": "worktree",
            "status": "WORKER_FAILED",
            "success": False,
            "target_root": str(ctx.root),
            "execution_root": "/tmp/cxor-p0001-cli",
            "artifact_root": str(ctx.root),
            "paths": {
                "run_dir": ".codex-orchestrator/runs/P0001_attempt1",
                "stdout": ".codex-orchestrator/runs/P0001_attempt1/stdout.txt",
                "stderr": ".codex-orchestrator/runs/P0001_attempt1/stderr.txt",
                "command": ".codex-orchestrator/runs/P0001_attempt1/command.json",
                "output_jsonl": ".codex-orchestrator/runs/P0001_attempt1/output.jsonl",
                "diff": ".codex-orchestrator/runs/P0001_attempt1/diff.patch",
            },
            "worktree": {
                "enabled": True,
                "path": "/tmp/cxor-p0001-cli",
                "base_sha": "abc123",
                "cleanup_policy": "remove",
                "cleanup_status": "removed",
            },
            "worker_failure": {
                "type": "WorkerExecutionError",
                "message": "codex worker failed with exit_code=1",
                "exit_code": 1,
                "retryable": False,
                "blind_retry_allowed": False,
                "failure_category": "worker_exception",
            },
            "artifact_preservation": {
                "run_dir_exists": True,
                "stdout_exists": True,
                "stderr_exists": True,
                "command_exists": True,
                "output_jsonl_exists": True,
                "diff_exists": False,
            },
            "diff_validation": {
                "valid": None,
                "reason": "not_run_worker_failed_before_diff_validation",
            },
            "report_validation": {
                "valid": None,
                "reason": "not_run_worker_failed_before_report_validation",
            },
            "state_after_failure": "PATCHLET_EXECUTION_IN_PROGRESS",
        },
    )
    return "P0001_attempt1"


def _initialized_repo(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return ctx


def test_cli_diagnose_real_codex_writes_diagnosis_for_existing_failed_attempt(git_repo: Path):
    ctx = _initialized_repo(git_repo)
    attempt_id = _seed_failed_attempt(ctx)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codex_orchestrator",
            "diagnose-real-codex",
            "--repo",
            str(ctx.root),
            "--attempt",
            attempt_id,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    diagnosis_dir = ctx.paths.real_codex_diagnostics_dir
    assert (diagnosis_dir / f"{attempt_id}_diagnosis.json").exists()
    assert (diagnosis_dir / f"{attempt_id}_diagnosis.md").exists()


def test_cli_diagnose_real_codex_prints_primary_category_and_paths(git_repo: Path):
    ctx = _initialized_repo(git_repo)
    attempt_id = _seed_failed_attempt(ctx)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codex_orchestrator",
            "diagnose-real-codex",
            "--repo",
            str(ctx.root),
            "--attempt",
            attempt_id,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "auth_or_session_error" in result.stdout
    assert "diagnosis_json_path" in result.stdout
    assert "diagnosis_md_path" in result.stdout


def test_cli_diagnose_real_codex_refuses_unknown_attempt(git_repo: Path):
    ctx = _initialized_repo(git_repo)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codex_orchestrator",
            "diagnose-real-codex",
            "--repo",
            str(ctx.root),
            "--attempt",
            "P9999_attempt1",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "unknown real_codex attempt" in result.stderr


def test_cli_diagnose_real_codex_is_read_only_for_product_files(git_repo: Path):
    ctx = _initialized_repo(git_repo)
    attempt_id = _seed_failed_attempt(ctx)
    app_hash_before = sha256_file(ctx.root / "app.py")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codex_orchestrator",
            "diagnose-real-codex",
            "--repo",
            str(ctx.root),
            "--attempt",
            attempt_id,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert sha256_file(ctx.root / "app.py") == app_hash_before
