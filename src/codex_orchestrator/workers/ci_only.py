from __future__ import annotations

from pathlib import Path

from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.target_repo import TargetRepoContext

from .base import Worker, WorkerResult, ensure_run_context


class CiOnlyWorker(Worker):
    def run_patchlet(
        self,
        ctx: TargetRepoContext,
        patchlet: dict,
        *,
        run_dir: Path | None = None,
        run_ctx: PatchletRunContext | None = None,
    ) -> WorkerResult:
        ensure_run_context(ctx, patchlet=patchlet, run_dir=run_dir, run_ctx=run_ctx)
        return WorkerResult(exit_code=1, stdout="", stderr="ci_only worker does not edit or create patchlet reports", report_path=None)
