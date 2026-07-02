from __future__ import annotations

import sys

from codex_orchestrator.command_runner import command_available
from codex_orchestrator.version import __version__
from codex_orchestrator.target_repo import TargetRepoContext


def doctor(ctx: TargetRepoContext | None = None) -> dict:
    result = {
        "python_version": sys.version.split()[0],
        "orchestrator_version": __version__,
        "git_available": command_available("git"),
        "codex_available": command_available("codex"),
        "target_repo": None,
        "target_is_git_repo": None,
        "workflow_initialized": None,
    }
    if ctx is not None:
        result.update({
            "target_repo": str(ctx.root),
            "target_is_git_repo": ctx.is_git_repo,
            "workflow_initialized": ctx.paths.state.exists(),
        })
    return result
