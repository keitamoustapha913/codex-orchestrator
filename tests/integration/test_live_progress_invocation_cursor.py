from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from codex_orchestrator.operator_events import append_operator_event


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def test_live_progress_starts_after_invocation_cursor(git_repo: Path):
    (git_repo / ".codex-orchestrator").mkdir()
    append_operator_event(git_repo, "old_event", summary="old event should not print")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY", "--live-progress"], cwd=git_repo)
    assert result.returncode == 0
    assert "old event should not print" not in result.stderr
    assert "workflow started" in result.stderr


def test_live_progress_does_not_replay_old_workflow_events(git_repo: Path):
    (git_repo / ".codex-orchestrator").mkdir()
    append_operator_event(git_repo, "workflow_started", summary="stale workflow started")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY", "--live-progress"], cwd=git_repo)
    assert "stale workflow started" not in result.stderr


def test_live_progress_prints_new_events_only(git_repo: Path):
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY", "--live-progress"], cwd=git_repo)
    assert result.returncode == 0
    assert "workflow started" in result.stderr


def test_live_progress_records_invocation_artifact(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY", "--live-progress"], cwd=git_repo)
    assert list((git_repo / ".codex-orchestrator" / "invocations").glob("INV*.json"))


def test_operator_events_include_invocation_id_for_new_invocation(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY", "--live-progress"], cwd=git_repo)
    events = (git_repo / ".codex-orchestrator" / "operator_events.jsonl").read_text(encoding="utf-8")
    assert "INV000001" in events


def test_monitor_can_filter_by_invocation_id(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY", "--live-progress"], cwd=git_repo)
    result = _run_cli(["monitor", "--repo", str(git_repo), "--invocation", "INV000001", "--json"], cwd=git_repo)
    assert result.returncode == 0
    assert "operator_event_list" in result.stdout


def test_jsonl_progress_includes_invocation_id(git_repo: Path):
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY", "--live-progress", "--progress-format", "jsonl"], cwd=git_repo)
    assert result.returncode == 0
    assert '"invocation_id": "INV000001"' in result.stderr


def test_existing_operator_events_without_invocation_are_ignored_for_current_live_stream(git_repo: Path):
    (git_repo / ".codex-orchestrator").mkdir()
    append_operator_event(git_repo, "patchlet_started", summary="old patchlet")
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "PATCHLETS_READY", "--live-progress"], cwd=git_repo)
    assert "old patchlet" not in result.stderr
