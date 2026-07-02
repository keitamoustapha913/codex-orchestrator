from __future__ import annotations

from pathlib import Path

from codex_orchestrator.target_repo import TargetRepoContext

from .base import Worker, WorkerResult


class CiOnlyWorker(Worker):
    def run_patchlet(self, ctx: TargetRepoContext, patchlet: dict, *, run_dir: Path) -> WorkerResult:
        return WorkerResult(exit_code=1, stdout="", stderr="ci_only worker does not edit or create patchlet reports", report_path=None)
