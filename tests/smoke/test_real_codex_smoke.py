from __future__ import annotations

from pathlib import Path

import pytest

from codex_orchestrator.real_codex_smoke import real_codex_smoke_enabled, run_real_codex_smoke
from codex_orchestrator.target_repo import resolve_target_repo


@pytest.mark.real_codex
def test_real_codex_smoke_manual_opt_in(git_repo: Path, request: pytest.FixtureRequest):
    ctx = resolve_target_repo(repo=git_repo)
    result = run_real_codex_smoke(
        ctx,
        master=git_repo / "master_prompt.md",
        allow_real_codex=real_codex_smoke_enabled(request.config.getoption("--run-real-codex")),
    )
    assert result["worker_mode"] == "real_codex"
    assert Path(result["stdout_path"]).exists()
    assert Path(result["stderr_path"]).exists()
