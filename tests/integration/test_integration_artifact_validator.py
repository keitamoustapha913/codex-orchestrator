from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.apply_results import apply_results
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.integration_artifact_validator import validate_integration_artifacts


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


def _ctx_with_accepted_change(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    mock_dir = ctx.paths.workflow_dir / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "next_patchlet_result.json").write_text(
        json.dumps({"change_allowed_product": True, "status": "COMPLETE"}) + "\n",
        encoding="utf-8",
    )
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    return ctx


def test_validate_integration_artifacts_accepts_generated_artifacts(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)

    result = validate_integration_artifacts(ctx.root)

    assert result["valid"] is True
    assert result["validated"]["integration_state"] is True
    assert result["validated"]["accepted_changes"] is True
    assert result["validated"]["checkpoints"] is True


def test_validate_integration_artifacts_reports_missing_integration_state(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    ctx.paths.integration_state.unlink()

    result = validate_integration_artifacts(ctx.root)

    assert result["valid"] is False
    assert any(error["path"].endswith("integration_state.json") for error in result["errors"])


def test_validate_integration_artifacts_reports_invalid_accepted_change_line(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    with ctx.paths.accepted_changes.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")

    result = validate_integration_artifacts(ctx.root)

    assert result["valid"] is False
    assert any(error.get("line") == 2 and "invalid JSON" in error["message"] for error in result["errors"])


def test_validate_integration_artifacts_reports_invalid_checkpoint(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    checkpoint = ctx.paths.integration_checkpoints_dir / "P0001.json"
    payload = read_json(checkpoint)
    payload["kind"] = "wrong"
    write_json(checkpoint, payload)

    result = validate_integration_artifacts(ctx.root)

    assert result["valid"] is False
    assert any(error["schema"] == "integration_checkpoint.schema.json" for error in result["errors"])


def test_validate_integration_artifacts_reports_invalid_apply_results_result(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    apply_results(ctx, mode="patch")
    result_path = ctx.paths.integration_dir / "apply_results" / "patch_result.json"
    payload = read_json(result_path)
    payload["mutated_working_tree"] = True
    write_json(result_path, payload)

    result = validate_integration_artifacts(ctx.root)

    assert result["valid"] is False
    assert any(error["schema"] == "apply_results_result.schema.json" for error in result["errors"])


def test_validate_integration_artifacts_handles_empty_accepted_changes_jsonl(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    result = validate_integration_artifacts(ctx.root)

    assert result["valid"] is True
    assert result["validated"]["accepted_changes"] is True


def test_validate_integration_artifacts_returns_structured_errors(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    payload = read_json(ctx.paths.integration_state)
    payload.pop("integration_sha")
    write_json(ctx.paths.integration_state, payload)

    result = validate_integration_artifacts(ctx.root)

    assert result["valid"] is False
    assert result["errors"]
    assert {"path", "schema", "message"}.issubset(result["errors"][0])
