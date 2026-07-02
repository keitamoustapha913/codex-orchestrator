from __future__ import annotations

import os
from pathlib import Path

import pytest

from codex_orchestrator.target_repo import TargetRepoError, resolve_target_repo


def test_explicit_repo_resolves_git_root_from_subdir(git_repo: Path):
    subdir = git_repo / "pkg" / "module"
    subdir.mkdir(parents=True)

    ctx = resolve_target_repo(repo=subdir)

    assert ctx.root == git_repo.resolve()
    assert ctx.workflow_dir == git_repo / ".codex-orchestrator"
    assert ctx.probe_dir == git_repo / ".artifacts" / "probes"
    assert ctx.is_git_repo is True


def test_current_working_directory_resolves_git_root(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    nested = git_repo / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)

    ctx = resolve_target_repo(repo=None)

    assert ctx.root == git_repo.resolve()


def test_non_git_repo_rejected_without_flag(tmp_path: Path):
    non_git = tmp_path / "plain"
    non_git.mkdir()

    with pytest.raises(TargetRepoError, match="No target repository found|not a Git repository"):
        resolve_target_repo(repo=non_git)


def test_non_git_repo_allowed_with_flag(tmp_path: Path):
    non_git = tmp_path / "plain"
    non_git.mkdir()

    ctx = resolve_target_repo(repo=non_git, allow_non_git=True)

    assert ctx.root == non_git.resolve()
    assert ctx.is_git_repo is False


def test_self_target_guard_blocks_orchestrator_like_repo(tmp_path: Path):
    repo = tmp_path / "codex-orchestrator"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "codex-orchestrator"\n', encoding="utf-8")
    (repo / "src" / "codex_orchestrator").mkdir(parents=True)

    with pytest.raises(TargetRepoError, match="appears to be the orchestrator source repo"):
        resolve_target_repo(repo=repo, allow_non_git=True)

    ctx = resolve_target_repo(repo=repo, allow_non_git=True, allow_self_target=True)
    assert ctx.root == repo.resolve()
