from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.operator_events import append_operator_event, read_operator_events
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo


def _run_cli(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", *args],
        cwd=cwd,
        env=full_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _setup_compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _write_invalid_report_scenario(ctx) -> None:
    scenario = {"report_override": {"probe_artifact_refs": ["not-an-object"]}}
    scenario_path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")


def test_cxor_auto_help_includes_live_progress_flags(git_repo: Path):
    result = _run_cli(["auto", "--help"], cwd=git_repo)

    assert result.returncode == 0
    assert "--live-progress" in result.stdout
    assert "--no-live-progress" in result.stdout
    assert "--progress-interval-seconds" in result.stdout
    assert "--progress-format" in result.stdout


def test_cxor_auto_live_progress_prints_workflow_started(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--live-progress"],
        cwd=git_repo,
    )

    assert result.returncode == 0
    assert "[cxor +" in result.stderr
    assert "workflow started repo=" in result.stderr


def test_cxor_auto_live_progress_prints_patchlet_started(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--live-progress"],
        cwd=git_repo,
    )

    assert "Started patchlet P0001" in result.stderr


def test_cxor_auto_live_progress_prints_prompt_saved(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--live-progress"],
        cwd=git_repo,
    )

    assert "Prompt saved for P0001_attempt1" in result.stderr


def test_cxor_auto_live_progress_prints_worker_started(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--live-progress"],
        cwd=git_repo,
    )

    assert "Worker started for P0001_attempt1" in result.stderr


def test_cxor_auto_live_progress_prints_worker_exited(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--live-progress"],
        cwd=git_repo,
    )

    assert "Worker exited for P0001_attempt1 code=0" in result.stderr


def test_cxor_auto_live_progress_prints_report_validation_failure(git_repo: Path):
    ctx = _setup_compiled_ctx(git_repo)
    _write_invalid_report_scenario(ctx)

    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--resume", "--until", "FAILURE_CLASSIFICATION_REQUIRED", "--worker-mode", "mock", "--use-worktree", "--live-progress"],
        cwd=git_repo,
    )

    assert result.returncode == 0
    assert "Report validation failed for P0001" in result.stderr


def test_cxor_auto_live_progress_prints_repair_plan_next_action(git_repo: Path):
    ctx = _setup_compiled_ctx(git_repo)
    _write_invalid_report_scenario(ctx)

    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--resume", "--until", "REPAIR_PLAN_READY", "--worker-mode", "mock", "--use-worktree", "--live-progress"],
        cwd=git_repo,
    )

    assert result.returncode == 0
    assert "Repair plan RP0001 created" in result.stderr


def test_cxor_auto_live_progress_does_not_replay_stale_loop_warning(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    append_operator_event(
        ctx.root,
        event_type="loop_governor_warning",
        severity="warning",
        stage="PATCHLET_REGENERATION_REQUIRED",
        summary="Repeated failure signature probe_artifact_refs_not_objects count=3 threshold=3.",
    )

    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--live-progress"],
        cwd=git_repo,
    )

    assert "probe_artifact_refs_not_objects" not in result.stderr
    assert "workflow started" in result.stderr


def test_cxor_auto_no_live_progress_suppresses_terminal_output_but_writes_events(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--no-live-progress"],
        cwd=git_repo,
    )
    ctx = resolve_target_repo(repo=git_repo)

    assert result.returncode == 0
    assert "[cxor +" not in result.stderr
    assert [event["event_type"] for event in read_operator_events(ctx.root)]


def test_cxor_auto_progress_format_jsonl_outputs_json_events(git_repo: Path):
    result = _run_cli(
        [
            "auto",
            "--repo",
            str(git_repo),
            "--master",
            str(git_repo / "master_prompt.md"),
            "--until",
            "DONE",
            "--worker-mode",
            "mock",
            "--live-progress",
            "--progress-format",
            "jsonl",
        ],
        cwd=git_repo,
    )

    lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert json.loads(lines[0])["kind"] == "operator_event"


def test_cxor_auto_live_progress_does_not_print_full_prompt_body(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--live-progress"],
        cwd=git_repo,
    )

    assert "REPORT_SCHEMA_CONTRACT" not in result.stderr
    assert "PYTHON RUNTIME SIDE EFFECT CONTRACT" not in result.stderr


def test_cxor_auto_live_progress_does_not_print_raw_codex_json_by_default(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--live-progress"],
        cwd=git_repo,
    )

    assert '{"mock": true' not in result.stderr


def test_cxor_auto_live_progress_interval_suppresses_excess_heartbeats(git_repo: Path):
    result = _run_cli(
        [
            "auto",
            "--repo",
            str(git_repo),
            "--master",
            str(git_repo / "master_prompt.md"),
            "--until",
            "DONE",
            "--worker-mode",
            "mock",
            "--live-progress",
            "--progress-interval-seconds",
            "120",
        ],
        cwd=git_repo,
    )

    assert "still running" not in result.stderr


def test_cxor_auto_live_progress_env_enables_output(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock"],
        cwd=git_repo,
        env={"CXOR_LIVE_PROGRESS": "1"},
    )

    assert "[cxor +" in result.stderr


def test_cxor_auto_no_live_progress_overrides_env(git_repo: Path):
    result = _run_cli(
        ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--until", "DONE", "--worker-mode", "mock", "--no-live-progress"],
        cwd=git_repo,
        env={"CXOR_LIVE_PROGRESS": "1"},
    )

    assert "[cxor +" not in result.stderr


def test_real_codex_runbook_live_progress_still_works_with_existing_flags(git_repo: Path):
    result = _run_cli(["real-codex-smoke-runbook", "--help"], cwd=git_repo)

    assert result.returncode == 0
    assert "--live-progress" in result.stdout
    assert "--no-live-progress" in result.stdout
