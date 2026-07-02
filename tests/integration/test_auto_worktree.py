from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.state import sha256_file
from codex_orchestrator.target_repo import resolve_target_repo


def _ctx(git_repo: Path):
    return resolve_target_repo(repo=git_repo)


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "codex_orchestrator", *args]
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _compiled_ctx(git_repo: Path):
    ctx = _ctx(git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def test_run_auto_accepts_use_worktree_false_and_preserves_existing_direct_flow(git_repo: Path):
    ctx = _ctx(git_repo)

    result = run_auto(
        ctx,
        master=git_repo / "master_prompt.md",
        until="DONE",
        worker_mode="mock",
        use_worktree=False,
        max_iterations=50,
    )

    manifest = read_json(ctx.paths.run_manifest)
    patchlet_runs = [run for run in manifest["runs"] if run.get("patchlet_id") == "P0001"]

    assert result.stage == "DONE"
    assert patchlet_runs
    assert all(run.get("execution_mode") == "direct" for run in patchlet_runs)
    assert all(run.get("worktree", {}).get("enabled") is False for run in patchlet_runs)


def test_run_auto_use_worktree_executes_pending_patchlet_with_worktree_metadata(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    result = run_auto(
        ctx,
        resume=True,
        until="PATCHLET_EXECUTION_COMPLETE",
        worker_mode="mock",
        use_worktree=True,
        max_iterations=25,
    )

    manifest = read_json(ctx.paths.run_manifest)
    patchlet_runs = [run for run in manifest["runs"] if run.get("patchlet_id") == "P0001"]

    assert result.stage == "PATCHLET_EXECUTION_COMPLETE"
    assert patchlet_runs
    assert patchlet_runs[-1]["execution_mode"] == "worktree"
    assert patchlet_runs[-1]["worktree"]["enabled"] is True
    assert patchlet_runs[-1]["worktree"]["cleanup_status"] == "removed"


def test_run_auto_use_worktree_reaches_done_in_mock_mode(git_repo: Path):
    ctx = _ctx(git_repo)

    result = run_auto(
        ctx,
        master=git_repo / "master_prompt.md",
        until="DONE",
        worker_mode="mock",
        use_worktree=True,
        max_iterations=150,
    )

    final = read_json(ctx.paths.final_verification_json)

    assert result.stage == "DONE"
    assert final["status"] == "DONE"


def test_run_auto_use_worktree_writes_reports_and_probes_to_target_artifact_root(git_repo: Path):
    ctx = _ctx(git_repo)

    run_auto(
        ctx,
        master=git_repo / "master_prompt.md",
        until="DONE",
        worker_mode="mock",
        use_worktree=True,
        max_iterations=150,
    )

    manifest = read_json(ctx.paths.run_manifest)
    patchlet_runs = [run for run in manifest["runs"] if run.get("patchlet_id") == "P0001"]

    assert (ctx.paths.reports_dir / "P0001.json").exists()
    assert (ctx.paths.probe_dir / "P0001" / "run_001" / "row_ledger.jsonl").exists()
    assert patchlet_runs
    assert patchlet_runs[-1]["artifact_root"] == str(ctx.root)


def test_run_auto_use_worktree_validates_transaction_group_and_global_verification(git_repo: Path):
    ctx = _ctx(git_repo)

    run_auto(
        ctx,
        master=git_repo / "master_prompt.md",
        until="DONE",
        worker_mode="mock",
        use_worktree=True,
        max_iterations=150,
    )

    transaction_groups = read_json(ctx.paths.transaction_groups)
    final = read_json(ctx.paths.final_verification_json)

    assert transaction_groups["transaction_groups"][0]["transaction_group_id"] == "TG001"
    assert transaction_groups["transaction_groups"][0]["status"] == "PASSED"
    assert final["status"] == "DONE"
    assert final["transaction_group_results"][0]["transaction_group_id"] == "TG001"
    assert final["transaction_group_results"][0]["status"] == "PASSED"


def test_run_auto_use_worktree_unauthorized_diff_preserves_target_product_files(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    other = ctx.root / "other.py"
    other.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ctx.root), "add", "other.py"], check=True)
    subprocess.run(
        ["git", "-C", str(ctx.root), "commit", "-m", "add other"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"unauthorized_files": {"other.py": "value = 2\n"}, "status": "COMPLETE"}),
        encoding="utf-8",
    )
    app_hash_before = sha256_file(ctx.root / "app.py")
    other_hash_before = sha256_file(other)

    result = run_auto(
        ctx,
        resume=True,
        until="FAILURE_CLASSIFICATION_REQUIRED",
        worker_mode="mock",
        use_worktree=True,
        max_iterations=25,
    )

    assert result.stage == "FAILURE_CLASSIFICATION_REQUIRED"
    assert sha256_file(ctx.root / "app.py") == app_hash_before
    assert sha256_file(other) == other_hash_before


def test_run_auto_use_worktree_unauthorized_diff_creates_failure_record_and_diff_artifact(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    other = ctx.root / "other.py"
    other.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ctx.root), "add", "other.py"], check=True)
    subprocess.run(
        ["git", "-C", str(ctx.root), "commit", "-m", "add other"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"unauthorized_files": {"other.py": "value = 2\n"}, "status": "COMPLETE"}),
        encoding="utf-8",
    )

    run_auto(
        ctx,
        resume=True,
        until="FAILURE_CLASSIFICATION_REQUIRED",
        worker_mode="mock",
        use_worktree=True,
        max_iterations=25,
    )

    diff_path = ctx.paths.runs_dir / "P0001_attempt1" / "diff.patch"
    assert (ctx.paths.failures_dir / "F0001.json").exists()
    assert diff_path.exists()
    assert "other.py" in diff_path.read_text(encoding="utf-8")


def test_run_auto_use_worktree_unauthorized_diff_can_continue_repair_loop_to_done(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    other = ctx.root / "other.py"
    other.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ctx.root), "add", "other.py"], check=True)
    subprocess.run(
        ["git", "-C", str(ctx.root), "commit", "-m", "add other"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({
            "unauthorized_files": {"other.py": "value = 2\n"},
            "status": "COMPLETE",
            "consume_after_run": True,
        }),
        encoding="utf-8",
    )
    app_hash_before = sha256_file(ctx.root / "app.py")
    other_hash_before = sha256_file(other)

    result = run_auto(
        ctx,
        resume=True,
        until="DONE",
        worker_mode="mock",
        use_worktree=True,
        max_iterations=100,
    )

    final = read_json(ctx.paths.final_verification_json)
    assert result.stage == "DONE"
    assert final["status"] == "DONE"
    assert (ctx.paths.failures_dir / "F0001.json").exists()
    assert (ctx.paths.repair_plans_dir / "RP0001.json").exists()
    assert (ctx.paths.repair_plans_dir / "RP0001_application.json").exists()
    assert (ctx.paths.reports_dir / "P0002.json").exists()
    assert sha256_file(ctx.root / "app.py") == app_hash_before
    assert sha256_file(other) == other_hash_before


def test_cli_auto_use_worktree_reaches_done_in_mock_mode(git_repo: Path, tmp_path: Path):
    result = _run_cli([
        "auto",
        "--repo", str(git_repo),
        "--master", str(git_repo / "master_prompt.md"),
        "--until", "DONE",
        "--worker-mode", "mock",
        "--use-worktree",
        "--max-iterations", "150",
    ], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout
    assert str(git_repo) in result.stdout


def test_cli_auto_use_worktree_records_worktree_metadata(git_repo: Path, tmp_path: Path):
    result = _run_cli([
        "auto",
        "--repo", str(git_repo),
        "--master", str(git_repo / "master_prompt.md"),
        "--until", "DONE",
        "--worker-mode", "mock",
        "--use-worktree",
        "--max-iterations", "150",
    ], cwd=tmp_path)

    ctx = _ctx(git_repo)
    manifest = read_json(ctx.paths.run_manifest)
    patchlet_runs = [run for run in manifest["runs"] if run.get("patchlet_id") == "P0001"]

    assert result.returncode == 0, result.stderr
    assert patchlet_runs
    assert patchlet_runs[-1]["execution_mode"] == "worktree"
    assert patchlet_runs[-1]["worktree"]["enabled"] is True


def test_cli_auto_use_worktree_refuses_dirty_repo(git_repo: Path, tmp_path: Path):
    (git_repo / "app.py").write_text("def main():\n    return 'dirty'\n", encoding="utf-8")
    app_hash_before = sha256_file(git_repo / "app.py")

    result = _run_cli([
        "auto",
        "--repo", str(git_repo),
        "--master", str(git_repo / "master_prompt.md"),
        "--until", "DONE",
        "--worker-mode", "mock",
        "--use-worktree",
        "--max-iterations", "150",
    ], cwd=tmp_path)

    assert result.returncode != 0
    assert "clean target repo" in result.stderr.lower() or "dirty" in result.stderr.lower() or "worktree" in result.stderr.lower()
    assert sha256_file(git_repo / "app.py") == app_hash_before


def test_cli_auto_resume_use_worktree_after_done_is_terminal_noop_or_done(git_repo: Path, tmp_path: Path):
    first = _run_cli([
        "auto",
        "--repo", str(git_repo),
        "--master", str(git_repo / "master_prompt.md"),
        "--until", "DONE",
        "--worker-mode", "mock",
        "--use-worktree",
        "--max-iterations", "150",
    ], cwd=tmp_path)
    ctx = _ctx(git_repo)
    state_hash_before = sha256_file(ctx.paths.state)

    second = _run_cli([
        "auto",
        "--repo", str(git_repo),
        "--resume",
        "--until", "DONE",
        "--worker-mode", "mock",
        "--use-worktree",
        "--max-iterations", "20",
    ], cwd=tmp_path)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "DONE" in second.stdout
    assert sha256_file(ctx.paths.state) == state_hash_before


def test_cli_auto_use_worktree_with_ci_only_is_rejected_or_explicit_read_only(git_repo: Path, tmp_path: Path):
    result = _run_cli([
        "auto",
        "--repo", str(git_repo),
        "--resume",
        "--until", "DONE",
        "--worker-mode", "ci_only",
        "--use-worktree",
        "--max-iterations", "10",
    ], cwd=tmp_path)

    assert result.returncode != 0
    assert "ci_only" in result.stderr.lower() or "read-only" in result.stderr.lower() or "use-worktree" in result.stderr.lower()


def test_run_auto_accepts_use_worktree_true_parameter_without_breaking_initialization(git_repo: Path):
    ctx = _ctx(git_repo)

    result = run_auto(
        ctx,
        master=git_repo / "master_prompt.md",
        until="MASTER_PROMPT_SAVED",
        worker_mode="mock",
        use_worktree=True,
        max_iterations=5,
    )

    assert result.stage == "MASTER_PROMPT_SAVED"
    assert ctx.paths.master_prompt.exists()
    assert ctx.paths.state.exists()


def test_run_auto_default_does_not_use_worktree_metadata(git_repo: Path):
    ctx = _ctx(git_repo)

    result = run_auto(
        ctx,
        master=git_repo / "master_prompt.md",
        until="DONE",
        worker_mode="mock",
        max_iterations=50,
    )

    manifest = read_json(ctx.paths.run_manifest)
    patchlet_runs = [run for run in manifest["runs"] if run.get("patchlet_id") == "P0001"]

    assert result.stage == "DONE"
    assert patchlet_runs
    assert all(run.get("execution_mode") == "direct" for run in patchlet_runs)
    assert all(run.get("worktree", {}).get("enabled") is False for run in patchlet_runs)
