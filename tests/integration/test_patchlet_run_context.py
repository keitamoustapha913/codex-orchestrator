from __future__ import annotations

import shutil
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
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.workers.mock import MockWorker


def _compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet_index = read_json(ctx.paths.patchlet_index)
    return ctx, patchlet_index["patchlets"][0]


def test_patchlet_run_context_default_uses_target_repo_for_execution_and_artifacts(git_repo: Path):
    from codex_orchestrator.stages.run_patchlet import build_patchlet_run_context

    ctx, patchlet = _compiled_ctx(git_repo)
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")

    assert run_ctx.target_root == ctx.root
    assert run_ctx.execution_root == ctx.root
    assert run_ctx.artifact_root == ctx.root
    assert run_ctx.workflow_dir == ctx.paths.workflow_dir
    assert run_ctx.probe_dir == ctx.paths.probe_dir
    assert run_ctx.reports_dir == ctx.paths.reports_dir
    assert run_ctx.runs_dir == ctx.paths.runs_dir
    assert run_ctx.is_worktree is False
    assert run_ctx.worktree_path is None


def test_mock_worker_writes_reports_and_probes_to_artifact_root(git_repo: Path, tmp_path: Path):
    from codex_orchestrator.stages.run_patchlet import PatchletRunContext

    ctx, patchlet = _compiled_ctx(git_repo)
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)
    run_ctx = PatchletRunContext(
        target_root=ctx.root,
        execution_root=execution_root,
        artifact_root=ctx.root,
        workflow_dir=ctx.paths.workflow_dir,
        probe_dir=ctx.paths.probe_dir,
        reports_dir=ctx.paths.reports_dir,
        runs_dir=ctx.paths.runs_dir,
        run_dir=ctx.paths.runs_dir / "P0001_attempt1",
        is_worktree=False,
        worktree_path=None,
    )

    result = MockWorker().run_patchlet(ctx, patchlet, run_ctx=run_ctx)

    assert result.report_path == ctx.paths.reports_dir / "P0001.json"
    assert (ctx.paths.reports_dir / "P0001.json").exists()
    assert (ctx.paths.probe_dir / "P0001" / "probe.py").exists()
    assert (ctx.paths.probe_dir / "P0001" / "run_001" / "row_ledger.jsonl").exists()
    assert not (execution_root / ".codex-orchestrator" / "reports" / "P0001.json").exists()
    assert not (execution_root / ".artifacts" / "probes" / "P0001" / "run_001" / "row_ledger.jsonl").exists()


def test_mock_worker_uses_execution_root_for_product_runtime_changes(git_repo: Path, tmp_path: Path):
    from codex_orchestrator.stages.run_patchlet import PatchletRunContext

    ctx, patchlet = _compiled_ctx(git_repo)
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text('{"change_allowed_product": true}', encoding="utf-8")
    run_ctx = PatchletRunContext(
        target_root=ctx.root,
        execution_root=execution_root,
        artifact_root=ctx.root,
        workflow_dir=ctx.paths.workflow_dir,
        probe_dir=ctx.paths.probe_dir,
        reports_dir=ctx.paths.reports_dir,
        runs_dir=ctx.paths.runs_dir,
        run_dir=ctx.paths.runs_dir / "P0001_attempt1",
        is_worktree=False,
        worktree_path=None,
    )

    MockWorker().run_patchlet(ctx, patchlet, run_ctx=run_ctx)

    assert "# cxor mock allowed product change" in (execution_root / "app.py").read_text(encoding="utf-8")
    assert "# cxor mock allowed product change" not in (ctx.root / "app.py").read_text(encoding="utf-8")


def test_run_next_default_behavior_preserves_existing_artifact_paths(git_repo: Path):
    ctx, _patchlet = _compiled_ctx(git_repo)

    result = run_next_patchlet(ctx, worker_mode="mock")

    assert result.patchlet_id == "P0001"
    assert (ctx.paths.reports_dir / "P0001.json").exists()
    assert (ctx.paths.probe_dir / "P0001" / "run_001" / "row_ledger.jsonl").exists()
    assert validate_json_file(ctx.paths.reports_dir / "P0001.json", "patchlet_report.schema.json") == []


def test_run_next_default_behavior_keeps_existing_full_mock_flow_green(git_repo: Path):
    ctx, _patchlet = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    assert load_state(ctx).stage == "PATCHLET_EXECUTION_COMPLETE"
