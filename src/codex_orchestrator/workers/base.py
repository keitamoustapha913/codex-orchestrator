from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_orchestrator.target_repo import TargetRepoContext


@dataclass(frozen=True)
class WorkerResult:
    exit_code: int
    stdout: str
    stderr: str
    report_path: Path | None


class Worker:
    def run_patchlet(self, ctx: TargetRepoContext, patchlet: dict, *, run_dir: Path) -> WorkerResult:
        raise NotImplementedError
