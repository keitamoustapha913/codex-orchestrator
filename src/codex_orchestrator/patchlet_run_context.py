from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_orchestrator.target_repo import TargetRepoContext


@dataclass(frozen=True)
class PatchletRunContext:
    target_root: Path
    execution_root: Path
    artifact_root: Path
    workflow_dir: Path
    probe_dir: Path
    reports_dir: Path
    runs_dir: Path
    run_dir: Path
    is_worktree: bool
    worktree_path: Path | None

    @property
    def attempt_scratch_dir(self) -> Path:
        return self.run_dir / "worker_scratch"

    @property
    def quarantine_dir(self) -> Path:
        return self.run_dir / "quarantined_scratch"

    def required_report_path(self, patchlet_id: str) -> Path:
        return self.reports_dir / f"{patchlet_id}.json"

    def required_probe_artifact_root(self, patchlet_id: str) -> Path:
        return self.probe_dir / patchlet_id


def build_patchlet_run_context(
    ctx: TargetRepoContext,
    *,
    patchlet: dict,
    run_id: str,
    execution_root: Path | None = None,
    artifact_root: Path | None = None,
    is_worktree: bool = False,
    worktree_path: Path | None = None,
) -> PatchletRunContext:
    del patchlet
    target_root = ctx.root
    artifact_root = (artifact_root or ctx.root).resolve()
    execution_root = (execution_root or ctx.root).resolve()
    return PatchletRunContext(
        target_root=target_root,
        execution_root=execution_root,
        artifact_root=artifact_root,
        workflow_dir=ctx.paths.workflow_dir,
        probe_dir=ctx.paths.probe_dir,
        reports_dir=ctx.paths.reports_dir,
        runs_dir=ctx.paths.runs_dir,
        run_dir=ctx.paths.runs_dir / run_id,
        is_worktree=is_worktree,
        worktree_path=worktree_path.resolve() if worktree_path is not None else None,
    )
