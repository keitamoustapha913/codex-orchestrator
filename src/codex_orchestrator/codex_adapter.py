from __future__ import annotations

from codex_orchestrator.workers.base import Worker
from codex_orchestrator.workers.ci_only import CiOnlyWorker
from codex_orchestrator.workers.codex_exec import CodexExecWorker
from codex_orchestrator.workers.manual import ManualWorker
from codex_orchestrator.workers.mock import MockWorker


def worker_for_mode(mode: str) -> Worker:
    if mode == "mock":
        return MockWorker()
    if mode == "real_codex":
        return CodexExecWorker()
    if mode == "manual":
        return ManualWorker()
    if mode == "ci_only":
        return CiOnlyWorker()
    raise ValueError(f"Unknown worker mode: {mode}")
