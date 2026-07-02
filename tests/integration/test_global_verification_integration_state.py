from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.target_repo import resolve_target_repo


def _status(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _run_done_with_worktree(git_repo: Path, *, product_change: bool = False):
    ctx = resolve_target_repo(repo=git_repo)
    if product_change:
        mock_dir = git_repo / ".codex-orchestrator" / "mock"
        mock_dir.mkdir(parents=True, exist_ok=True)
        (mock_dir / "next_patchlet_result.json").write_text(
            '{"change_allowed_product": true, "status": "COMPLETE"}\n',
            encoding="utf-8",
        )
    result = run_auto(
        ctx,
        master=git_repo / "master_prompt.md",
        until="DONE",
        worker_mode="mock",
        use_worktree=True,
        max_iterations=50,
    )
    assert result.stage == "DONE"
    return ctx


def test_final_verification_references_integration_state(git_repo: Path):
    ctx = _run_done_with_worktree(git_repo)

    final = read_json(ctx.paths.final_verification_json)
    state = read_json(ctx.paths.integration_state)

    assert final["integration_ref"] == state["integration_ref"]
    assert final["integration_sha"] == state["integration_sha"]
    assert final["target_head_sha"] == state["target_head_sha"]


def test_done_requires_integration_state_consistency(git_repo: Path):
    ctx = _run_done_with_worktree(git_repo)

    state = read_json(ctx.paths.integration_state)
    final = read_json(ctx.paths.final_verification_json)

    assert final["status"] == "DONE"
    assert final["integration_sha"] == state["integration_sha"]


def test_done_requires_target_working_tree_clean_before_finalization(git_repo: Path):
    ctx = _run_done_with_worktree(git_repo)

    final = read_json(ctx.paths.final_verification_json)
    dirty_product_lines = [
        line for line in _status(git_repo).splitlines()
        if not line[3:].startswith(".codex-orchestrator/") and not line[3:].startswith(".artifacts/")
    ]
    assert final["target_working_tree_clean"] is True
    assert dirty_product_lines == []


def test_final_diff_from_target_head_to_integration_sha_exists(git_repo: Path):
    ctx = _run_done_with_worktree(git_repo)

    final = read_json(ctx.paths.final_verification_json)

    assert final["final_diff_path"] == ".codex-orchestrator/integration/final_diff.patch"
    assert ctx.paths.final_diff_path.exists()


def test_final_verification_uses_integration_sha_not_target_head_when_results_are_unapplied(git_repo: Path):
    ctx = _run_done_with_worktree(git_repo, product_change=True)

    final = read_json(ctx.paths.final_verification_json)

    assert final["integration_sha"] != final["target_head_sha"]
