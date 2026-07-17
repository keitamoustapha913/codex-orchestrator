from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import read_json
import pytest

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "codex_orchestrator", *args]
    repo_root = Path(__file__).resolve().parents[2]
    env = {"PYTHONPATH": str(repo_root / "src")}
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def test_verify_group_passes_after_all_patchlets_complete_or_verified_no_change_needed(git_repo: Path):
    from codex_orchestrator.stages.verify_group import verify_group

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    app_hash_before = (git_repo / "app.py").read_text(encoding="utf-8")

    result = verify_group(ctx, transaction_group_id="TG001")

    groups = read_json(ctx.paths.transaction_groups)
    assert result["status"] == "PASSED"
    assert validate_json_file(ctx.paths.transaction_groups, "transaction_group.schema.json") == []
    assert groups["transaction_groups"][0]["transaction_group_id"] == "TG001"
    assert groups["transaction_groups"][0]["status"] == "PASSED"
    assert groups["transaction_groups"][0]["result"]["validated_patchlet_ids"] == ["P0001"]
    assert (git_repo / "app.py").read_text(encoding="utf-8") == app_hash_before


def test_verify_group_refuses_before_required_patchlets_complete(git_repo: Path):
    from codex_orchestrator.stages.verify_group import verify_group

    ctx = _ctx(git_repo)
    state_hash_before = ctx.paths.state.read_text(encoding="utf-8")
    app_hash_before = (git_repo / "app.py").read_text(encoding="utf-8")

    with pytest.raises(StagePreconditionError, match="verify-group.*TG001"):
        verify_group(ctx, transaction_group_id="TG001")

    assert ctx.paths.state.read_text(encoding="utf-8") == state_hash_before
    assert (git_repo / "app.py").read_text(encoding="utf-8") == app_hash_before


def test_verify_group_failed_patchlet_report_creates_failure_record(git_repo: Path):
    from codex_orchestrator.stages.verify_group import verify_group
    from codex_orchestrator.state import load_state

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    report_path = ctx.paths.reports_dir / "P0001.json"
    report = read_json(report_path)
    report["status"] = "FAILED_WITH_EVIDENCE"
    report["failed_probe_evidence"] = "group verifier consumed a failing report"
    report_path.write_text(__import__("json").dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_group(ctx, transaction_group_id="TG001")

    assert result["status"] == "FAILED"
    assert (ctx.paths.failures_dir / "F0001.json").exists()
    assert read_json(ctx.paths.failures_dir / "F0001.json")["source"] == "TRANSACTION_GROUP_VERIFICATION_FAILED"
    assert load_state(ctx).stage == "FAILURE_CLASSIFICATION_REQUIRED"


def test_verify_all_groups_updates_all_pending_groups(git_repo: Path):
    from codex_orchestrator.stages.verify_group import verify_all_groups

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")

    results = verify_all_groups(ctx)

    assert [result["transaction_group_id"] for result in results] == ["TG001"]
    assert results[0]["status"] == "PASSED"


def test_verify_group_is_read_only_for_product_runtime_files(git_repo: Path):
    from codex_orchestrator.stages.verify_group import verify_group

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    app_hash_before = ctx.root.joinpath("app.py").read_text(encoding="utf-8")

    verify_group(ctx, transaction_group_id="TG001")

    assert ctx.root.joinpath("app.py").read_text(encoding="utf-8") == app_hash_before


def test_cli_verify_group_outputs_group_result_and_artifact_path(git_repo: Path, tmp_path: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    result = _run_cli(["verify-group", "--repo", str(git_repo), "TG001"], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "TG001" in result.stdout
    assert "PASSED" in result.stdout
    assert str(ctx.paths.transaction_groups) in result.stdout


def test_cli_verify_group_refuses_incomplete_group_with_stable_precondition_error(git_repo: Path, tmp_path: Path):
    _ctx(git_repo)

    result = _run_cli(["verify-group", "--repo", str(git_repo), "TG001"], cwd=tmp_path)

    assert result.returncode == 2
    assert "precondition" in result.stderr.lower()
    assert "tg001" in result.stderr.lower()
    assert str(git_repo) in result.stderr
