from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.stages.apply_repair import apply_repair
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.classify_failures import classify_failures
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.plan_repair import plan_repair
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.state import sha256_file
from codex_orchestrator.target_repo import resolve_target_repo


def run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "codex_orchestrator", *args]
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def setup_repair_plan_ready_repo(git_repo: Path) -> Path:
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet_index = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))
    patchlet_index["patchlets"][0]["required_allowed_product_change"] = True
    ctx.paths.patchlet_index.write_text(json.dumps(patchlet_index), encoding="utf-8")
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        '{"status":"COMPLETE"}',
        encoding="utf-8",
    )
    run_next_patchlet(ctx, worker_mode="mock")
    classify_failures(ctx)
    plan_repair(ctx)
    return git_repo


def setup_patchlet_regeneration_required_repo(git_repo: Path) -> Path:
    ctx = resolve_target_repo(repo=setup_repair_plan_ready_repo(git_repo))
    apply_repair(ctx)
    return git_repo


def setup_done_repo(git_repo: Path) -> Path:
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet_index = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))
    patchlet_index["patchlets"][0]["required_allowed_product_change"] = True
    ctx.paths.patchlet_index.write_text(json.dumps(patchlet_index), encoding="utf-8")
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        '{"status":"COMPLETE","consume_after_run":true}',
        encoding="utf-8",
    )
    result = run_auto(ctx, until="DONE", worker_mode="mock", max_iterations=50)
    assert result.stage == "DONE"
    return git_repo


def test_module_version_works_from_any_directory(tmp_path: Path):
    result = run_cli(["--version"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "codex-orchestrator" in result.stdout


def test_cli_init_and_status_with_explicit_repo(git_repo: Path, tmp_path: Path):
    init_result = run_cli(["init", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md")], cwd=tmp_path)
    assert init_result.returncode == 0, init_result.stderr
    assert "MASTER_PROMPT_SAVED" in init_result.stdout

    status_result = run_cli(["status", "--repo", str(git_repo)], cwd=tmp_path)
    assert status_result.returncode == 0, status_result.stderr
    assert "MASTER_PROMPT_SAVED" in status_result.stdout


def test_cli_auto_mock_until_done(git_repo: Path, tmp_path: Path):
    result = run_cli([
        "auto",
        "--repo", str(git_repo),
        "--master", str(git_repo / "master_prompt.md"),
        "--until", "DONE",
        "--worker-mode", "mock",
        "--max-iterations", "25",
    ], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout
    assert (git_repo / ".codex-orchestrator" / "final_verification.json").exists()


def test_cli_apply_repair_advances_to_patchlet_regeneration_required(git_repo: Path, tmp_path: Path):
    setup_repair_plan_ready_repo(git_repo)

    result = run_cli(["apply-repair", "--repo", str(git_repo)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "PATCHLET_REGENERATION_REQUIRED" in result.stdout
    assert (git_repo / ".codex-orchestrator" / "repair_plans" / "RP0001_application.json").exists()

    status_result = run_cli(["status", "--repo", str(git_repo)], cwd=tmp_path)
    assert status_result.returncode == 0, status_result.stderr
    assert "PATCHLET_REGENERATION_REQUIRED" in status_result.stdout


def test_cli_regenerate_patchlets_from_latest_repair_plan(git_repo: Path, tmp_path: Path):
    setup_patchlet_regeneration_required_repo(git_repo)

    result = run_cli(["regenerate-patchlets", "--repo", str(git_repo), "--from-repair-plan", "latest"], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "P0002" in result.stdout
    assert (git_repo / ".codex-orchestrator" / "subprompts" / "0002_repair.md").exists()

    status_result = run_cli(["status", "--repo", str(git_repo)], cwd=tmp_path)
    assert status_result.returncode == 0, status_result.stderr
    assert "PATCHLETS_READY" in status_result.stdout


def test_cli_apply_repair_is_idempotent(git_repo: Path, tmp_path: Path):
    setup_repair_plan_ready_repo(git_repo)

    first = run_cli(["apply-repair", "--repo", str(git_repo)], cwd=tmp_path)
    second = run_cli(["apply-repair", "--repo", str(git_repo)], cwd=tmp_path)

    applications = sorted((git_repo / ".codex-orchestrator" / "repair_plans").glob("RP0001_application*.json"))
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "PATCHLET_REGENERATION_REQUIRED" in first.stdout
    assert "PATCHLET_REGENERATION_REQUIRED" in second.stdout
    assert [path.name for path in applications] == ["RP0001_application.json"]


def test_cli_regenerate_patchlets_is_idempotent(git_repo: Path, tmp_path: Path):
    setup_patchlet_regeneration_required_repo(git_repo)

    first = run_cli(["regenerate-patchlets", "--repo", str(git_repo), "--from-repair-plan", "latest"], cwd=tmp_path)
    second = run_cli(["regenerate-patchlets", "--repo", str(git_repo), "--from-repair-plan", "latest"], cwd=tmp_path)

    patchlet_index = json.loads((git_repo / ".codex-orchestrator" / "patchlets" / "patchlet_index.json").read_text(encoding="utf-8"))
    repair_patchlets = [
        patchlet for patchlet in patchlet_index.get("patchlets", [])
        if patchlet.get("is_repair_patchlet") and patchlet.get("repair_plan_id") == "RP0001"
    ]
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "P0002" in first.stdout
    assert "P0002" in second.stdout
    assert [patchlet.get("patchlet_id") for patchlet in repair_patchlets] == ["P0002"]


def test_cli_auto_resume_after_done_is_idempotent(git_repo: Path, tmp_path: Path):
    setup_done_repo(git_repo)

    first = run_cli([
        "auto",
        "--repo", str(git_repo),
        "--resume",
        "--until", "DONE",
        "--worker-mode", "mock",
        "--max-iterations", "10",
    ], cwd=tmp_path)
    second = run_cli([
        "auto",
        "--repo", str(git_repo),
        "--resume",
        "--until", "DONE",
        "--worker-mode", "mock",
        "--max-iterations", "10",
    ], cwd=tmp_path)

    failures = sorted(path.name for path in (git_repo / ".codex-orchestrator" / "failures").glob("F*.json"))
    repair_plans = sorted(path.name for path in (git_repo / ".codex-orchestrator" / "repair_plans").glob("RP*.json"))
    applications = sorted(path.name for path in (git_repo / ".codex-orchestrator" / "repair_plans").glob("RP*_application*.json"))
    patchlet_index = json.loads((git_repo / ".codex-orchestrator" / "patchlets" / "patchlet_index.json").read_text(encoding="utf-8"))
    repair_patchlets = [
        patchlet for patchlet in patchlet_index.get("patchlets", [])
        if patchlet.get("is_repair_patchlet") and patchlet.get("repair_plan_id") == "RP0001"
    ]
    status_result = run_cli(["status", "--repo", str(git_repo)], cwd=tmp_path)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "DONE" in first.stdout
    assert "DONE" in second.stdout
    assert failures == ["F0001.json"]
    assert "RP0001.json" in repair_plans
    assert "RP0002.json" not in repair_plans
    assert applications == ["RP0001_application.json"]
    assert [patchlet.get("patchlet_id") for patchlet in repair_patchlets] == ["P0002"]
    assert status_result.returncode == 0, status_result.stderr
    assert "DONE" in status_result.stdout


def test_cli_apply_repair_after_done_is_terminal_noop(git_repo: Path, tmp_path: Path):
    setup_done_repo(git_repo)
    workflow = git_repo / ".codex-orchestrator"
    state_hash_before = sha256_file(workflow / "state.json")
    repair_plan_files_before = sorted(path.name for path in (workflow / "repair_plans").glob("*"))
    patchlet_index_hash_before = sha256_file(workflow / "patchlets" / "patchlet_index.json")
    final_hash_before = sha256_file(workflow / "final_verification.json")
    app_hash_before = sha256_file(git_repo / "app.py")

    result = run_cli(["apply-repair", "--repo", str(git_repo)], cwd=tmp_path)
    status_result = run_cli(["status", "--repo", str(git_repo)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "done" in result.stdout.lower() or "no-op" in result.stdout.lower() or "terminal" in result.stdout.lower()
    assert sha256_file(workflow / "state.json") == state_hash_before
    assert sorted(path.name for path in (workflow / "repair_plans").glob("*")) == repair_plan_files_before
    assert sha256_file(workflow / "patchlets" / "patchlet_index.json") == patchlet_index_hash_before
    assert sha256_file(workflow / "final_verification.json") == final_hash_before
    assert sha256_file(git_repo / "app.py") == app_hash_before
    assert status_result.returncode == 0, status_result.stderr
    assert "DONE" in status_result.stdout


def test_cli_regenerate_patchlets_after_done_is_terminal_noop(git_repo: Path, tmp_path: Path):
    setup_done_repo(git_repo)
    workflow = git_repo / ".codex-orchestrator"
    state_hash_before = sha256_file(workflow / "state.json")
    patchlet_index_hash_before = sha256_file(workflow / "patchlets" / "patchlet_index.json")
    final_hash_before = sha256_file(workflow / "final_verification.json")
    report_hash_before = sha256_file(workflow / "reports" / "P0002.json")
    app_hash_before = sha256_file(git_repo / "app.py")

    result = run_cli(["regenerate-patchlets", "--repo", str(git_repo), "--from-repair-plan", "latest"], cwd=tmp_path)
    status_result = run_cli(["status", "--repo", str(git_repo)], cwd=tmp_path)
    patchlet_index = json.loads((workflow / "patchlets" / "patchlet_index.json").read_text(encoding="utf-8"))
    repair_patchlets = [
        patchlet for patchlet in patchlet_index.get("patchlets", [])
        if patchlet.get("is_repair_patchlet") and patchlet.get("repair_plan_id") == "RP0001"
    ]

    assert result.returncode == 0, result.stderr
    assert "done" in result.stdout.lower() or "no-op" in result.stdout.lower() or "terminal" in result.stdout.lower()
    assert sha256_file(workflow / "state.json") == state_hash_before
    assert sha256_file(workflow / "patchlets" / "patchlet_index.json") == patchlet_index_hash_before
    assert sha256_file(workflow / "final_verification.json") == final_hash_before
    assert sha256_file(workflow / "reports" / "P0002.json") == report_hash_before
    assert sha256_file(git_repo / "app.py") == app_hash_before
    assert [patchlet.get("patchlet_id") for patchlet in repair_patchlets] == ["P0002"]
    assert status_result.returncode == 0, status_result.stderr
    assert "DONE" in status_result.stdout


def test_cli_apply_repair_missing_repair_plan_exits_nonzero_with_stable_message(git_repo: Path, tmp_path: Path):
    repo = setup_repair_plan_ready_repo(git_repo)
    workflow = repo / ".codex-orchestrator"
    (workflow / "repair_plans" / "RP0001.json").unlink()
    state_hash_before = sha256_file(workflow / "state.json")
    app_hash_before = sha256_file(repo / "app.py")

    result = run_cli(["apply-repair", "--repo", str(repo)], cwd=tmp_path)

    assert result.returncode == 2
    assert "precondition" in result.stderr.lower()
    assert "missing repair plan" in result.stderr.lower()
    assert "repair_plan_ready" in result.stderr.lower()
    assert str(repo) in result.stderr
    assert sha256_file(workflow / "state.json") == state_hash_before
    assert sha256_file(repo / "app.py") == app_hash_before
    assert not (workflow / "repair_plans" / "RP0001_application.json").exists()


def test_cli_regenerate_patchlets_missing_application_exits_nonzero_with_stable_message(git_repo: Path, tmp_path: Path):
    repo = setup_repair_plan_ready_repo(git_repo)
    workflow = repo / ".codex-orchestrator"
    state_hash_before = sha256_file(workflow / "state.json")
    app_hash_before = sha256_file(repo / "app.py")

    result = run_cli(["regenerate-patchlets", "--repo", str(repo), "--from-repair-plan", "latest"], cwd=tmp_path)

    assert result.returncode == 2
    assert "precondition" in result.stderr.lower()
    assert "missing repair application" in result.stderr.lower()
    assert "repair_plan_ready" in result.stderr.lower()
    assert str(repo) in result.stderr
    assert sha256_file(workflow / "state.json") == state_hash_before
    assert sha256_file(repo / "app.py") == app_hash_before
    assert not (workflow / "subprompts" / "0002_repair.md").exists()
