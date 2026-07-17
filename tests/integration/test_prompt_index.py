from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.prompt_index import read_prompt_index
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.classify_failures import classify_failures
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.plan_repair import plan_repair
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def _init_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return ctx


def _compiled_ctx(git_repo: Path):
    ctx = _init_ctx(git_repo)
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _prompt_entries(ctx, kind: str | None = None):
    entries = read_prompt_index(ctx.root)["prompts"]
    if kind is not None:
        entries = [entry for entry in entries if entry["kind"] == kind]
    return entries


def _invalid_report_then_abort(ctx):
    scenario_path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_path.write_text(json.dumps({"report_production_override": {"probe_artifact_refs": ["bad"]}}), encoding="utf-8")
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    classify_failures(ctx)
    plan_repair(ctx)


def test_prompt_index_created_when_master_prompt_is_copied(git_repo: Path):
    ctx = _init_ctx(git_repo)

    entries = _prompt_entries(ctx, "master_prompt")

    assert len(entries) == 1
    assert entries[0]["path"] == ".codex-orchestrator/master_prompt.md"


def test_prompt_index_created_when_patchlet_subprompt_written(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    entries = _prompt_entries(ctx, "patchlet_subprompt")

    assert entries
    assert entries[0]["patchlet_id"] == "P0001"
    assert entries[0]["path"].startswith(".codex-orchestrator/subprompts/")


def test_prompt_index_created_when_patchlet_prompt_written(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entries = _prompt_entries(ctx, "patchlet_worker_prompt")
    assert entries[0]["path"] == ".codex-orchestrator/runs/P0001_attempt1/codex_task_prompt.md"


def test_prompt_index_entry_contains_prompt_path(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _prompt_entries(ctx, "patchlet_worker_prompt")[0]

    assert (ctx.root / entry["path"]).exists()


def test_prompt_index_entry_contains_patchlet_and_attempt(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _prompt_entries(ctx, "patchlet_worker_prompt")[0]

    assert entry["patchlet_id"] == "P0001"
    assert entry["attempt_id"] == "P0001_attempt1"


def test_prompt_index_entry_contains_sha256_and_size(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _prompt_entries(ctx, "patchlet_worker_prompt")[0]

    assert len(entry["sha256"]) == 64
    assert entry["size_bytes"] > 0


def test_prompt_index_entry_contains_model_and_reasoning(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _prompt_entries(ctx, "patchlet_worker_prompt")[0]

    assert "model" in entry
    assert "reasoning" in entry


def test_prompt_index_entry_contains_contracts(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _prompt_entries(ctx, "patchlet_worker_prompt")[0]

    assert "TASK_COMPLETION_HANDOFF_CONTRACT.md" in entry["contracts"]
    assert "REPORT_SCHEMA_CONTRACT.md" not in entry["contracts"]
    assert "FINAL_REPORT_CONTRACT.md" in entry["contracts"]


def test_prompt_index_entry_contains_subprompt_path_when_available(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    entry = _prompt_entries(ctx, "patchlet_worker_prompt")[0]

    assert entry["subprompt_path"].startswith(".codex-orchestrator/subprompts/")


def test_prompt_index_written_before_worker_start_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    events = read_operator_events(ctx.root)
    event_types = [event["event_type"] for event in events]
    assert event_types.index("prompt_index_updated") < event_types.index("patchlet_worker_started")


def test_prompt_index_does_not_add_product_repair_prompt_for_report_only_failure(
    git_repo: Path,
):
    ctx = _compiled_ctx(git_repo)

    _invalid_report_then_abort(ctx)

    repair_entries = _prompt_entries(ctx, "repair_subprompt")
    assert repair_entries == []


def test_prompt_index_does_not_duplicate_same_prompt_path(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    paths = [entry["path"] for entry in _prompt_entries(ctx)]
    assert len(paths) == len(set(paths))


def test_prompt_index_schema_validates_generated_index(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert validate_json_file(ctx.paths.workflow_dir / "prompt_index.json", "prompt_index.schema.json") == []


def test_prompt_index_updated_operator_event_written(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    events = [event for event in read_operator_events(ctx.root) if event["event_type"] == "prompt_index_updated"]
    assert events
    assert events[-1]["prompt_id"].startswith("PR")
