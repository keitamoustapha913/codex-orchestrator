from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.operator_events import append_operator_event, operator_events_path
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


def _seed_events(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    append_operator_event(ctx.root, "patchlet_started", patchlet_id="P0001", attempt_id="P0001_attempt1", summary="Started patchlet P0001.")
    append_operator_event(ctx.root, "patchlet_worker_started", patchlet_id="P0001", attempt_id="P0001_attempt1", summary="Worker started.")
    append_operator_event(ctx.root, "patchlet_accepted", severity="success", patchlet_id="P0001", attempt_id="P0001_attempt1", summary="Accepted.")
    return ctx


def test_cxor_monitor_help_exists(git_repo: Path):
    result = _run_cli(["monitor", "--help"], cwd=git_repo)

    assert result.returncode == 0
    assert "--follow" in result.stdout
    assert "--since" in result.stdout


def test_cxor_monitor_prints_existing_operator_events(git_repo: Path):
    _seed_events(git_repo)

    result = _run_cli(["monitor", "--repo", str(git_repo)], cwd=git_repo)

    assert result.returncode == 0
    assert "OE000001" in result.stdout
    assert "Started patchlet P0001" in result.stdout


def test_cxor_monitor_json_outputs_structured_events(git_repo: Path):
    _seed_events(git_repo)

    result = _run_cli(["monitor", "--repo", str(git_repo), "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["kind"] == "operator_event_list"
    assert payload["count"] == 3


def test_cxor_monitor_since_filters_events(git_repo: Path):
    _seed_events(git_repo)

    result = _run_cli(["monitor", "--repo", str(git_repo), "--since", "OE000001", "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert [event["event_id"] for event in payload["events"]] == ["OE000002", "OE000003"]


def test_cxor_monitor_attempt_filters_events(git_repo: Path):
    _seed_events(git_repo)

    result = _run_cli(["monitor", "--repo", str(git_repo), "--attempt", "P0001_attempt1", "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["count"] == 3


def test_cxor_monitor_patchlet_filters_events(git_repo: Path):
    _seed_events(git_repo)

    result = _run_cli(["monitor", "--repo", str(git_repo), "--patchlet", "P0001", "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["count"] == 3


def test_cxor_monitor_event_type_filters_events(git_repo: Path):
    _seed_events(git_repo)

    result = _run_cli(["monitor", "--repo", str(git_repo), "--event-type", "patchlet_accepted", "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["count"] == 1
    assert payload["events"][0]["event_type"] == "patchlet_accepted"


def test_cxor_monitor_limit_limits_events(git_repo: Path):
    _seed_events(git_repo)

    result = _run_cli(["monitor", "--repo", str(git_repo), "--limit", "2", "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["count"] == 2


def test_cxor_monitor_handles_missing_events_file(git_repo: Path):
    result = _run_cli(["monitor", "--repo", str(git_repo)], cwd=git_repo)

    assert result.returncode == 0
    assert "No operator events found" in result.stdout


def test_cxor_monitor_handles_partial_trailing_line(git_repo: Path):
    ctx = _seed_events(git_repo)
    with operator_events_path(ctx.root).open("a", encoding="utf-8") as handle:
        handle.write('{"event_id": "OE999999"')

    result = _run_cli(["monitor", "--repo", str(git_repo), "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["count"] == 3


def test_cxor_monitor_is_read_only(git_repo: Path):
    ctx = _seed_events(git_repo)
    before = operator_events_path(ctx.root).stat().st_mtime_ns

    result = _run_cli(["monitor", "--repo", str(git_repo), "--json"], cwd=git_repo)
    after = operator_events_path(ctx.root).stat().st_mtime_ns

    assert result.returncode == 0
    assert after == before


def test_cxor_monitor_does_not_invoke_codex(git_repo: Path):
    _seed_events(git_repo)

    result = _run_cli(["monitor", "--repo", str(git_repo)], cwd=git_repo)

    assert result.returncode == 0
    assert "codex exec" not in result.stderr


def test_cxor_monitor_follow_can_be_exercised_with_bounded_fake_events(git_repo: Path):
    _seed_events(git_repo)

    result = _run_cli(["monitor", "--repo", str(git_repo), "--follow", "--max-events", "2", "--interval", "0.01"], cwd=git_repo)

    assert result.returncode == 0
    assert "OE000001" in result.stdout
    assert "OE000002" in result.stdout
