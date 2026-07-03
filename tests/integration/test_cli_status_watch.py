from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


def _run_cli(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", *args],
        cwd=cwd,
        env=os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _ctx_with_attempt(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    return ctx


def _status_json(git_repo: Path) -> dict:
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_status_help_includes_json_and_watch(git_repo: Path):
    result = _run_cli(["status", "--help"], cwd=git_repo)

    assert result.returncode == 0
    assert "--json" in result.stdout
    assert "--watch" in result.stdout


def test_status_json_contains_operator_status_fields(git_repo: Path):
    _ctx_with_attempt(git_repo)

    payload = _status_json(git_repo)

    assert payload["kind"] == "operator_status"
    assert payload["repo"] == str(git_repo)


def test_status_json_reports_current_patchlet_and_attempt(git_repo: Path):
    _ctx_with_attempt(git_repo)

    payload = _status_json(git_repo)

    assert payload["current_patchlet_id"] == "P0001"
    assert payload["current_attempt_id"] == "P0001_attempt1"


def test_status_json_reports_loop_iteration(git_repo: Path):
    ctx = _ctx_with_attempt(git_repo)
    state = json.loads(ctx.paths.state.read_text(encoding="utf-8"))
    state["current_loop_iteration"] = 87
    ctx.paths.state.write_text(json.dumps(state), encoding="utf-8")

    payload = _status_json(git_repo)

    assert payload["current_loop_iteration"] == 87


def test_status_json_reports_patchlet_counts(git_repo: Path):
    _ctx_with_attempt(git_repo)

    payload = _status_json(git_repo)

    assert payload["completed_patchlet_count"] >= 1
    assert payload["failed_patchlet_count"] == 0
    assert payload["pending_patchlet_count"] == 0


def test_status_json_reports_last_event(git_repo: Path):
    _ctx_with_attempt(git_repo)

    payload = _status_json(git_repo)

    assert payload["last_event"]["event_id"].startswith("OE")


def test_status_json_reports_active_prompt_path(git_repo: Path):
    _ctx_with_attempt(git_repo)

    payload = _status_json(git_repo)

    assert payload["active_prompt_path"].endswith("codex_task_prompt.md")


def test_status_json_reports_last_progress_age(git_repo: Path):
    _ctx_with_attempt(git_repo)

    payload = _status_json(git_repo)

    assert isinstance(payload["last_progress_age_seconds"], int)


def test_status_json_classifies_active_from_recent_progress(git_repo: Path):
    _ctx_with_attempt(git_repo)

    payload = _status_json(git_repo)

    assert payload["classification"] in {"active", "silent_but_active"}


def test_status_json_classifies_silent_but_active_from_recent_file_progress_without_terminal(git_repo: Path):
    ctx = _ctx_with_attempt(git_repo)
    progress = ctx.paths.runs_dir / "P0001_attempt1" / "progress.jsonl"
    if progress.exists():
        progress.unlink()

    payload = _status_json(git_repo)

    assert payload["classification"] == "silent_but_active"


def test_status_json_classifies_likely_stalled_from_old_progress(git_repo: Path):
    ctx = _ctx_with_attempt(git_repo)
    old = time.time() - 1000
    for path in (ctx.paths.runs_dir / "P0001_attempt1").glob("*.txt"):
        os.utime(path, (old, old))
    for path in (ctx.paths.runs_dir / "P0001_attempt1").glob("*.jsonl"):
        os.utime(path, (old, old))

    payload = _status_json(git_repo)

    assert payload["classification"] == "likely_stalled"


def test_status_json_classifies_done_when_final_state_done(git_repo: Path):
    ctx = _ctx_with_attempt(git_repo)
    state = json.loads(ctx.paths.state.read_text(encoding="utf-8"))
    state["stage"] = "DONE"
    ctx.paths.state.write_text(json.dumps(state), encoding="utf-8")

    payload = _status_json(git_repo)

    assert payload["classification"] == "done"


def test_status_json_handles_missing_operator_events(git_repo: Path):
    ctx = _ctx_with_attempt(git_repo)
    (ctx.paths.workflow_dir / "operator_events.jsonl").unlink()

    payload = _status_json(git_repo)

    assert payload["last_event"] is None


def test_status_json_handles_missing_prompt_index(git_repo: Path):
    ctx = _ctx_with_attempt(git_repo)
    (ctx.paths.workflow_dir / "prompt_index.json").unlink()

    payload = _status_json(git_repo)

    assert payload["active_prompt_path"] is None


def test_status_watch_prints_repeated_status_in_bounded_mode(git_repo: Path):
    _ctx_with_attempt(git_repo)

    result = _run_cli(
        ["status", "--repo", str(git_repo), "--watch", "--interval", "0.01", "--max-iterations", "2"],
        cwd=git_repo,
    )

    assert result.returncode == 0
    assert result.stdout.count("Repo:") == 2


def test_status_watch_is_read_only(git_repo: Path):
    ctx = _ctx_with_attempt(git_repo)
    before = ctx.paths.state.stat().st_mtime_ns

    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    after = ctx.paths.state.stat().st_mtime_ns

    assert result.returncode == 0
    assert after == before


def test_status_watch_does_not_invoke_codex(git_repo: Path):
    _ctx_with_attempt(git_repo)

    result = _run_cli(["status", "--repo", str(git_repo), "--watch", "--max-iterations", "1"], cwd=git_repo)

    assert result.returncode == 0
    assert "codex exec" not in result.stderr
