from __future__ import annotations

from pathlib import Path

from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.target_repo import TargetRepoContext

from .base import Worker, WorkerResult, ensure_run_context


class ManualWorker(Worker):
    def run_patchlet(
        self,
        ctx: TargetRepoContext,
        patchlet: dict,
        *,
        run_dir: Path | None = None,
        run_ctx: PatchletRunContext | None = None,
    ) -> WorkerResult:
        run_ctx = ensure_run_context(ctx, patchlet=patchlet, run_dir=run_dir, run_ctx=run_ctx)
        report_path = run_ctx.reports_dir / f"{patchlet['patchlet_id']}.json"
        return WorkerResult(
            exit_code=0 if report_path.exists() else 1,
            stdout="manual worker expects pre-created report",
            stderr="" if report_path.exists() else f"missing report {report_path}",
            report_path=report_path if report_path.exists() else None,
        )
