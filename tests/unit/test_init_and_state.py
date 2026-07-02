from __future__ import annotations

from pathlib import Path

from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.state import load_state, save_state
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.state_validator import validate_state_file


def test_init_creates_target_artifacts_without_copying_source(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    result = init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    assert result.stage == "MASTER_PROMPT_SAVED"
    assert (git_repo / ".codex-orchestrator" / "state.json").exists()
    assert (git_repo / ".codex-orchestrator" / "run_manifest.json").exists()
    assert (git_repo / ".codex-orchestrator" / "config.toml").exists()
    assert (git_repo / ".codex-orchestrator" / "master_prompt.md").read_text(encoding="utf-8").startswith("Make app")
    assert (git_repo / ".artifacts" / "probes" / ".gitkeep").exists()
    assert not (git_repo / "src" / "codex_orchestrator").exists()
    assert not (git_repo / "tools" / "codex_orchestrator").exists()


def test_state_file_validates_after_init(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    errors = validate_state_file(ctx.paths.state)

    assert errors == []


def test_atomic_state_save_updates_stage(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    state = load_state(ctx)
    state.stage = "GOAL_SPEC_READY"
    save_state(ctx, state)

    assert load_state(ctx).stage == "GOAL_SPEC_READY"
    assert not (ctx.paths.state.with_suffix(".json.tmp")).exists()
