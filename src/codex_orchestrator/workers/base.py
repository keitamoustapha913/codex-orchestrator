from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_orchestrator.patchlet_run_context import PatchletRunContext, build_patchlet_run_context
from codex_orchestrator.target_repo import TargetRepoContext


@dataclass(frozen=True)
class WorkerResult:
    exit_code: int
    stdout: str
    stderr: str
    report_path: Path | None


class Worker:
    def run_patchlet(
        self,
        ctx: TargetRepoContext,
        patchlet: dict,
        *,
        run_dir: Path | None = None,
        run_ctx: PatchletRunContext | None = None,
    ) -> WorkerResult:
        raise NotImplementedError


def ensure_run_context(
    ctx: TargetRepoContext,
    *,
    patchlet: dict,
    run_dir: Path | None,
    run_ctx: PatchletRunContext | None,
) -> PatchletRunContext:
    if run_ctx is not None:
        return run_ctx
    if run_dir is None:
        raise ValueError("Worker requires either run_ctx or run_dir")
    return build_patchlet_run_context(
        ctx,
        patchlet=patchlet,
        run_id=run_dir.name,
        execution_root=ctx.root,
        artifact_root=ctx.root,
        is_worktree=False,
        worktree_path=None,
    )
