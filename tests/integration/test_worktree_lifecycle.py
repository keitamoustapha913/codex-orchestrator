from __future__ import annotations

from pathlib import Path

import pytest

from codex_orchestrator.errors import WorkerPreconditionError
from codex_orchestrator.target_repo import resolve_target_repo


def test_worktree_lifecycle_creates_worktree_from_clean_repo(git_repo: Path):
    from codex_orchestrator.worktree import create_patchlet_worktree

    ctx = resolve_target_repo(repo=git_repo)

    worktree = create_patchlet_worktree(ctx, patchlet_id="P0001")

    assert worktree.patchlet_id == "P0001"
    assert worktree.target_root == git_repo
    assert worktree.path.exists()
    assert (worktree.path / ".git").exists()
    assert worktree.base_sha


def test_worktree_lifecycle_refuses_dirty_target_repo(git_repo: Path):
    from codex_orchestrator.worktree import create_patchlet_worktree

    ctx = resolve_target_repo(repo=git_repo)
    (git_repo / "app.py").write_text('print("dirty")\n', encoding="utf-8")

    with pytest.raises(WorkerPreconditionError, match="clean target repo"):
        create_patchlet_worktree(ctx, patchlet_id="P0001")


def test_worktree_lifecycle_refuses_non_git_repo(tmp_path: Path):
    from codex_orchestrator.worktree import create_patchlet_worktree

    repo = tmp_path / "non-git"
    repo.mkdir()
    ctx = resolve_target_repo(repo=repo, allow_non_git=True, repo_exact=True)

    with pytest.raises(WorkerPreconditionError, match="git repo"):
        create_patchlet_worktree(ctx, patchlet_id="P0001")


def test_worktree_lifecycle_cleanup_removes_created_worktree_only(git_repo: Path, tmp_path: Path):
    from codex_orchestrator.worktree import cleanup_patchlet_worktree, create_patchlet_worktree

    ctx = resolve_target_repo(repo=git_repo)
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    worktree = create_patchlet_worktree(ctx, patchlet_id="P0001")
    cleanup_patchlet_worktree(worktree)

    assert not worktree.path.exists()
    assert sentinel.exists()


def test_worktree_lifecycle_records_base_sha_and_patchlet_id(git_repo: Path):
    from codex_orchestrator.git_guard import repo_head
    from codex_orchestrator.worktree import create_patchlet_worktree

    ctx = resolve_target_repo(repo=git_repo)

    worktree = create_patchlet_worktree(ctx, patchlet_id="P0001")

    assert worktree.patchlet_id == "P0001"
    assert worktree.base_sha == repo_head(git_repo)
    assert worktree.cleanup_policy == "remove"


def test_worktree_lifecycle_does_not_create_workflow_artifacts_in_orchestrator_source_repo(git_repo: Path):
    from codex_orchestrator.worktree import create_patchlet_worktree

    ctx = resolve_target_repo(repo=git_repo)
    source_repo = Path(__file__).resolve().parents[2]

    worktree = create_patchlet_worktree(ctx, patchlet_id="P0001")

    assert source_repo not in worktree.path.parents
    assert worktree.path.parent != source_repo
