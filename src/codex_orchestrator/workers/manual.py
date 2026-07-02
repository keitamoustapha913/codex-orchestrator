from __future__ import annotations

from pathlib import Path

from codex_orchestrator.target_repo import TargetRepoContext

from .base import Worker, WorkerResult


class ManualWorker(Worker):
    def run_patchlet(self, ctx: TargetRepoContext, patchlet: dict, *, run_dir: Path) -> WorkerResult:
        report_path = ctx.paths.reports_dir / f"{patchlet['patchlet_id']}.json"
        return WorkerResult(
            exit_code=0 if report_path.exists() else 1,
            stdout="manual worker expects pre-created report",
            stderr="" if report_path.exists() else f"missing report {report_path}",
            report_path=report_path if report_path.exists() else None,
        )
