from __future__ import annotations

from pathlib import Path

from codex_orchestrator.patchlet_run_context import build_patchlet_run_context
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.worktree import cleanup_patchlet_worktree, create_patchlet_worktree


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return ctx


def _patchlet() -> dict:
    return {
        "patchlet_id": "P0001",
        "allowed_product_runtime_file": "app.py",
    }


def test_build_worker_capsule_paths_are_under_run_dir(git_repo: Path):
    from codex_orchestrator.worker_capsule import build_worker_capsule

    ctx = _ctx(git_repo)
    patchlet = _patchlet()
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")

    capsule = build_worker_capsule(run_ctx, patchlet)

    assert capsule.run_dir == ctx.paths.runs_dir / "P0001_attempt1"
    assert capsule.worker_memory_dir == capsule.run_dir / "worker_memory"
    assert capsule.worker_stage_dir == capsule.run_dir / "worker_stage"
    assert capsule.worker_hooks_dir == capsule.run_dir / "worker_hooks"
    assert capsule.gates_dir == capsule.run_dir / "gates"
    assert capsule.diagnostics_dir == capsule.run_dir / "diagnostics"
    assert capsule.manifest_path == capsule.run_dir / "worker_capsule.json"


def test_worker_capsule_paths_are_under_target_artifact_root_not_worktree(git_repo: Path):
    from codex_orchestrator.worker_capsule import build_worker_capsule

    ctx = _ctx(git_repo)
    worktree_ctx = create_patchlet_worktree(ctx, patchlet_id="P0001")
    try:
        patchlet = _patchlet()
        run_ctx = build_patchlet_run_context(
            ctx,
            patchlet=patchlet,
            run_id="P0001_attempt1",
            execution_root=worktree_ctx.path,
            artifact_root=ctx.root,
            is_worktree=True,
            worktree_path=worktree_ctx.path,
        )

        capsule = build_worker_capsule(run_ctx, patchlet)

        assert capsule.run_dir.is_relative_to(ctx.root)
        assert not capsule.run_dir.is_relative_to(worktree_ctx.path)
        assert capsule.manifest_path.is_relative_to(ctx.root)
    finally:
        cleanup_patchlet_worktree(worktree_ctx)


def test_worker_capsule_schema_validates_minimum_capsule_manifest(git_repo: Path):
    from codex_orchestrator.worker_capsule import build_worker_capsule, write_worker_capsule_manifest

    ctx = _ctx(git_repo)
    patchlet = _patchlet()
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")

    capsule = build_worker_capsule(run_ctx, patchlet)
    write_worker_capsule_manifest(ctx, capsule)

    assert validate_json_file(capsule.manifest_path, "worker_capsule.schema.json") == []


def test_worker_capsule_direct_mode_uses_existing_run_dir(git_repo: Path):
    from codex_orchestrator.worker_capsule import build_worker_capsule

    ctx = _ctx(git_repo)
    patchlet = _patchlet()
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")

    capsule = build_worker_capsule(run_ctx, patchlet)

    assert capsule.run_dir == run_ctx.run_dir
    assert capsule.manifest_path.parent == run_ctx.run_dir


def test_worker_capsule_worktree_mode_keeps_capsule_under_target_run_dir(git_repo: Path):
    from codex_orchestrator.worker_capsule import build_worker_capsule

    ctx = _ctx(git_repo)
    worktree_ctx = create_patchlet_worktree(ctx, patchlet_id="P0001")
    try:
        patchlet = _patchlet()
        run_ctx = build_patchlet_run_context(
            ctx,
            patchlet=patchlet,
            run_id="P0001_attempt1",
            execution_root=worktree_ctx.path,
            artifact_root=ctx.root,
            is_worktree=True,
            worktree_path=worktree_ctx.path,
        )

        capsule = build_worker_capsule(run_ctx, patchlet)

        assert capsule.run_dir == ctx.paths.runs_dir / "P0001_attempt1"
        assert capsule.manifest_path.parent == ctx.paths.runs_dir / "P0001_attempt1"
        assert not str(capsule.run_dir).startswith(str(worktree_ctx.path))
    finally:
        cleanup_patchlet_worktree(worktree_ctx)
