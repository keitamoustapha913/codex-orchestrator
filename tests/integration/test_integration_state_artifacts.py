from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()


def _compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _run_accepted_mock_patchlet(ctx) -> None:
    scenario_dir = ctx.paths.workflow_dir / "mock"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "next_patchlet_result.json").write_text(
        json.dumps({"status": "COMPLETE", "change_allowed_product": True}) + "\n",
        encoding="utf-8",
    )
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)


def test_integration_state_initialized_from_target_head(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    state = read_json(ctx.paths.integration_state)

    assert state["target_head_sha"] == _head(git_repo)
    assert state["integration_sha"] == state["target_head_sha"]


def test_integration_state_uses_hidden_cxor_ref(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    state = read_json(ctx.paths.integration_state)

    assert state["integration_ref"].startswith("refs/cxor/runs/")
    assert state["integration_ref"].endswith("/integration")


def test_integration_state_records_finalize_only_apply_mode(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    assert read_json(ctx.paths.integration_state)["apply_mode"] == "finalize_only"


def test_integration_state_records_target_product_dirty_not_allowed(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    assert read_json(ctx.paths.integration_state)["target_product_dirty_allowed"] is False


def test_accepted_patchlet_records_accepted_change(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_mock_patchlet(ctx)

    entries = [
        json.loads(line)
        for line in ctx.paths.accepted_changes.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries) == 1
    assert entries[0]["kind"] == "accepted_change"
    assert entries[0]["patchlet_id"] == "P0001"


def test_integration_state_records_current_integration_sha(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_mock_patchlet(ctx)

    state = read_json(ctx.paths.integration_state)
    checkpoint = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")
    assert state["integration_sha"] == checkpoint["new_integration_sha"]
    assert state["integration_sha"] != state["target_head_sha"]
    assert state["accepted_patchlets"] == ["P0001"]


def test_integration_state_references_wrapper_gate_result(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_mock_patchlet(ctx)

    entry = json.loads(ctx.paths.accepted_changes.read_text(encoding="utf-8").splitlines()[0])
    assert entry["wrapper_gate_result"] == ".codex-orchestrator/runs/P0001_attempt1/gates/wrapper_gate_result.json"


def test_integration_checkpoint_is_written_per_accepted_patchlet(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_mock_patchlet(ctx)

    checkpoint = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")
    assert checkpoint["kind"] == "integration_checkpoint"
    assert checkpoint["patchlet_id"] == "P0001"
    assert checkpoint["diff_path"] == ".codex-orchestrator/runs/P0001_attempt1/diff.patch"


def test_integration_artifacts_are_under_target_workflow_dir(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    assert ctx.paths.integration_dir == git_repo / ".codex-orchestrator" / "integration"
    assert ctx.paths.integration_state.parent == ctx.paths.integration_dir
    assert ctx.paths.accepted_changes.parent == ctx.paths.integration_dir
