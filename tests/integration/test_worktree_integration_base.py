from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import read_json

from codex_orchestrator.errors import WorkerPreconditionError
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.worktree import cleanup_patchlet_worktree, create_patchlet_worktree


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()


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


def test_worktree_manifest_records_integration_base_sha(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    run = read_json(ctx.paths.run_manifest)["runs"][-1]
    state = read_json(ctx.paths.integration_state)
    assert run["worktree"]["base_sha"] == state["integration_sha"]
    assert run["worktree"]["base_source"] == "integration_state"
    assert run["worktree"]["integration_ref"] == state["integration_ref"]


def test_patchlet_worktree_uses_integration_state_base_sha(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    integration_sha = read_json(ctx.paths.integration_state)["integration_sha"]
    (git_repo / "app.py").write_text("def main():\n    return 'new head'\n", encoding="utf-8")
    _git(git_repo, "add", "app.py")
    _git(git_repo, "commit", "-m", "advance target head")
    state = read_json(ctx.paths.integration_state)
    state["accepted_patchlets"] = ["P0001"]
    state["integration_sha"] = integration_sha
    write_json(ctx.paths.integration_state, state)

    worktree = create_patchlet_worktree(ctx, patchlet_id="P0001")
    try:
        assert worktree.base_sha == integration_sha
        assert _git(worktree.path, "rev-parse", "HEAD") == integration_sha
    finally:
        cleanup_patchlet_worktree(worktree)


def test_external_dirty_target_file_still_blocks_worktree_execution(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    (git_repo / "app.py").write_text("def main():\n    return 'dirty'\n", encoding="utf-8")

    with pytest.raises(WorkerPreconditionError, match="clean target repo"):
        create_patchlet_worktree(ctx, patchlet_id="P0001")


def test_artifact_dirs_do_not_block_worktree_execution(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    (git_repo / ".operator-runs" / "sample").mkdir(parents=True)
    (git_repo / ".operator-runs" / "sample" / "result.json").write_text("{}\n", encoding="utf-8")

    worktree = create_patchlet_worktree(ctx, patchlet_id="P0001")
    try:
        assert worktree.base_source == "integration_state"
    finally:
        cleanup_patchlet_worktree(worktree)


def test_missing_integration_state_is_recreated_or_reports_structured_error(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    ctx.paths.integration_state.unlink()

    worktree = create_patchlet_worktree(ctx, patchlet_id="P0001")
    try:
        assert ctx.paths.integration_state.exists()
        assert worktree.base_source == "integration_state"
    finally:
        cleanup_patchlet_worktree(worktree)
