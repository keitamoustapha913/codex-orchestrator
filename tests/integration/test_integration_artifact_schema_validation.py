from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.apply_results import apply_results
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json, validate_json_file


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


def _accepted_change_entry(ctx) -> dict:
    lines = [line for line in ctx.paths.accepted_changes.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    return json.loads(lines[0])


def _without(payload: dict, key: str) -> dict:
    copy = dict(payload)
    copy.pop(key, None)
    return copy


def test_generated_integration_state_validates_against_schema(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    assert validate_json_file(ctx.paths.integration_state, "integration_state.schema.json") == []


def test_integration_state_schema_rejects_missing_kind(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    errors = validate_json(_without(read_json(ctx.paths.integration_state), "kind"), "integration_state.schema.json")

    assert errors


def test_integration_state_schema_rejects_wrong_kind(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    payload = read_json(ctx.paths.integration_state)
    payload["kind"] = "wrong"

    assert validate_json(payload, "integration_state.schema.json")


def test_integration_state_schema_rejects_missing_integration_sha(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])

    assert validate_json(_without(read_json(ctx.paths.integration_state), "integration_sha"), "integration_state.schema.json")


def test_integration_state_schema_rejects_invalid_apply_mode(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    payload = read_json(ctx.paths.integration_state)
    payload["apply_mode"] = "direct"

    assert validate_json(payload, "integration_state.schema.json")


def test_generated_accepted_changes_jsonl_entries_validate_against_schema(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)

    entries = [json.loads(line) for line in ctx.paths.accepted_changes.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert entries
    assert all(validate_json(entry, "accepted_change.schema.json") == [] for entry in entries)


def test_accepted_change_schema_rejects_missing_patchlet_id(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)

    assert validate_json(_without(_accepted_change_entry(ctx), "patchlet_id"), "accepted_change.schema.json")


def test_accepted_change_schema_rejects_wrong_kind(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = _accepted_change_entry(ctx)
    payload["kind"] = "wrong"

    assert validate_json(payload, "accepted_change.schema.json")


def test_accepted_change_schema_rejects_missing_wrapper_gate_result(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)

    assert validate_json(_without(_accepted_change_entry(ctx), "wrapper_gate_result"), "accepted_change.schema.json")


def test_accepted_change_schema_rejects_non_array_changed_product_runtime_files(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = _accepted_change_entry(ctx)
    payload["changed_product_runtime_files"] = "app.py"

    assert validate_json(payload, "accepted_change.schema.json")


def test_generated_integration_checkpoint_validates_against_schema(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)

    assert validate_json_file(ctx.paths.integration_checkpoints_dir / "P0001.json", "integration_checkpoint.schema.json") == []


def test_integration_checkpoint_schema_rejects_missing_new_integration_sha(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")

    assert validate_json(_without(payload, "new_integration_sha"), "integration_checkpoint.schema.json")


def test_integration_checkpoint_schema_rejects_dirty_target_flag_false(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")
    payload["target_working_tree_clean_after_checkpoint"] = False

    assert validate_json(payload, "integration_checkpoint.schema.json")


def test_integration_checkpoint_schema_rejects_missing_wrapper_gate_result(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")

    assert validate_json(_without(payload, "wrapper_gate_result"), "integration_checkpoint.schema.json")


def test_integration_checkpoint_schema_rejects_non_array_changed_product_runtime_files(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")
    payload["changed_product_runtime_files"] = "app.py"

    assert validate_json(payload, "integration_checkpoint.schema.json")


def test_apply_results_patch_result_validates_against_schema(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    result = apply_results(ctx, mode="patch")

    assert validate_json(result, "apply_results_result.schema.json") == []


def test_apply_results_branch_result_validates_against_schema(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    result = apply_results(ctx, mode="branch")

    assert validate_json(result, "apply_results_result.schema.json") == []


def test_apply_results_working_tree_result_validates_against_schema(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    result = apply_results(ctx, mode="working-tree")

    assert validate_json(result, "apply_results_result.schema.json") == []


def test_apply_results_result_schema_rejects_missing_mode(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = apply_results(ctx, mode="patch")

    assert validate_json(_without(payload, "mode"), "apply_results_result.schema.json")


def test_apply_results_result_schema_rejects_patch_mode_with_mutated_working_tree_true(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = apply_results(ctx, mode="patch")
    payload["mutated_working_tree"] = True

    assert validate_json(payload, "apply_results_result.schema.json")


def test_apply_results_result_schema_rejects_branch_mode_without_created_branch(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = apply_results(ctx, mode="branch")
    payload["created_branch"] = None

    assert validate_json(payload, "apply_results_result.schema.json")


def test_apply_results_result_schema_rejects_working_tree_mode_with_mutated_working_tree_false(git_repo: Path):
    ctx = _ctx_with_accepted_change(git_repo)
    payload = apply_results(ctx, mode="working-tree")
    payload["mutated_working_tree"] = False

    assert validate_json(payload, "apply_results_result.schema.json")
