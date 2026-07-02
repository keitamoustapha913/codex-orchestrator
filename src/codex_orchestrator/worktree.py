from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from codex_orchestrator.errors import WorkerPreconditionError
from codex_orchestrator.git_guard import repo_head
from codex_orchestrator.integration_state import ensure_integration_state
from codex_orchestrator.target_repo import TargetRepoContext


VOLATILE_PREFIXES = (".codex-orchestrator/", ".artifacts/", ".operator-runs/")


@dataclass(frozen=True)
class WorktreeContext:
    patchlet_id: str
    target_root: Path
    path: Path
    base_sha: str
    base_source: str
    integration_ref: str | None
    cleanup_policy: str
    cleanup_status: str | None = None


def _status_lines(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise WorkerPreconditionError(f"Unable to inspect git status for target repo: {repo_root}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def _tracked_path_from_status_line(line: str) -> str:
    path = line[3:]
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path


def assert_clean_for_worktree(ctx: TargetRepoContext) -> None:
    if not ctx.is_git_repo or ctx.git_root is None:
        raise WorkerPreconditionError(f"Worktree execution requires a git repo target: {ctx.root}")
    dirty_paths = []
    for line in _status_lines(ctx.root):
        path = _tracked_path_from_status_line(line)
        if any(path.startswith(prefix) for prefix in VOLATILE_PREFIXES):
            continue
        dirty_paths.append(path)
    if dirty_paths:
        raise WorkerPreconditionError(
            f"Worktree execution requires a clean target repo; dirty paths: {', '.join(sorted(dirty_paths))}"
        )


def create_patchlet_worktree(ctx: TargetRepoContext, *, patchlet_id: str) -> WorktreeContext:
    assert_clean_for_worktree(ctx)
    integration_state = ensure_integration_state(ctx)
    base_sha = integration_state.get("integration_sha") or repo_head(ctx.root)
    if not base_sha:
        raise WorkerPreconditionError(f"Unable to resolve base SHA for target repo: {ctx.root}")
    root = Path(tempfile.mkdtemp(prefix=f"cxor-{patchlet_id.lower()}-", dir="/tmp")).resolve()
    subprocess.run(
        ["git", "-C", str(ctx.root), "worktree", "add", "--detach", str(root), base_sha],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return WorktreeContext(
        patchlet_id=patchlet_id,
        target_root=ctx.root,
        path=root,
        base_sha=base_sha,
        base_source="integration_state",
        integration_ref=integration_state.get("integration_ref"),
        cleanup_policy="remove",
        cleanup_status=None,
    )


def cleanup_patchlet_worktree(worktree: WorktreeContext) -> WorktreeContext:
    path = worktree.path.resolve()
    subprocess.run(
        ["git", "-C", str(worktree.target_root), "worktree", "remove", "--force", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if path.exists():
        shutil.rmtree(path)
    return WorktreeContext(
        patchlet_id=worktree.patchlet_id,
        target_root=worktree.target_root,
        path=worktree.path,
        base_sha=worktree.base_sha,
        base_source=worktree.base_source,
        integration_ref=worktree.integration_ref,
        cleanup_policy=worktree.cleanup_policy,
        cleanup_status="removed",
    )
