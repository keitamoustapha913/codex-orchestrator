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
from codex_orchestrator.state import sha256_file
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.worktree import cleanup_patchlet_worktree, create_patchlet_worktree


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
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


def _run_accepted_product_change(ctx) -> None:
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}) + "\n",
        encoding="utf-8",
    )
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)


def _status(repo: Path) -> str:
    return _git(repo, "status", "--porcelain")


def test_accepted_patchlet_advances_integration_ref(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    before = read_json(ctx.paths.integration_state)["integration_sha"]

    _run_accepted_product_change(ctx)

    state = read_json(ctx.paths.integration_state)
    assert state["integration_sha"] != before
    assert _git(git_repo, "rev-parse", state["integration_ref"]) == state["integration_sha"]


def test_accepted_patchlet_does_not_dirty_target_product_file(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    before_hash = sha256_file(git_repo / "app.py")

    _run_accepted_product_change(ctx)

    assert sha256_file(git_repo / "app.py") == before_hash
    assert "app.py" not in _status(git_repo)


def test_target_product_file_remains_clean_between_patchlets(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_product_change(ctx)

    dirty_product_lines = [
        line for line in _status(git_repo).splitlines()
        if not line[3:].startswith(".codex-orchestrator/") and not line[3:].startswith(".artifacts/")
    ]
    assert dirty_product_lines == []


def test_second_patchlet_worktree_includes_first_patchlet_accepted_change(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_product_change(ctx)
    worktree = create_patchlet_worktree(ctx, patchlet_id="P0002")
    try:
        assert "# cxor mock allowed product change" in (worktree.path / "app.py").read_text(encoding="utf-8")
    finally:
        cleanup_patchlet_worktree(worktree)


def test_integration_ref_commit_contains_only_allowed_product_runtime_files(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_product_change(ctx)

    state = read_json(ctx.paths.integration_state)
    parent = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")["previous_integration_sha"]
    changed = _git(git_repo, "diff", "--name-only", parent, state["integration_sha"]).splitlines()
    assert changed == ["app.py"]


def test_integration_state_updates_after_each_accepted_patchlet(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_product_change(ctx)

    state = read_json(ctx.paths.integration_state)
    checkpoint = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")
    assert state["accepted_patchlets"] == ["P0001"]
    assert checkpoint["new_integration_sha"] == state["integration_sha"]


def test_accepted_changes_jsonl_appends_one_entry_per_accepted_patchlet(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_product_change(ctx)

    entries = [json.loads(line) for line in ctx.paths.accepted_changes.read_text(encoding="utf-8").splitlines() if line]
    assert len(entries) == 1
    assert entries[0]["new_integration_sha"] == read_json(ctx.paths.integration_state)["integration_sha"]


def test_accepted_patchlet_checkpoint_runs_integration_artifact_validation(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_product_change(ctx)

    validation_path = ctx.paths.integration_dir / "validation_result.json"
    validation = read_json(validation_path)
    assert validation["kind"] == "integration_artifact_validation"
    assert validation["valid"] is True


def test_run_manifest_records_integration_artifact_validation(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    _run_accepted_product_change(ctx)

    manifest = read_json(ctx.paths.run_manifest)
    record = manifest["runs"][-1]
    assert record["integration_artifact_validation"]["valid"] is True
    assert record["integration_artifact_validation"]["path"] == ".codex-orchestrator/integration/validation_result.json"
