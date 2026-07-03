from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.operator_progress import format_operator_event_compact
from codex_orchestrator.prompt_index import read_prompt_index
from codex_orchestrator.stages.auto import run_auto
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.stages.verify_global import verify_global
from codex_orchestrator.stages.verify_group import verify_group
from codex_orchestrator.target_repo import resolve_target_repo


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


def _accepted_ctx(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    return ctx


def _event_types(ctx) -> list[str]:
    return [event["event_type"] for event in read_operator_events(ctx.root)]


def test_verify_group_emits_transaction_group_started(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_group(ctx, transaction_group_id="TG001")

    assert "transaction_group_started" in _event_types(ctx)


def test_verify_group_emits_transaction_group_passed(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_group(ctx, transaction_group_id="TG001")

    assert "transaction_group_passed" in _event_types(ctx)


def test_verify_group_emits_transaction_group_failed(git_repo: Path):
    ctx = _accepted_ctx(git_repo)
    wrapper_gate = ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json"
    gate = json.loads(wrapper_gate.read_text(encoding="utf-8"))
    gate["accepted"] = False
    wrapper_gate.write_text(json.dumps(gate), encoding="utf-8")

    verify_group(ctx, transaction_group_id="TG001")

    assert "transaction_group_failed" in _event_types(ctx)


def test_verify_group_event_includes_transaction_group_id(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_group(ctx, transaction_group_id="TG001")

    event = [event for event in read_operator_events(ctx.root) if event["event_type"] == "transaction_group_started"][-1]
    assert event["transaction_group_id"] == "TG001"


def test_verify_group_event_includes_member_patchlet_count_or_details(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_group(ctx, transaction_group_id="TG001")

    event = [event for event in read_operator_events(ctx.root) if event["event_type"] == "transaction_group_started"][-1]
    assert event["details"]["patchlet_ids"] == ["P0001"]


def test_verify_global_emits_global_verifier_started(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_global(ctx)

    assert "global_verifier_started" in _event_types(ctx)


def test_verify_global_emits_global_verifier_passed(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_global(ctx)

    assert "global_verifier_passed" in _event_types(ctx)


def test_verify_global_emits_global_verifier_failed(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    verify_global(ctx)

    assert "global_verifier_failed" in _event_types(ctx)


def test_workflow_done_emits_operator_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_auto(ctx, until="DONE", worker_mode="mock", use_worktree=True, max_iterations=30)

    assert "workflow_done" in _event_types(ctx)


def test_workflow_safe_failed_emits_operator_event(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    verify_global(ctx)

    assert "workflow_safe_failed" in _event_types(ctx)


def test_deterministic_verifier_without_prompt_emits_no_prompt_event(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_group(ctx, transaction_group_id="TG001")
    verify_global(ctx)

    events = [event for event in read_operator_events(ctx.root) if event["event_type"] == "verifier_no_prompt"]
    assert len(events) >= 2


def test_verifier_prompt_index_entry_when_prompt_exists(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_group(ctx, transaction_group_id="TG001")

    prompts = read_prompt_index(ctx.root)["prompts"]
    assert not [prompt for prompt in prompts if prompt["kind"] in {"transaction_group_verifier_prompt", "global_verifier_prompt"}]
    assert "verifier_no_prompt" in _event_types(ctx)


def test_live_progress_prints_transaction_group_events(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_group(ctx, transaction_group_id="TG001")
    event = [event for event in read_operator_events(ctx.root) if event["event_type"] == "transaction_group_started"][-1]

    assert "transaction group TG001" in format_operator_event_compact(event)


def test_live_progress_prints_global_verifier_events(git_repo: Path):
    ctx = _accepted_ctx(git_repo)

    verify_global(ctx)
    event = [event for event in read_operator_events(ctx.root) if event["event_type"] == "global_verifier_started"][-1]

    assert "global verifier" in format_operator_event_compact(event)
