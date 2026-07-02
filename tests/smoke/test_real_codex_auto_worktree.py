from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_orchestrator.real_codex_smoke import (
    real_codex_smoke_enabled,
    run_real_codex_auto_worktree_smoke,
)
from codex_orchestrator.target_repo import resolve_target_repo


@pytest.mark.real_codex
def test_real_codex_auto_worktree_manual_opt_in(
    git_repo: Path,
    request: pytest.FixtureRequest,
):
    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_auto_worktree_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=real_codex_smoke_enabled(
            request.config.getoption("--run-real-codex")
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    assert result["worker_mode"] == "real_codex"
    assert result["use_worktree"] is True
