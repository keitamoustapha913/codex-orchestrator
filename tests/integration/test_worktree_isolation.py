from __future__ import annotations

import json
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
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.state import load_state, sha256_file
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


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


def test_patchlet_worktree_valid_diff_advances_integration_without_dirtying_target(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}),
        encoding="utf-8",
    )
    app_hash_before = sha256_file(ctx.root / "app.py")

    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert result.patchlet_id == "P0001"
    assert result.status == "COMPLETE"
    assert sha256_file(ctx.root / "app.py") == app_hash_before
    state = read_json(ctx.paths.integration_state)
    integrated_app = subprocess.run(
        ["git", "-C", str(ctx.root), "show", f"{state['integration_sha']}:app.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout
    assert "# cxor mock allowed product change" in integrated_app


def test_worktree_run_records_worktree_path_base_sha_and_cleanup_status(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}),
        encoding="utf-8",
    )

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    manifest = read_json(ctx.paths.run_manifest)
    run = manifest["runs"][-1]
    assert run["execution_mode"] == "worktree"
    assert run["target_root"] == str(ctx.root)
    assert run["artifact_root"] == str(ctx.root)
    assert run["execution_root"] != str(ctx.root)
    assert run["worktree"]["enabled"] is True
    assert run["worktree"]["path"]
    assert run["worktree"]["base_sha"]
    assert run["worktree"]["cleanup_status"] == "removed"


def test_worktree_run_writes_reports_and_probes_to_target_artifact_root(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}),
        encoding="utf-8",
    )

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert (ctx.paths.reports_dir / "P0001.json").exists()
    assert (ctx.paths.probe_dir / "P0001" / "run_001" / "row_ledger.jsonl").exists()
    assert validate_json_file(ctx.paths.reports_dir / "P0001.json", "patchlet_report.schema.json") == []


def test_patchlet_worktree_unauthorized_diff_does_not_mutate_target_repo(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    other = ctx.root / "other.py"
    other.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ctx.root), "add", "other.py"], check=True)
    subprocess.run(["git", "-C", str(ctx.root), "commit", "-m", "add other"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"unauthorized_files": {"other.py": "value = 2\n"}, "status": "COMPLETE"}),
        encoding="utf-8",
    )
    app_hash_before = sha256_file(ctx.root / "app.py")
    other_hash_before = sha256_file(other)

    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert result.status == "FAILED_WITH_EVIDENCE"
    assert sha256_file(ctx.root / "app.py") == app_hash_before
    assert sha256_file(other) == other_hash_before
    assert load_state(ctx).stage == "FAILURE_CLASSIFICATION_REQUIRED"


def test_patchlet_worktree_unauthorized_diff_saves_failed_diff_artifact(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    other = ctx.root / "other.py"
    other.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ctx.root), "add", "other.py"], check=True)
    subprocess.run(["git", "-C", str(ctx.root), "commit", "-m", "add other"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"unauthorized_files": {"other.py": "value = 2\n"}, "status": "COMPLETE"}),
        encoding="utf-8",
    )

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    diff_path = ctx.paths.runs_dir / "P0001_attempt1" / "diff.patch"
    assert diff_path.exists()
    assert "other.py" in diff_path.read_text(encoding="utf-8")


def test_patchlet_worktree_unauthorized_diff_creates_failure_record(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    other = ctx.root / "other.py"
    other.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ctx.root), "add", "other.py"], check=True)
    subprocess.run(["git", "-C", str(ctx.root), "commit", "-m", "add other"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"unauthorized_files": {"other.py": "value = 2\n"}, "status": "COMPLETE"}),
        encoding="utf-8",
    )

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert (ctx.paths.failures_dir / "F0001.json").exists()
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert failure["source_id"] == "P0001"
    assert "other.py" in failure["observed_failure"]


def test_worktree_run_manifest_records_diff_validation_result(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}),
        encoding="utf-8",
    )

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    run = read_json(ctx.paths.run_manifest)["runs"][-1]
    assert run["diff_validation"]["valid"] is True
    assert run["diff_validation"]["changed_product_runtime_files"] == ["app.py"]
    assert run["diff_validation"]["unauthorized_files"] == []


def test_worktree_run_manifest_records_cleanup_status_for_success_and_failure(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}),
        encoding="utf-8",
    )

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    success_run = read_json(ctx.paths.run_manifest)["runs"][-1]
    assert success_run["worktree"]["cleanup_status"] == "removed"


def test_cli_run_next_use_worktree_valid_diff(git_repo: Path, tmp_path: Path):
    ctx = _compiled_ctx(git_repo)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}),
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[2]
    env = {"PYTHONPATH": str(repo_root / "src")}

    result = subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", "run-next", "--repo", str(git_repo), "--worker-mode", "mock", "--use-worktree"],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "P0001" in result.stdout


def test_cli_run_next_use_worktree_unauthorized_diff(git_repo: Path, tmp_path: Path):
    ctx = _compiled_ctx(git_repo)
    other = ctx.root / "other.py"
    other.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ctx.root), "add", "other.py"], check=True)
    subprocess.run(["git", "-C", str(ctx.root), "commit", "-m", "add other"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"unauthorized_files": {"other.py": "value = 2\n"}, "status": "COMPLETE"}),
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[2]
    env = {"PYTHONPATH": str(repo_root / "src")}

    result = subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", "run-next", "--repo", str(git_repo), "--worker-mode", "mock", "--use-worktree"],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert "FAILED_WITH_EVIDENCE" in result.stdout
