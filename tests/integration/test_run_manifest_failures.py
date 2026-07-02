from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from conftest import read_json

from codex_orchestrator.errors import WorkerExecutionError
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.state import load_state, sha256_file
from codex_orchestrator.target_repo import resolve_target_repo


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


def _write_fake_codex(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _last_patchlet_run(ctx) -> dict:
    manifest = read_json(ctx.paths.run_manifest)
    patchlet_runs = [run for run in manifest["runs"] if run.get("patchlet_id") == "P0001"]
    assert len(patchlet_runs) == 1
    return patchlet_runs[0]


def test_failed_worker_attempt_appends_run_manifest_entry(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
print("worker failed", file=sys.stderr)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError, match="exit_code=17"):
        run_next_patchlet(ctx, worker_mode="real_codex")

    run = _last_patchlet_run(ctx)
    assert run["attempt_id"] == "P0001_attempt1"
    assert run["status"] == "WORKER_FAILED"
    assert run["success"] is False
    assert run["worker_mode"] == "real_codex"
    assert load_state(ctx).stage != "DONE"


def test_failed_worker_run_manifest_records_stdout_stderr_command_output_paths(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
print("stdout-marker")
print("stderr-marker", file=sys.stderr)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    run = _last_patchlet_run(ctx)
    paths = run["paths"]
    assert Path(ctx.root / paths["run_dir"]).exists()
    assert Path(ctx.root / paths["stdout"]).exists()
    assert Path(ctx.root / paths["stderr"]).exists()
    assert Path(ctx.root / paths["command"]).exists()
    assert Path(ctx.root / paths["output_jsonl"]).exists()
    assert Path(ctx.root / paths["stdout"]).read_text(encoding="utf-8").strip() == "stdout-marker"
    assert "stderr-marker" in Path(ctx.root / paths["stderr"]).read_text(encoding="utf-8")


def test_failed_worker_run_manifest_records_exception_type_message_and_exit_code(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
print("boom", file=sys.stderr)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    run = _last_patchlet_run(ctx)
    failure = run["worker_failure"]
    assert failure["type"] == "WorkerExecutionError"
    assert "exit_code=17" in failure["message"]
    assert failure["exit_code"] == 17
    assert failure["failure_category"] == "worker_exception"


def test_failed_worker_run_manifest_marks_blind_retry_not_allowed(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    run = _last_patchlet_run(ctx)
    assert run["worker_failure"]["retryable"] is False
    assert run["worker_failure"]["blind_retry_allowed"] is False


def test_failed_worker_run_manifest_records_not_run_diff_and_report_validation(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    app_hash_before = sha256_file(ctx.root / "app.py")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    run = _last_patchlet_run(ctx)
    assert run["diff_validation"]["valid"] is None
    assert run["diff_validation"]["reason"] == "not_run_worker_failed_before_diff_validation"
    assert run["report_validation"]["valid"] is None
    assert run["report_validation"]["reason"] == "not_run_worker_failed_before_report_validation"
    assert sha256_file(ctx.root / "app.py") == app_hash_before


def test_failed_worktree_worker_run_manifest_records_execution_and_artifact_roots(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    run = _last_patchlet_run(ctx)
    assert run["execution_mode"] == "worktree"
    assert run["target_root"] == str(ctx.root)
    assert run["artifact_root"] == str(ctx.root)
    assert run["execution_root"] != str(ctx.root)


def test_failed_worktree_worker_run_manifest_records_worktree_metadata_and_cleanup_status(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    run = _last_patchlet_run(ctx)
    assert run["worktree"]["enabled"] is True
    assert run["worktree"]["path"]
    assert run["worktree"]["base_sha"]
    assert run["worktree"]["cleanup_policy"] == "remove"
    assert run["worktree"]["cleanup_status"] == "removed"


def test_failed_worktree_worker_preserves_target_product_files(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    app_hash_before = sha256_file(ctx.root / "app.py")
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    assert sha256_file(ctx.root / "app.py") == app_hash_before
    assert load_state(ctx).stage != "DONE"


def test_failed_worktree_worker_artifacts_are_written_to_target_root_not_worktree(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
print("worker failed", file=sys.stderr)
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex", use_worktree=True)

    run = _last_patchlet_run(ctx)
    paths = run["paths"]
    assert Path(ctx.root / paths["stdout"]).exists()
    assert Path(ctx.root / paths["stderr"]).exists()
    assert Path(ctx.root / paths["command"]).exists()
    assert Path(ctx.root / paths["output_jsonl"]).exists()
